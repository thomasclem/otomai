"""Behavioural tests with no network, real orders or Telegram messages."""

import copy
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import ccxt
import pytest
from pydantic import ValidationError

from otomai import configs
from otomai.adapters import BingXExchange
from otomai.core.constants import DAY_MS, HOUR_MS
from otomai.core.enums import TradeSide
from otomai.core.exceptions import OrderNotFound
from otomai.settings import MainSettings
from otomai.strategies.listing_volume_short import (
    ListingVolumeShortStrategy,
    ListingVolumeStrategyParams,
)
from otomai.strategies.listing_volume_short.signal import (
    ListingDataError,
    initial_volume,
    reject_prelisting_trades,
    volume_reference,
)
from otomai.strategies.listing_volume_short.state import Listing, ListingState

L = int(datetime(2030, 1, 31, tzinfo=UTC).timestamp() * 1000)
NOW = L + 4 * HOUR_MS  # the decision of the SYMBOL listing
SYMBOL = "NEW/USDT:USDT"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(
        ccxt.Exchange, "fetch", Mock(side_effect=AssertionError("Network forbidden"))
    )


def bars(start=L, volume=10.0):
    return [[start + i * HOUR_MS, 100.0, 101.0, 99.0, 100.0, volume] for i in range(4)]


class Venue:
    """In-memory exchange account behind FakeBingX."""

    def __init__(self):
        self.markets, self.candles, self.orders = {}, {}, {}
        self.positions, self.open_orders, self.writes = [], [], []
        self.bid, self.ask = 100.0, 100.1
        self.entry_timeout = self.protect_timeout = self.close_timeout = self.reject_prepare = False
        self.accept_entry = self.accept_close = True
        self.close_rests = False
        self.before_entry = None
        self.add(SYMBOL, L)

    def add(self, symbol, launch):
        self.markets[symbol] = {
            "symbol": symbol,
            "base": symbol.split("/")[0],
            "swap": True,
            "linear": True,
            "settle": "USDT",
            "active": True,
            "contractSize": 1.0,
            "info": {"launchTime": launch},
        }
        self.candles[symbol] = bars(launch)


