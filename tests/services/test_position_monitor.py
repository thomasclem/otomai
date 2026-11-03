"""Lifecycle regressions: zero PnL, partial fills, duplicate fills, concurrent symbols."""

import asyncio
from types import SimpleNamespace

import pydantic as pdt
import pytest

from otomai.adapters import BingXExchange
from otomai.core.exceptions import PositionTimeoutError
from otomai.core.models import Trades
from otomai.ports import Database, Notifier
from otomai.services.position_monitor import PositionMonitor

BASE = 1_700_000_000_000
DATE = "2023-11-14T22:13:20+00:00"
SYMBOL = "NEW/USDT:USDT"


class MemoryDatabase(Database):
    KIND: str = "Memory"
    rows: list = pdt.Field(default_factory=list)

    def insert_trade(self, trade):
        self.rows.append(trade)

    def fetch_all_trades(self):
        return Trades(trades=self.rows)


class RecordingNotifier(Notifier):
    KIND: str = "Recording"
    messages: list = pdt.Field(default_factory=list)

    async def send_message(self, message):
        self.messages.append(message)

    async def send_image(self, image, caption):
        pass


class MonitorExchange(BingXExchange):
    def position(self, symbol, side=None):
        self._session.position_calls += 1
        queue = self._session.positions[symbol]
        return queue.pop(0) if queue else None

    def fills(self, symbol, since):
        queue = self._session.fills[symbol]
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def position_history(self, symbols=None, since=None):
        return self._session.history


def position(symbol=SYMBOL, entry=100.0, amount=2.0):
    return {
        "id": symbol,
        "symbol": symbol,
        "side": "long",
        "contracts": amount,
        "entryPrice": entry,
        "markPrice": entry,
        "notional": entry * amount,
        "unrealizedPnl": 0,
        "percentage": 0,
        "timestamp": BASE,
    }


def fill(id, price, amount=1.0, stamp=10, symbol=SYMBOL):
    return {
        "id": id,
        "order": "close",
        "symbol": symbol,
        "side": "sell",
        "amount": amount,
        "price": price,
        "timestamp": BASE + stamp,
        "is_close": True,
        "realized_pnl": 0.0,
    }


def monitor(positions, fills, history):
    x = MonitorExchange()
    x._session = SimpleNamespace(
        positions=positions, fills=fills, history=history, position_calls=0
    )
    db = MemoryDatabase()
    notifier = RecordingNotifier()
    return (
        PositionMonitor(
            exchange_service=x, notifier_service=notifier, database_service=db, strategy_name="test"
        ),
        db,
        x,
    )


@pytest.fixture(autouse=True)
def immediate_poll(monkeypatch):
    import otomai.services.position_monitor as module

    monkeypatch.setattr(module, "POSITION_CLOSING_CHECK_INTERVAL", 0)
    monkeypatch.setattr(module, "POSITION_OPENING_CHECK_INTERVAL", 0)


@pytest.mark.asyncio
async def test_zero_profit_partial_fills_wait_for_flat_and_are_deduplicated():
    f1, f2 = fill("1", 101), fill("2", 103, stamp=20)
    before = fill("old", 999, stamp=-1)
    other = fill("other", 999, symbol="OTHER/USDT:USDT")
    history = [
        {
            "id": SYMBOL,
            "symbol": SYMBOL,
            "side": "long",
            "timestamp": BASE,
            "closedTimestamp": BASE + 30,
            "netPnl": 0.0,
        }
    ]
    m, db, x = monitor(
        {SYMBOL: [position(amount=1), None]},
        {SYMBOL: [[f1, f1, before, other], [f1, f2, f2]]},
        history,
    )
    await m.monitor_position_closing(
        SYMBOL, DATE, "long", max_timeout=10, open_price=100, expected_amount=2, position_id=SYMBOL
    )
    assert x._session.position_calls == 2
    assert len(db.rows) == 1 and float(db.rows[0].amount) == 2
    assert float(db.rows[0].close_price) == 102 and float(db.rows[0].net_profit) == 0


@pytest.mark.asyncio
async def test_unknown_net_profit_is_not_reported_as_realised_gross_profit():
    m, db, _ = monitor({SYMBOL: [None]}, {SYMBOL: [[fill("1", 110, amount=2)]]}, [])
    await m.monitor_position_closing(
        SYMBOL, DATE, "long", max_timeout=10, open_price=100, expected_amount=2
    )
    assert len(db.rows) == 1 and db.rows[0].net_profit is None
    assert "not yet confirmed" in m.notifier_service.messages[-1]


@pytest.mark.asyncio
async def test_full_fill_does_not_prove_flat_position():
    m, db, x = monitor(
        {SYMBOL: [position(amount=1), None]}, {SYMBOL: [[fill("1", 110, amount=2)]]}, []
    )
    await m.monitor_position_closing(
        SYMBOL, DATE, "long", max_timeout=10, open_price=100, expected_amount=2
    )
    assert x._session.position_calls == 2 and len(db.rows) == 1


@pytest.mark.asyncio
async def test_shared_monitor_keeps_each_symbols_open_price_and_size_local():
    other = "OTHER/USDT:USDT"
    m, db, _ = monitor(
        {
            SYMBOL: [position(entry=100, amount=1), None],
            other: [position(symbol=other, entry=200, amount=2), None],
        },
        {SYMBOL: [[fill("a", 110, amount=1)]], other: [[fill("b", 190, amount=2, symbol=other)]]},
        [],
    )
    await asyncio.gather(m.monitor_position(SYMBOL, DATE), m.monitor_position(other, DATE))
    result = {t.symbol: t for t in db.rows}
    assert float(result[SYMBOL].open_price) == 100 and float(result[SYMBOL].amount) == 1
    assert float(result[other].open_price) == 200 and float(result[other].amount) == 2


@pytest.mark.asyncio
async def test_opening_timeout_is_explicit():
    m, db, _ = monitor({SYMBOL: [None]}, {SYMBOL: [[]]}, [])
    with pytest.raises(PositionTimeoutError):
        await m.monitor_position_opening(SYMBOL, order_timeout=0)
    assert not db.rows
