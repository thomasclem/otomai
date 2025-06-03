# %% IMPORTS

import uuid
from datetime import datetime, timezone
import typing as T

import pydantic as pdt


# %% ORDERS


class Order(pdt.BaseModel):
    order_id: str
    symbol: str
    price: str
    amount: str
    order_side: str


class Orders(pdt.BaseModel):
    orders: T.List[Order]


# %% POSITIONS


class Position(pdt.BaseModel):
    id: str = pdt.Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str
    open_price: str
    close_price: str
    hold_side: str
    open_date: str = pdt.Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    close_date: T.Optional[str] = pdt.Field(default_factory=None)
    net_profit: T.Optional[str] = pdt.Field(default_factory=None)
    strategy_params: T.Optional[str] = pdt.Field(default_factory=None)


class Positions(pdt.BaseModel):
    positions: T.List[Position]