class FakeBingX(BingXExchange):
    """The exchange port over a Venue; adapter details are tested separately."""

    def markets(self):
        return {s: self.normalize_market(m) for s, m in self._session.markets.items()}

    def require_live_credentials(self):
        pass

    def account_fingerprint(self):
        return "test-account-fingerprint"

    def candles(self, symbol, timeframe, since=None, until=None, limit=None):
        return self._session.candles[symbol]

    def balance(self):
        return 10_000.0, 10_000.0

    def positions(self, symbols=None):
        return copy.deepcopy(self._session.positions)

    def open_orders(self, symbol=None):
        return [r for r in self._session.open_orders if symbol is None or r["symbol"] == symbol]

    def order_book(self, symbol, depth=50):
        return {"bids": [(self._session.bid, 1e9)], "asks": [(self._session.ask, 1e9)]}

    def order_amount(self, symbol, notional, price):
        q = int(notional / price * 1e6) / 1e6
        return q, q * price

    def set_margin_mode_and_leverage(self, symbol, margin_mode, leverage):
        if self._session.reject_prepare:
            raise ccxt.ExchangeError("Cannot set isolated margin")

    def create_order(
        self,
        symbol,
        side,
        amount,
        type,
        trade_side,
        margin_mode,
        price=None,
        reduce=False,
        take_profit_price=None,
        stop_loss_price=None,
        client_id=None,
    ):
        if trade_side == TradeSide.OPEN:
            return self._enter(symbol, amount, stop_loss_price, client_id)
        if type == "limit":
            return self._resting("target", symbol, amount, client_id)
        return self._close(symbol, client_id)

    def create_stop_order(self, symbol, side, amount, trigger_price, client_id=None):
        return self._resting("stop", symbol, amount, client_id)

    def _enter(self, symbol, amount, stop_price, cid):
        v = self._session
        if v.before_entry:
            v.before_entry()
        v.writes.append(("entry", symbol, cid))
        order = {
            "id": "entry",
            "symbol": symbol,
            "status": "closed",
            "filled": amount,
            "average": 100.0,
            "timestamp": NOW,
        }
        if v.accept_entry:
            v.orders[cid] = order
            v.positions.append(
                {"symbol": symbol, "side": "short", "contracts": amount, "notional": amount * 100}
            )
            v.open_orders.append(
                {
                    "id": "bootstrap",
                    "symbol": symbol,
                    "side": "buy",
                    "type": "stop_market",
                    "reduceOnly": True,
                    "stopLossPrice": stop_price,
                    "timestamp": NOW,
                }
            )
        if v.entry_timeout:
            raise ccxt.RequestTimeout("Entry acknowledgement lost")
        return order

    def _resting(self, name, symbol, amount, cid):
        v = self._session
        if name == "target" and v.protect_timeout:
            raise ccxt.RequestTimeout("Target acknowledgement lost")
        v.writes.append((name, symbol, cid))
        order = {
            "id": f"{name}-{cid}",
            "clientOrderId": cid,
            "symbol": symbol,
            "status": "open",
            "amount": amount,
        }
        v.orders[cid] = order
        v.open_orders.append(order)
        return order

    def _close(self, symbol, cid):
        v = self._session
        v.writes.append(("close", symbol, cid))
        if v.accept_close:
            v.positions = []
            v.orders[cid] = {"id": "close", "status": "closed", "symbol": symbol}
        elif v.close_rests:
            v.orders[cid] = {"id": "close", "status": "open", "symbol": symbol}
        if v.close_timeout:
            raise ccxt.RequestTimeout("Close acknowledgement lost")
        return v.orders.get(cid, {"id": None, "status": "rejected", "symbol": symbol})

    def order_by_client_id(self, symbol, cid):
        if cid not in self._session.orders:
            raise OrderNotFound(cid)
        return self._session.orders[cid]

    def cancel(self, symbol, oid):
        self._session.open_orders = [r for r in self._session.open_orders if r["id"] != oid]
        for order in self._session.orders.values():
            if order["id"] == oid and order["status"] == "open":
                order["status"] = "canceled"


def kinds(venue):
    return {o["id"].split("-")[0] for o in venue.open_orders}


@pytest.fixture
def runner(tmp_path):
    opened = []

    def build(*, venue=None, path=None, seed=True, **params):
        v = venue or Venue()
        exchange = FakeBingX()
        exchange._session = v
        p = {
            "state_path": str(path or tmp_path / "state.sqlite"),
            "history_batch_size": 100,
            **params,
        }
        bot = ListingVolumeShortStrategy(
            strategy_params=ListingVolumeStrategyParams(**p), exchange_service=exchange
        )
        bot.__enter__()
        opened.append(bot)
        if seed:
            for i in range(10):
                bot._state.discover(f"REF{i}/USDT:USDT", L - (10 - i) * DAY_MS)
            for row in bot._state.rows():
                if row.symbol.startswith("REF"):
                    bot._state.save(row, NOW, status="expired", volume=1000.0)
        return bot, v

    yield build
    for bot in opened:
        bot.__exit__()


def current(bot):
    return next(r for r in bot._state.rows() if r.symbol == SYMBOL)


def test_initial_window_ignores_later_bars():
    candles = bars() + [[L + 4 * HOUR_MS, 100, 9999, 1, 9999, 1e12]]
    assert initial_volume(candles, L, 4, NOW) == 4000


@pytest.mark.parametrize(
    "candles",
    [
        bars()[:-1],
        bars() + [bars()[0]],
        [[L, 100, 90, 99, 100, 10]] + bars()[1:],
        [[L, 100, 101, 99, 100, float("nan")]] + bars()[1:],
    ],
)
def test_bad_initial_window_rejected(candles):
    with pytest.raises(ValueError):
        initial_volume(candles, L, 4, NOW)


