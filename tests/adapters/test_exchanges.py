"""Adapter contracts use representative Bitget/BingX formats, never real APIs."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import ccxt
import pytest

from otomai.adapters import BingXExchange, BitgetExchange
from otomai.core.enums import OrderSide, TradeSide
from otomai.core.exceptions import InsufficientFunds, OrderNotFound
from otomai.ports import Exchange

SYMBOL = "NEW/USDT:USDT"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(
        ccxt.Exchange, "fetch", Mock(side_effect=AssertionError("Network forbidden"))
    )
    for key in [
        "BITGET_API_KEY",
        "BITGET_SECRET",
        "BITGET_PASSWORD",
        "BINGX_API_KEY",
        "BINGX_SECRET",
    ]:
        monkeypatch.delenv(key, raising=False)


def session_for(exchange):
    session = Mock()
    session.check_required_credentials.return_value = True
    session.has = {"fetchPositionsHistory": True}
    exchange._session = session
    return session


@pytest.mark.parametrize("kind", [BitgetExchange, BingXExchange])
def test_lazy_public_session_without_credentials(kind, monkeypatch):
    for k in [
        "BITGET_API_KEY",
        "BITGET_SECRET",
        "BITGET_PASSWORD",
        "BINGX_API_KEY",
        "BINGX_SECRET",
    ]:
        monkeypatch.delenv(k, raising=False)
    client = kind()
    assert client._session is None
    with pytest.raises(ccxt.AuthenticationError):
        client.require_live_credentials()
    assert client._session is not None


def test_exchange_specific_required_credentials():
    with pytest.raises(ccxt.AuthenticationError):
        BitgetExchange(apiKey="test", secret="test").require_live_credentials()
    BingXExchange(apiKey="test", secret="test").require_live_credentials()  # no passphrase
    bitget = BitgetExchange(apiKey="test", secret="test", password="test")
    bitget.require_live_credentials()
    assert "apiKey" not in bitget.model_dump() and "test" not in repr(bitget)


def test_bitget_equity_and_available_are_distinct_from_withdrawable_cash():
    client = BitgetExchange()
    s = session_for(client)
    s.fetch_balance.return_value = {
        "USDT": {"total": 100, "free": 90},
        "info": [
            {
                "marginCoin": "USDT",
                "accountEquity": "125",
                "available": "110",
                "maxTransferOut": "90",
            }
        ],
    }
    assert client.balance() == (125, 110)


def test_bingx_equity_is_not_reconstructed_free_plus_used():
    client = BingXExchange()
    s = session_for(client)
    s.fetch_balance.return_value = {
        "USDT": {"total": 100, "free": 90},
        "info": {"data": [{"asset": "USDT", "equity": "125"}]},
    }
    assert client.balance() == (125, 90)


@pytest.mark.parametrize("kind", [BitgetExchange, BingXExchange])
def test_positions_drop_empty_slots_and_normalize_signed_contracts(kind):
    client = kind()
    s = session_for(client)
    s.fetch_positions.return_value = [
        {"symbol": SYMBOL, "contracts": 0, "side": None},
        {
            "id": "p",
            "symbol": SYMBOL,
            "contracts": -3,
            "side": "short",
            "entryPrice": "99",
            "markPrice": "100",
            "contractSize": 1,
            "notional": None,
            "unrealizedPnl": "0",
            "percentage": "0",
            "timestamp": 1,
            "info": {"vendor": "hidden"},
        },
    ]
    rows = client.positions()
    assert len(rows) == 1
    assert rows[0]["contracts"] == 3 and rows[0]["notional"] == 300
    assert rows[0]["unrealizedPnl"] == 0 and "info" not in rows[0]


def test_bitget_missing_unified_position_fields_are_repaired_by_wrapper():
    x = BitgetExchange()
    s = session_for(x)
    s.fetch_positions.return_value = [
        {
            "symbol": SYMBOL,
            "contracts": None,
            "markPrice": 100,
            "info": {"total": "3", "holdSide": "short", "openPriceAvg": "99"},
        }
    ]
    p = x.positions()[0]
    assert p["contracts"] == 3 and p["entryPrice"] == 99 and p["side"] == "short"


def test_identical_zero_profit_closing_fill_contract_across_venues():
    base = {
        "id": "f",
        "order": "o",
        "symbol": SYMBOL,
        "amount": "2",
        "price": "105",
        "timestamp": 1234,
    }
    a = BitgetExchange().normalize_fill(
        {
            **base,
            "side": "buy",
            "info": {"tradeSide": "close", "posMode": "hedge_mode", "profit": "0"},
        }
    )
    b = BingXExchange().normalize_fill(
        {**base, "side": "sell", "info": {"positionSide": "LONG", "realizedProfit": "0"}}
    )
    assert a == b
    assert a["side"] == "sell" and a["is_close"] is True and a["realized_pnl"] == 0
    assert "info" not in a


def test_unconfirmed_realized_profit_is_unknown_not_zero():
    f = BingXExchange().normalize_fill(
        {"id": "x", "symbol": SYMBOL, "side": "buy", "amount": 1, "price": 100, "timestamp": 1234}
    )
    assert f["realized_pnl"] is None and f["is_close"] is None


def test_order_booleans_and_client_ids_are_canonical():
    a = BitgetExchange().normalize_order(
        {
            "id": 1,
            "symbol": SYMBOL,
            "side": "sell",
            "type": "STOP_MARKET",
            "info": {
                "clientOid": "client",
                "reduceOnly": "YES",
                "triggerPrice": "120",
                "cTime": "1234",
            },
        }
    )
    b = BingXExchange().normalize_order(
        {
            "id": 1,
            "symbol": SYMBOL,
            "side": "sell",
            "type": "STOP_MARKET",
            "info": {
                "clientOrderID": "client",
                "reduceOnly": "true",
                "stopPrice": "120",
                "time": "1234",
            },
        }
    )
    assert a == b and a["reduceOnly"] is True and a["timestamp"] == 1234


@pytest.mark.parametrize(
    "kind,raw",
    [
        (BitgetExchange, {"ctime": "100", "utime": "200", "netProfit": "0"}),
        (BingXExchange, {"openTime": "100", "updateTime": "200", "netProfit": "0"}),
    ],
)
def test_reported_net_zero_is_preserved(kind, raw):
    x = kind()
    s = session_for(x)
    s.fetch_positions_history.return_value = [
        {"id": "p", "symbol": SYMBOL, "side": "long", "info": raw}
    ]
    result = x.position_history([SYMBOL], 100)[0]
    assert result["timestamp"] == 100 and result["closedTimestamp"] == 200 and result["netPnl"] == 0


def test_bitget_last_price_fallback_stays_inside_wrapper():
    x = BitgetExchange()
    s = session_for(x)
    s.fetch_ticker.return_value = {"last": None, "info": {"lastPr": "123"}}
    assert x.ticker_price(SYMBOL) == 123


def test_already_set_margin_is_the_only_ignored_setup_error():
    x = BitgetExchange()
    s = session_for(x)
    s.set_margin_mode.side_effect = ccxt.MarginModeAlreadySet("same")
    x.set_margin_mode_and_leverage(SYMBOL, "isolated", 1)
    assert s.set_leverage.call_count == 2
    assert {c.kwargs["params"]["holdSide"] for c in s.set_leverage.call_args_list} == {
        "long",
        "short",
    }


def test_real_ccxt_bitget_hedge_close_mapping():
    client = ccxt.bitget({"options": {"defaultType": "swap"}})
    client.set_markets(
        [
            {
                "id": "NEWUSDT",
                "symbol": SYMBOL,
                "base": "NEW",
                "baseId": "NEW",
                "quote": "USDT",
                "quoteId": "USDT",
                "settle": "USDT",
                "settleId": "USDT",
                "type": "swap",
                "swap": True,
                "spot": False,
                "contract": True,
                "linear": True,
                "inverse": False,
                "contractSize": 1,
                "precision": {"amount": 0.001, "price": 0.001},
                "limits": {},
                "active": True,
            }
        ]
    )
    wrapper = BitgetExchange()
    params = wrapper.order_params(SYMBOL, OrderSide.SELL, TradeSide.CLOSE, "isolated", True)
    assert "tradeSide" not in params
    request = client.create_order_request(SYMBOL, "market", "sell", 3, None, params)
    # Logical sell closes a long. Bitget hedge API encodes the held direction instead.
    assert request["side"] == "buy" and request["tradeSide"].lower() == "close"
    assert request["productType"] == "USDT-FUTURES"


def test_bitget_includes_all_plan_order_streams_and_deduplicates():
    x = BitgetExchange()
    s = session_for(x)
    regular = {"id": "1", "symbol": SYMBOL, "side": "sell"}
    stop = {"id": "2", "symbol": SYMBOL, "side": "buy", "info": {"planType": "pos_loss"}}
    s.fetch_open_orders.side_effect = [[regular], [regular], [stop], []]
    rows = x.open_orders(SYMBOL)
    assert len(rows) == 2 and rows[1]["reduceOnly"] is True
    assert s.fetch_open_orders.call_count == 4
    assert [
        c.kwargs.get("params", {}).get("planType") for c in s.fetch_open_orders.call_args_list
    ] == [None, "normal_plan", "profit_loss", "track_plan"]


def test_telegram_construction_is_lazy_and_preserves_injected_bot(monkeypatch):
    from otomai.adapters.notifiers import TelegramNotifier

    monkeypatch.delenv("TELEGRAM_API_KEY", raising=False)
    assert TelegramNotifier().bot is None
    bot = Mock()
    notifier = TelegramNotifier(bot=bot)
    assert notifier._get_bot() is bot
    assert "bot" not in notifier.model_dump()


def test_adapters_implement_the_exchange_port():
    assert issubclass(BitgetExchange, Exchange) and issubclass(BingXExchange, Exchange)
    BitgetExchange(), BingXExchange()  # no abstract method left unimplemented


def test_missing_actual_equity_never_falls_back_to_wallet_total():
    x = BingXExchange()
    x._session = SimpleNamespace(
        check_required_credentials=lambda: None,
        fetch_balance=lambda: {"USDT": {"total": 10000, "free": 10000}},
    )
    with pytest.raises(ValueError, match="raw USDT equity unavailable"):
        x.balance()


@pytest.mark.parametrize(
    "base,tradfi",
    [
        ("NCSKAAPU2USD", True),
        ("NCSKAXONUSDT", True),
        ("NCCOHEATINGOIL2USD", True),
        ("NCFXEURSGD2USD", True),
        ("NCSIDXY2USD", True),
        ("NCSKSOFTBANK2JPY", True),
        ("NCXXFUTURE2USD", True),
        ("NC", False),
        ("NCT", False),
        ("NCDT", False),
        ("PNUT", False),
    ],
)
def test_bingx_tradfi_market_classification(base, tradfi):
    assert BingXExchange().normalize_market({"base": base})["tradfi"] is tradfi


def test_bingx_launch_time_requires_milliseconds():
    x = BingXExchange()
    assert (
        x.normalize_market({"info": {"launchTime": "1700000000000"}})["launchTime"] == 1700000000000
    )
    assert x.normalize_market({"info": {"launchTime": 1700000000}})["launchTime"] is None
    assert BitgetExchange().normalize_market({"launchTime": None})["tradfi"] is False


def test_candles_pass_the_window_end_as_until():
    x = BingXExchange()
    s = session_for(x)
    x.candles(SYMBOL, "1h", since=1000, until=5000, limit=28)
    s.fetch_ohlcv.assert_called_once_with(
        SYMBOL, "1h", since=1000, limit=28, params={"until": 5000}
    )


def test_order_book_is_normalized_to_float_pairs():
    x = BingXExchange()
    s = session_for(x)
    s.fetch_order_book.return_value = {"bids": [["100", "2", 0]], "asks": [[100.1, 3]], "info": {}}
    assert x.order_book(SYMBOL) == {"bids": [(100.0, 2.0)], "asks": [(100.1, 3.0)]}


def test_order_amount_rounds_down_inside_exchange_limits():
    x = BingXExchange()
    s = session_for(x)
    s.market.return_value = {
        "contractSize": 1,
        "limits": {"amount": {"min": 1}, "cost": {"min": 10}},
    }
    s.amount_to_precision.side_effect = lambda symbol, q: str(int(q))
    assert x.order_amount(SYMBOL, 599, 100) == (5, 500)
    with pytest.raises(ValueError):
        x.order_amount(SYMBOL, 99, 100)


def test_bingx_client_lookup_translates_not_found():
    x = BingXExchange()
    s = session_for(x)
    s.market.return_value = {"id": "NEW-USDT"}
    s.swapV2PrivateGetTradeOrder.return_value = {"data": {"order": {"orderId": "x"}}}
    s.parse_order.return_value = {"id": "x", "symbol": SYMBOL}
    x.order_by_client_id(SYMBOL, "custom")
    s.swapV2PrivateGetTradeOrder.assert_called_once_with(
        {"symbol": "NEW-USDT", "clientOrderId": "custom"}
    )
    s.swapV2PrivateGetTradeOrder.side_effect = ccxt.OrderNotFound("none")
    with pytest.raises(OrderNotFound):
        x.order_by_client_id(SYMBOL, "missing")


def test_margin_rejection_is_translated_for_the_services():
    x = BitgetExchange()
    s = session_for(x)
    s.create_order.side_effect = ccxt.InsufficientFunds("no margin")
    with pytest.raises(InsufficientFunds):
        x.create_order(SYMBOL, OrderSide.SELL, 1, "market", TradeSide.OPEN, "isolated")


def bingx_with_markets():
    client = ccxt.bingx({"apiKey": "k", "secret": "s", "options": {"defaultType": "swap"}})
    client.set_markets(
        [
            {
                "id": "NEW-USDT",
                "symbol": SYMBOL,
                "base": "NEW",
                "quote": "USDT",
                "settle": "USDT",
                "type": "swap",
                "swap": True,
                "spot": False,
                "contract": True,
                "linear": True,
                "inverse": False,
                "contractSize": 1.0,
                "precision": {"amount": 0.001, "price": 0.001},
                "limits": {"amount": {"min": 0.001}, "cost": {"min": 5}},
                "active": True,
            }
        ]
    )
    x = BingXExchange()
    x._session = client
    client.create_order = Mock(return_value={"id": "1", "symbol": SYMBOL})
    return x, client


def test_bingx_entry_carries_a_last_price_stop():
    x, client = bingx_with_markets()
    x.create_order(
        SYMBOL,
        OrderSide.SELL,
        5,
        "market",
        TradeSide.OPEN,
        "isolated",
        stop_loss_price=120,
        client_id="stable",
    )
    params = client.create_order.call_args.kwargs["params"]
    request = client.create_order_request(SYMBOL, "market", "sell", 5, None, params)
    stop = json.loads(request["stopLoss"])
    assert request["clientOrderID"] == "stable" and request["positionSide"] == "BOTH"
    assert stop["type"] == "STOP_MARKET" and stop["stopPrice"] == 120
    assert stop["workingType"] == "CONTRACT_PRICE"


def test_bingx_protection_and_close_are_reduce_only_buys():
    x, client = bingx_with_markets()
    x.create_stop_order(SYMBOL, OrderSide.BUY, 5, 126, client_id="s")
    x.create_order(
        SYMBOL,
        OrderSide.BUY,
        5,
        "limit",
        TradeSide.CLOSE,
        "isolated",
        price=42,
        reduce=True,
        client_id="t",
    )
    x.create_order(
        SYMBOL, OrderSide.BUY, 5, "market", TradeSide.CLOSE, "isolated", reduce=True, client_id="c"
    )
    stop, target, close = [c.kwargs for c in client.create_order.call_args_list]
    assert all(c["side"] == "buy" and c["params"]["reduceOnly"] for c in (stop, target, close))
    request = client.create_order_request(SYMBOL, "market", "buy", 5, None, stop["params"])
    assert request["type"] == "STOP_MARKET" and request["stopPrice"] == 126
    assert request["workingType"] == "CONTRACT_PRICE" and request["reduceOnly"]
    assert target["type"] == "limit" and target["price"] == 42
    assert close["type"] == "market"
