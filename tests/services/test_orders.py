"""Order placement through the exchange port, tested on the Bitget adapter's request formats."""

from unittest.mock import Mock

import ccxt
import pytest

from otomai.adapters import BitgetExchange
from otomai.core.enums import OrderSide
from otomai.core.parameters import TradingParams
from otomai.services.orders import close_position, open_position

SYMBOL = "NEW/USDT:USDT"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(
        ccxt.Exchange, "fetch", Mock(side_effect=AssertionError("Network forbidden"))
    )


def bitget(balance=None):
    x = BitgetExchange()
    s = Mock()
    s.check_required_credentials.return_value = True
    s.fetch_ticker.return_value = {"last": 20}
    s.fetch_balance.return_value = balance or {"USDT": {"total": 10000, "free": 10000}, "info": []}
    s.market.return_value = {"contractSize": 1, "limits": {}}
    s.amount_to_precision.side_effect = lambda symbol, amount: str(amount)
    s.create_order.return_value = {"id": "o", "symbol": SYMBOL}
    x._session = s
    return x, s


@pytest.mark.parametrize("error", [ccxt.RequestTimeout("lost"), ccxt.ExchangeError("rejected")])
def test_margin_or_leverage_failure_blocks_entry(error):
    x, s = bitget()
    s.set_margin_mode.side_effect = error
    with pytest.raises(type(error)):
        open_position(x, SYMBOL, OrderSide.SELL, TradingParams(equity_trade_pct=5))
    s.create_order.assert_not_called()


def test_ambiguous_order_submission_is_not_retried():
    x, s = bitget()
    s.create_order.side_effect = ccxt.RequestTimeout("accepted but ack lost")
    with pytest.raises(ccxt.RequestTimeout):
        open_position(x, SYMBOL, OrderSide.SELL, TradingParams(equity_trade_pct=5, max_retries=3))
    assert s.create_order.call_count == 1
    assert s.create_order.call_args.kwargs["params"]["clientOrderId"]


def test_explicit_margin_rejection_retries_smaller_with_the_same_client_id():
    x, s = bitget()
    s.create_order.side_effect = [ccxt.InsufficientFunds("too big"), {"id": "o", "symbol": SYMBOL}]
    params = TradingParams(equity_trade_pct=10, max_retries=2, safety_margin=0.1)
    open_position(x, SYMBOL, OrderSide.SELL, params)
    first, second = s.create_order.call_args_list
    assert second.kwargs["amount"] == pytest.approx(first.kwargs["amount"] * 0.9)
    assert first.kwargs["params"]["clientOrderId"] == second.kwargs["params"]["clientOrderId"]


@pytest.mark.parametrize("basis,expected", [("available", 4), ("equity", 5)])
def test_allocation_base_is_explicit(basis, expected):
    x, s = bitget({"USDT": {"total": 1000, "free": 800}, "info": []})
    open_position(x, SYMBOL, OrderSide.SELL, TradingParams(equity_trade_pct=10, sizing_basis=basis))
    assert s.create_order.call_args.kwargs["amount"] == pytest.approx(expected)


def test_close_position_is_reduce_only_and_noop_when_flat():
    x, s = bitget()
    s.fetch_positions.return_value = []
    assert close_position(x, SYMBOL, "market", "isolated") == {}
    s.fetch_positions.return_value = [
        {"symbol": SYMBOL, "contracts": 3, "side": "long", "info": {}}
    ]
    close_position(x, SYMBOL, "market", "isolated")
    assert s.create_order.call_args.kwargs["side"] == "sell"
    assert s.create_order.call_args.kwargs["params"]["reduceOnly"] is True