def test_unclosed_and_zero_volume_are_not_signals():
    with pytest.raises(ValueError):
        initial_volume(bars(), L, 4, L + 3 * HOUR_MS)
    with pytest.raises(ValueError):
        initial_volume(bars(volume=0), L, 4, NOW)


def test_reference_excludes_simultaneous_future_and_missing_member():
    p = ListingVolumeStrategyParams()
    rows = [
        SimpleNamespace(symbol=str(i), listing_ms=L - (i + 1) * HOUR_MS, volume=1000.0)
        for i in range(31)
    ]
    rows += [
        SimpleNamespace(symbol="same", listing_ms=L, volume=1e12),
        SimpleNamespace(symbol="future", listing_ms=L + HOUR_MS, volume=1e12),
    ]
    assert volume_reference(rows, L, p) == 1000
    rows[0].volume = None
    assert volume_reference(rows, L, p) is None


def test_invalid_history_is_a_listing_data_error():
    with pytest.raises(ListingDataError):
        initial_volume(bars()[:-1], L, 4, NOW)
    with pytest.raises(ListingDataError):
        initial_volume([[L, 100, 90, 99, 100, 10]] + bars()[1:], L, 4, NOW)
    with pytest.raises(ValueError) as early:
        initial_volume(bars(), L, 4, L + 3 * HOUR_MS)
    assert not isinstance(early.value, ListingDataError)  # scheduling, not data


def test_prelisting_trades_rejected_but_placeholders_allowed():
    reject_prelisting_trades([[L - HOUR_MS, 100, 100, 100, 100, 0.0]] + bars(), L)
    with pytest.raises(ListingDataError):
        reject_prelisting_trades([[L - HOUR_MS, 100, 101, 99, 100, 5.0]] + bars(), L)


def test_state_single_owner_and_frozen_identity(tmp_path):
    path = str(tmp_path / "state.sqlite")
    state = ListingState(path, {"account": "a"})
    with pytest.raises(RuntimeError, match="Another runner"):
        ListingState(path, {"account": "a"})
    state.close()
    with pytest.raises(RuntimeError, match="different account or rule"):
        ListingState(path, {"account": "b"})
    state = ListingState(path, {"account": "a"})
    state.close()


def test_config_registration_credential_free():
    root = Path(__file__).parents[2]
    config = configs.to_object(configs.parse_file(str(root / "conf/dev/listing_volume_short.yml")))
    bot = MainSettings.model_validate(config).strategy
    assert isinstance(bot, ListingVolumeShortStrategy)
    assert bot.exchange_service._session is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"volume_multiplier": float("nan")},
        {"min_reference_listings": 31},
        {"bootstrap_listings": 30, "reference_listings": 40},
    ],
)
def test_invalid_params_rejected(kwargs):
    with pytest.raises(ValidationError):
        ListingVolumeStrategyParams(**kwargs)


def test_late_signal_expires(runner):
    bot, v = runner()
    bot.cycle(NOW + 121000)
    assert current(bot).status == "expired" and not v.writes


def test_three_simultaneous_entries_share_day_budget(runner):
    bot, v = runner()
    v.add("NEW2/USDT:USDT", L)
    v.add("NEW3/USDT:USDT", L)
    bot.cycle(NOW)
    opened = [r for r in bot._state.rows() if r.status == "entry_pending"]
    assert len(opened) == 3 and sum(r.notional for r in opened) <= 1000
    assert max(r.notional for r in opened) == pytest.approx(min(r.notional for r in opened))


def test_missing_reference_blocks_signal(runner):
    bot, v = runner()
    r = bot._state.rows()[0]
    bot._state.save(r, NOW, volume=0.0)
    bot.cycle(NOW)
    assert current(bot).status == "observing" and not v.writes


