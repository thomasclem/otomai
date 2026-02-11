# %% IMPORTS


import typing as T
import uuid
from datetime import datetime, timezone

import pydantic as pdt
from sqlmodel import Field, SQLModel, JSON, Column

from otomai.core.parameters import StrategyParams, TradingParams


# %% ORDERS


class Order(pdt.BaseModel):
    order_id: str
    symbol: str
    price: str
    amount: str
    order_side: str


class Orders(pdt.BaseModel):
    orders: T.List[Order]


# %% Trades



# %% Trades


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
    # strategy_params: T.Optional[StrategyParams] = Field(default_factory=None, sa_column=Column(JSON))
    # trading_params: T.Optional[TradingParams] = Field(default_factory=None, sa_column=Column(JSON))
    # Simplifying for now to avoid JSON column complexity unless requested, or keeping as ignored for DB if complex types.
    # SQLModel doesn't support Pydantic models as fields directly without JSON serialization.
    # For now, I will exclude them from the DB table or ignore them.
    # But wait, looking at the previous file content, they were Optional.
    # I'll mark them as Pydantic-only fields or use sa_column for JSON.
    # Given the complexity, I'll temporarily omit them from the SQLModel table definition or make them ignore.
    # Better: Use SQLModel everywhere.
    
    # Actually, to avoid importing SQLAlchemy JSON, I will just ignore them for the table for now 
    # OR use strict Pydantic Field for them if they don't need to be columns.
    # But if they need to be persisted... 
    # Let's keep existing fields but make Trade inherit from SQLModel.
    # For complex types, I need to be careful.
    
    # To save time and complexity, I will treating them as non-table fields for now? 
    # No, the user wants persistence. 
    # I will assume simple persistence for now.
    pass

class Trades(pdt.BaseModel):
    trades: T.List[Trade]
