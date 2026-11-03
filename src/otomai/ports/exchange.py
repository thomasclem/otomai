"""Exchange port: everything strategies and services may ask of a derivatives venue.

Implementations return the normalized records of `core.models`, never vendor payloads.
"""

import abc

import pandas as pd
import pydantic as pdt

from otomai.core.enums import OrderSide, TradeSide
from otomai.core.models import (
    ClosedPosition,
    ExchangeFill,
    ExchangeOrder,
    ExchangePosition,
    Market,
    OrderBook,
)


class Exchange(abc.ABC, pdt.BaseModel):
    KIND: str

    # %% ACCOUNT

    @abc.abstractmethod
    def require_live_credentials(self) -> None:
        """Raise unless private (trading) endpoints can be used."""

    @abc.abstractmethod
    def account_fingerprint(self) -> str:
        """Stable, non-secret identifier of the configured account."""

    @abc.abstractmethod
    def balance(self) -> tuple[float, float]:
        """(equity including unrealised P&L, available margin) in USDT."""

    @abc.abstractmethod
    def positions(self, symbols: list[str] | None = None) -> list[ExchangePosition]: ...

    def position(self, symbol: str, side: str | None = None) -> ExchangePosition | None:
        matches = [
            p
            for p in self.positions([symbol])
            if p["symbol"] == symbol and (side is None or p["side"] == side)
        ]
        if len(matches) > 1:
            raise ValueError("Multiple position sides; specify the owned side")
        return matches[0] if matches else None

    @abc.abstractmethod
    def position_history(
        self, symbols: list[str] | None = None, since: int | None = None
    ) -> list[ClosedPosition]: ...

    @abc.abstractmethod
    def fills(self, symbol: str, since: int) -> list[ExchangeFill]: ...

    # %% MARKET DATA

    @abc.abstractmethod
    def markets(self) -> dict[str, Market]: ...

    @abc.abstractmethod
    def candles(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        until: int | None = None,
        limit: int | None = None,
    ) -> list[list]:
        """Raw [timestamp_ms, open, high, low, close, volume] rows, oldest first."""

    @abc.abstractmethod
    def fetch_ohlcv_df(self, symbol: str, timeframe: str, window: int) -> pd.DataFrame: ...

    @abc.abstractmethod
    async def fetch_all_symbols_ohlcv_df(
        self, timeframe: str = "1h", ohlcv_window: int = 20
    ) -> pd.DataFrame: ...

    @abc.abstractmethod
    def ticker_price(self, symbol: str) -> float: ...

    @abc.abstractmethod
    def order_book(self, symbol: str, depth: int = 50) -> OrderBook: ...

    # %% ORDERS

    @abc.abstractmethod
    def order_amount(self, symbol: str, notional: float, price: float) -> tuple[float, float]:
        """(quantity rounded down to venue precision, its notional); raises outside limits."""

    @abc.abstractmethod
    def set_margin_mode_and_leverage(
        self, symbol: str, margin_mode: str, leverage: int
    ) -> None: ...

    @abc.abstractmethod
    def create_order(
        self,
        symbol: str,
        side: OrderSide,
        amount: float,
        type: str,
        trade_side: TradeSide,
        margin_mode: str,
        price: float | None = None,
        reduce: bool = False,
        take_profit_price: float | None = None,
        stop_loss_price: float | None = None,
        client_id: str | None = None,
    ) -> ExchangeOrder: ...

    @abc.abstractmethod
    def create_stop_order(
        self,
        symbol: str,
        side: OrderSide,
        amount: float,
        trigger_price: float,
        client_id: str | None = None,
    ) -> ExchangeOrder:
        """Reduce-only stop-market order triggered at `trigger_price`."""

    @abc.abstractmethod
    def open_orders(self, symbol: str | None = None) -> list[ExchangeOrder]: ...

    @abc.abstractmethod
    def order_by_client_id(self, symbol: str, client_id: str) -> ExchangeOrder:
        """Raise ccxt.OrderNotFound when the venue has no such order."""

    @abc.abstractmethod
    def cancel(self, symbol: str, order_id: str) -> None:
        """Cancel an order; an already-gone order is not an error."""