def test_tradfi_and_excluded_bases_are_outside_universe(runner):
    bot, v = runner()
    for symbol in ["NCSKAAPU2USD/USDT:USDT", "NCFXEURSGD2USD/USDT:USDT", "PAXG/USDT:USDT"]:
        v.add(symbol, L)
    bot.cycle(NOW)
    assert {r.symbol for r in bot._state.rows() if not r.symbol.startswith("REF")} == {SYMBOL}


def test_invalid_old_window_is_excluded_and_stops_blocking_reference(runner):
    bot, v = runner()
    v.add("BAD/USDT:USDT", L - DAY_MS)
    v.candles["BAD/USDT:USDT"] = v.candles["BAD/USDT:USDT"][:3]
    bot.cycle(NOW)
    bad = next(r for r in bot._state.rows() if r.symbol == "BAD/USDT:USDT")
    assert bad.status == "excluded" and bad.excluded_reason
    assert current(bot).status == "entry_pending"


def test_transient_failure_keeps_blocking_reference(runner, monkeypatch):
    bot, v = runner()
    v.add("LAG/USDT:USDT", L - DAY_MS)
    original = FakeBingX.candles

    def flaky(self, symbol, *args, **kwargs):
        if symbol == "LAG/USDT:USDT":
            raise ccxt.NetworkError("timeout")
        return original(self, symbol, *args, **kwargs)

    monkeypatch.setattr(FakeBingX, "candles", flaky)
    bot.cycle(NOW)
    lag = next(r for r in bot._state.rows() if r.symbol == "LAG/USDT:USDT")
    assert lag.excluded_reason is None and lag.volume_error
    assert current(bot).status == "observing" and not v.writes


@pytest.mark.parametrize(
    "candles",
    [
        bars()[:3],  # last decision bar not yet published
        [[L - HOUR_MS, 100.0, 101.0, 99.0, 100.0, 5.0]] + bars(),  # relaunch / early start
    ],
)
def test_bad_own_window_retries_within_entry_window_then_excluded(runner, candles):
    decision = L + 4 * HOUR_MS
    bot, v = runner()
    v.candles[SYMBOL] = candles
    bot.cycle(decision)
    row = current(bot)
    assert row.status == "observing" and row.excluded_reason is None
    bot.cycle(decision + 120_001)
    row = current(bot)
    assert row.status == "excluded" and row.excluded_reason
    assert not v.writes


@pytest.mark.asyncio
async def test_async_cycle_uses_main_thread_created_state(runner, monkeypatch):
    bot, v = runner()
    original = type(bot).cycle
    monkeypatch.setattr(type(bot), "cycle", lambda self: original(self, NOW))
    result = await bot.run_once()
    assert result["states"]["entry_pending"] == 1


def test_live_durable_intent_protection_and_time_exit(runner):
    bot, v = runner()

    def before_entry():
        assert current(bot).status == "submitting"

    v.before_entry = before_entry
    bot.cycle(NOW)
    assert current(bot).status == "entry_pending"
    bot.cycle(NOW + 30000)
    assert current(bot).status == "open" and kinds(v) == {"stop", "target"}
    bot.cycle(NOW + 504 * HOUR_MS)
    assert current(bot).status == "closing"
    bot.cycle(NOW + 504 * HOUR_MS + 30000)
    assert current(bot).status == "closed" and not v.open_orders
    assert [w[0] for w in v.writes] == ["entry", "stop", "target", "close"]


def test_accepted_entry_timeout_recovers_once(runner):
    bot, v = runner()
    v.entry_timeout = True
    bot.cycle(NOW)
    assert current(bot).status == "uncertain"
    bot.cycle(NOW + 30000)
    assert current(bot).status == "open" and len([w for w in v.writes if w[0] == "entry"]) == 1


def test_unknown_entry_never_retried_after_restart(runner):
    bot, v = runner()
    v.entry_timeout = True
    v.accept_entry = False
    bot.cycle(NOW)
    path = bot.strategy_params.state_path
    bot.__exit__()
    resumed, _ = runner(venue=v, path=path)
    resumed.cycle(NOW + 30000)
    resumed.cycle(NOW + 60000)
    assert current(resumed).status == "uncertain" and len(v.writes) == 1


