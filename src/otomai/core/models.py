# %% IMPORTS

import typing as T
import uuid
from datetime import datetime, timezone

import pydantic as pdt
from sqlmodel import Field, SQLModel


# %% ORDERS


class Order(pdt.BaseModel):
    order_id: str
    symbol: str
    price: str
    amount: str
    order_side: str


class Orders(pdt.BaseModel):
    orders: T.List[Order]



# %% TRADES


class OptionalSQLModel(SQLModel):
    """
    Base model that makes all fields optional for partial updates/creation if needed.
    """
    pass


class Trade(OptionalSQLModel, table=True):
    id: T.Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    symbol: str
    open_price: str
    close_price: str
    hold_side: str
    amount: T.Optional[str] = Field(default=None, description="Position size/amount")
    strategy: T.Optional[str] = Field(default=None, description="Strategy name")
    open_date: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    close_date: T.Optional[str] = Field(default_factory=None)
    net_profit: T.Optional[str] = Field(default_factory=None)


class Trades(pdt.BaseModel):
    trades: T.List[Trade]
