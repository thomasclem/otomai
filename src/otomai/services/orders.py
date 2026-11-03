"""Order placement shared by the single-order strategies."""

import uuid

from otomai.core import utils
from otomai.core.enums import OrderSide, TradeSide
from otomai.core.exceptions import InsufficientFunds
from otomai.core.models import ExchangeOrder
from otomai.core.parameters import TradingParams
from otomai.core.sizing import equity_amount
from otomai.ports import Exchange


def open_position(
    exchange: Exchange, symbol: str, side: OrderSide, params: TradingParams
) -> ExchangeOrder:
    """Open a position sized on equity, with attached take-profit and stop-loss.

    Only an explicit margin rejection allows another attempt, each one smaller by
    `safety_margin`. A timeout or any other error propagates: the order may have been
    accepted, and a second submission could double the position.
    """
    exchange.require_live_credentials()
    exchange.set_margin_mode_and_leverage(symbol, params.margin_mode, params.leverage)
    client_id = "ot" + uuid.uuid4().hex[:28]
    for attempt in range(params.max_retries):
        price = exchange.ticker_price(symbol)
        equity, free = exchange.balance()
        capital = free if params.sizing_basis == "available" else equity
        quantity = equity_amount(capital, params.equity_trade_pct, price)
        quantity *= 1 - params.safety_margin * attempt
        quantity, _ = exchange.order_amount(symbol, quantity * price, price)
        take_profit = (
            utils.calculate_take_profit_price(price, side, params.take_profit_pct, params.leverage)
            if params.take_profit_pct
            else None
        )
        stop_loss = (
            utils.calculate_stop_loss_price(price, side, params.stop_loss_pct, params.leverage)
            if params.stop_loss_pct
            else None
        )
        try:
            return exchange.create_order(
                symbol,
                side,
                quantity,
                params.order_type,
                TradeSide.OPEN,
                params.margin_mode,
                price if params.order_type == "limit" else None,
                take_profit_price=take_profit,
                stop_loss_price=stop_loss,
                client_id=client_id,
            )
        except InsufficientFunds:
            if attempt + 1 >= params.max_retries:
                raise
    raise RuntimeError("Order was not submitted")


def close_position(exchange: Exchange, symbol: str, order_type: str, margin_mode: str) -> dict:
    """Close the whole position on `symbol` with a reduce-only order; {} when flat."""
    position = exchange.position(symbol)
    if position is None:
        return {}
    return exchange.create_order(
        symbol,
        OrderSide.SELL if position["side"] == "long" else OrderSide.BUY,
        position["contracts"],
        order_type,
        TradeSide.CLOSE,
        margin_mode,
        reduce=True,
    )