def test_protection_failure_keeps_bootstrap_then_replaces_attempt(runner):
    bot, v = runner()
    bot.cycle(NOW)
    v.protect_timeout = True
    bot.cycle(NOW + 30000)
    row = current(bot)
    assert row.status == "uncertain" and row.phase == "protection"
    assert "bootstrap" in kinds(v)  # never cancelled before a replacement is acknowledged
    v.protect_timeout = False
    bot.cycle(NOW + 60000)
    row = current(bot)
    assert row.status == "open" and kinds(v) == {"stop", "target"}
    assert {o["clientOrderId"] for o in v.open_orders} == {
        row.stop_client_id,
        row.target_client_id,
    }
    bot.cycle(NOW + 504 * HOUR_MS)
    assert v.writes[-1][0] == "close"


def test_protection_uncertainty_does_not_block_new_entries(runner):
    bot, v = runner()
    bot.cycle(NOW)
    v.protect_timeout = True
    bot.cycle(NOW + 30000)
    assert current(bot).status == "uncertain"
    v.add("NEW2/USDT:USDT", L + HOUR_MS)
    bot.cycle(NOW + HOUR_MS)
    assert ("entry", "NEW2/USDT:USDT") in {w[:2] for w in v.writes}


def test_position_is_adopted_after_state_loss(runner, tmp_path):
    bot, v = runner()
    bot.cycle(NOW)
    bot.cycle(NOW + 30000)
    bot.__exit__()
    fresh, _ = runner(venue=v, path=tmp_path / "lost.sqlite")
    fresh.cycle(NOW + 60000)  # discovers the listing; the owned symbol is never re-entered
    fresh.cycle(NOW + 90000)  # adopts the short from its deterministic entry order
    row = current(fresh)
    assert row.status == "open" and row.deadline_ms == NOW + 504 * HOUR_MS
    assert kinds(v) == {"stop", "target"}
    fresh.cycle(NOW + 504 * HOUR_MS)
    assert v.writes[-1][0] == "close"
    assert len([w for w in v.writes if w[0] == "entry"]) == 1


def test_ambiguous_close_is_replaced_by_a_fresh_reduce_only_close(runner):
    bot, v = runner()
    bot.cycle(NOW)
    bot.cycle(NOW + 30000)
    v.close_timeout = True
    v.accept_close = False
    bot.cycle(NOW + 504 * HOUR_MS)
    assert current(bot).phase == "close"
    v.close_timeout = False
    v.accept_close = True
    bot.cycle(NOW + 505 * HOUR_MS)
    closes = [w for w in v.writes if w[0] == "close"]
    assert len(closes) == 2 and closes[0][2] != closes[1][2]
    bot.cycle(NOW + 505 * HOUR_MS + 30000)
    assert current(bot).status == "closed" and not v.open_orders


def test_working_close_is_not_duplicated(runner):
    bot, v = runner()
    bot.cycle(NOW)
    bot.cycle(NOW + 30000)
    v.accept_close = False
    v.close_rests = True
    bot.cycle(NOW + 504 * HOUR_MS)
    bot.cycle(NOW + 505 * HOUR_MS)
    assert current(bot).status == "closing"
    assert len([w for w in v.writes if w[0] == "close"]) == 1


def test_margin_failure_never_enters(runner):
    bot, v = runner()
    v.reject_prepare = True
    bot.cycle(NOW)
    assert current(bot).status == "skipped" and not v.writes


def test_client_ids_stable_distinct_lowercase():
    a, b = (
        Listing(key="key", symbol=SYMBOL, listing_ms=L),
        Listing(key="key", symbol=SYMBOL, listing_ms=L),
    )
    assert a.order_id_for("e") == b.order_id_for("e") != a.order_id_for("c")
    assert len(a.order_id_for("e")) <= 40
    assert a.order_id_for("e").isalnum() and a.order_id_for("e").islower()


