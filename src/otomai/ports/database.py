import abc

import pydantic as pdt

from otomai.core.models import Trade, Trades


class Database(abc.ABC, pdt.BaseModel):
    """Stores closed trades."""

    KIND: str

    @abc.abstractmethod
    def insert_trade(self, trade: Trade) -> None: ...

    @abc.abstractmethod
    def fetch_all_trades(self) -> Trades: ...
