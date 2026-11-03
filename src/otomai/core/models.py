# %% IMPORTS

import typing as T
import uuid
from datetime import UTC, datetime

import pydantic as pdt
from sqlmodel import Field, SQLModel

# %% TRADES


class OptionalSQLModel(SQLModel):
    """
    Base model that makes all fields optional for partial updates/creation if needed.
    """

    pass


class Trade(OptionalSQLModel, table=True):
    id: str | None = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    symbol: str
    open_price: str
    close_price: str
    hold_side: str
    amount: str | None = Field(default=None, description="Position size/amount")
    strategy: str | None = Field(default=None, description="Strategy name")
    open_date: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    close_date: str | None = Field(default_factory=None)
    net_profit: str | None = Field(default_factory=None)


class Trades(pdt.BaseModel):
    trades: list[Trade]


# %% EXCHANGE RECORDS


# Normalized exchange records returned by the exchange port; never the vendor's raw `info`.
# Nullable fields mean the venue has not confirmed that value; zero is a real value.
class ExchangePosition(T.TypedDict):
    id: str | None
    symbol: str
    side: T.Literal["long", "short"]
    contracts: float
    entryPrice: float | None
    markPrice: float | None
    notional: float | None
    unrealizedPnl: float | None
    percentage: float | None
    timestamp: int | None


class ExchangeOrder(T.TypedDict):
    id: str | None
    clientOrderId: str | None
    symbol: str
    side: str | None
    type: str | None
    status: str | None
    amount: float | None
    filled: float | None
    average: float | None
    price: float | None
    timestamp: int | None
    lastTradeTimestamp: int | None
    reduceOnly: bool | None


class ExchangeFill(T.TypedDict):
    id: str | None
    order: str | None
    symbol: str
    side: str
    amount: float
    price: float
    timestamp: int
    is_close: bool | None
    realized_pnl: float | None


class ClosedPosition(T.TypedDict):
    id: str | None
    symbol: str
    side: str | None
    timestamp: int | None
    closedTimestamp: int | None
    netPnl: float | None


class Market(T.TypedDict):
    symbol: str
    base: str | None
    swap: bool | None
    linear: bool | None
    settle: str | None
    active: bool | None
    contractSize: float | None
    launchTime: int | None  # milliseconds; None when the venue does not publish it
    tradfi: bool  # tracks a stock, commodity, FX pair or index rather than a crypto asset


class OrderBook(T.TypedDict):
    bids: list[tuple[float, float]]  # (price, base quantity), best first
    asks: list[tuple[float, float]]