def test_unknown_listing_field_is_rejected(runner):
    bot, _ = runner()
    listing = bot._state.rows()[0]
    with pytest.raises(ValidationError, match="no attribute"):
        bot._state.save(listing, NOW, not_a_field=1)
    with pytest.raises(ValidationError):
        bot._state.save(listing, NOW, status="not_a_status")


def test_cancelled_partial_fill_gets_protection_for_actual_quantity(runner):
    bot, v = runner()
    bot.cycle(NOW)
    order = v.orders[current(bot).client_id]
    order["status"] = "canceled"
    order["filled"] /= 2
    v.positions[0]["contracts"] /= 2
    v.positions[0]["notional"] /= 2
    bot.cycle(NOW + 30000)
    assert current(bot).status == "open"
    assert current(bot).amount == order["filled"]


def test_bootstrap_stop_can_close_before_first_reconciliation(runner):
    bot, v = runner()
    bot.cycle(NOW)
    v.positions = []
    bot.cycle(NOW + 30000)
    assert current(bot).status == "closed"
    assert [w[0] for w in v.writes] == ["entry"]
    assert not v.open_orders


def test_missing_protection_is_restored_and_deadline_kept(runner):
    bot, v = runner()
    bot.cycle(NOW)
    bot.cycle(NOW + 30000)
    v.open_orders = [o for o in v.open_orders if not o["id"].startswith("target")]
    bot.cycle(NOW + 60000)
    assert current(bot).status == "open" and kinds(v) == {"stop", "target"}
    assert len(v.open_orders) == 2  # the orphaned stop of the first attempt is cancelled
    assert len([w for w in v.writes if w[0] == "stop"]) == 2
    bot.cycle(NOW + 504 * HOUR_MS)
    assert v.writes[-1][0] == "close"


def test_market_discovery_failure_does_not_postpone_known_deadline(runner, monkeypatch):
    bot, v = runner()
    bot.cycle(NOW)
    bot.cycle(NOW + 30000)
    monkeypatch.setattr(FakeBingX, "markets", Mock(side_effect=ccxt.NetworkError("catalog down")))
    with pytest.raises(ccxt.NetworkError):
        bot.cycle(NOW + 504 * HOUR_MS)
    assert v.writes[-1][0] == "close"
    assert current(bot).status == "closing"


@pytest.mark.parametrize(
    "symbol,status", [("OTHER/USDT:USDT", "entry_pending"), (SYMBOL, "skipped")]
)
def test_leftover_order_blocks_only_its_own_symbol(runner, symbol, status):
    bot, v = runner()
    v.open_orders.append({"id": "leftover", "symbol": symbol})
    bot.cycle(NOW)
    assert current(bot).status == status


def test_live_deadline_survives_restart(runner):
    bot, v = runner()
    bot.cycle(NOW)
    bot.cycle(NOW + 30000)
    path = bot.strategy_params.state_path
    bot.__exit__()
    resumed, _ = runner(venue=v, path=path)
    resumed.cycle(NOW + 504 * HOUR_MS)
    assert v.writes[-1][0] == "close"
    assert len([w for w in v.writes if w[0] == "entry"]) == 1


def test_increased_market_latency_expires_entry_before_post(runner, monkeypatch):
    bot, v = runner()
    from otomai.strategies.listing_volume_short import execution

    monkeypatch.setattr(execution.time, "time", lambda: (NOW + 121000) / 1000)
    bot.cycle(NOW)
    assert current(bot).status == "skipped"
    assert not v.writes


def test_unknown_notional_blocks_admission_but_not_existing_exit(runner):
    bot, v = runner()
    bot.cycle(NOW)
    bot.cycle(NOW + 30000)
    v.positions[0]["notional"] = None
    bot.cycle(NOW + 504 * HOUR_MS)
    assert v.writes[-1][0] == "close"


def test_stale_symbol_orders_are_cancelled_once_protected(runner):
    bot, v = runner()
    bot.cycle(NOW)
    v.open_orders.append({"id": "stale", "symbol": SYMBOL, "side": "buy", "type": "limit"})
    bot.cycle(NOW + 30000)
    assert current(bot).status == "open" and kinds(v) == {"stop", "target"}


def test_partial_bootstrap_stop_protects_only_remaining_position(runner):
    bot, v = runner()
    bot.cycle(NOW)
    original_amount = v.positions[0]["contracts"]
    v.positions[0]["contracts"] /= 2
    v.positions[0]["notional"] /= 2
    bot.cycle(NOW + 30000)
    assert current(bot).status == "open"
    assert current(bot).amount == original_amount  # confirmed fill
    assert {o["amount"] for o in v.open_orders} == {original_amount / 2}  # protects the remainder


def test_checked_in_yaml_uses_the_live_state_file():
    root = Path(__file__).parents[2]
    for env in ["dev", "prod"]:
        s = MainSettings.model_validate(
            configs.to_object(
                configs.parse_file(str(root / "conf" / env / "listing_volume_short.yml"))
            )
        ).strategy
        assert s.strategy_params.state_path.endswith("listing_volume_short.live.sqlite")


def test_entry_waits_for_four_closed_candles_and_uses_current_quote(runner):
    decision = L + 4 * HOUR_MS
    bot, venue = runner()
    venue.bid, venue.ask = 87.0, 87.1
    bot.cycle(decision - 1)
    assert current(bot).status == "observing"
    bot.cycle(decision)
    row = current(bot)
    assert row.status == "entry_pending"
    assert row.submitted_ms >= decision
    assert row.quote == 87  # the last decision candle's close is not an executable fill
    assert [w[0] for w in venue.writes] == ["entry"]


def test_entry_rejects_entry_that_expires_during_requests(runner, monkeypatch):
    from otomai.strategies.listing_volume_short import execution

    decision = L + 4 * HOUR_MS
    bot, venue = runner()
    monkeypatch.setattr(execution.time, "time", lambda: (decision + 121000) / 1000)
    bot.cycle(decision)
    assert current(bot).status == "skipped"
    assert not venue.writes


def test_entry_deadline_uses_actual_fill_time(runner, monkeypatch):
    from otomai.strategies.listing_volume_short import execution

    decision = L + 4 * HOUR_MS
    bot, v = runner()
    monkeypatch.setattr(execution.time, "time", lambda: (decision + 15000) / 1000)
    bot.cycle(decision)
    assert current(bot).submitted_ms == decision + 15000
    bot.cycle(decision + 30000)
    fill = v.orders[current(bot).client_id]["timestamp"]
    assert current(bot).deadline_ms == fill + 504 * HOUR_MS


@pytest.mark.parametrize("offset,expected", [(120000, "entry_pending"), (120001, "expired")])
def test_entry_grace_boundary(runner, offset, expected):
    bot, _ = runner()
    bot.cycle(L + 4 * HOUR_MS + offset)
    assert current(bot).status == expected


def test_rule_change_does_not_silently_reuse_an_old_open_portfolio(runner):
    bot, venue = runner()
    bot.cycle(NOW)
    path = bot.strategy_params.state_path
    assert current(bot).status == "entry_pending"
    bot.__exit__()
    with pytest.raises(RuntimeError, match="different account or rule"):
        runner(volume_multiplier=3.0, venue=venue, path=path)
    resumed, _ = runner(venue=venue, path=path)
    assert current(resumed).status == "entry_pending"


def test_config_preflight_does_not_initialize_state_or_exchange(monkeypatch):
    from otomai import scripts

    root = Path(__file__).parents[2]
    enter = Mock(side_effect=AssertionError("Must not initialize state during config preflight"))
    monkeypatch.setattr(ListingVolumeShortStrategy, "_ensure_state", enter)
    monkeypatch.setattr(scripts.configs, "load_env", lambda: None)
    scripts.main(["--files", str(root / "conf/prod/listing_volume_short.yml"), "--check-config"])
    enter.assert_not_called()
