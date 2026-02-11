# %% IMPORTS

import abc
import typing as T

import pydantic as pdt

from otomai.core.parameters import TradingParams, StrategyParams
from otomai.services import (
    ExchangeServiceKind,
    NotifierService,
    DatabaseService,
    DynamoDB,
)
from otomai.services.position_monitor import PositionMonitor


# %% STRATEGY


class Strategy(abc.ABC, pdt.BaseModel, strict=True, extra="forbid"):
    KIND: str

    symbol: T.Optional[str] = pdt.Field(
        default=None,
        pattern=r"^[A-Z0-9]+/USDT:USDT$",
        description="Trading pair symbol in the format BASE/QUOTE[:EXCHANGE] (e.g., ETH/USDT:USDT)",
        strict=True,
    )
    exchange_service: ExchangeServiceKind = pdt.Field(..., discriminator="KIND")
    notifier_service: NotifierService = pdt.Field(..., discriminator="KIND")
    database_service: DatabaseService = DynamoDB()
    strategy_params: StrategyParams = pdt.Field(...)
    trading_params: TradingParams = pdt.Field(...)

    # Position monitoring service (separation of concerns)
    _position_monitor: T.Optional[PositionMonitor] = pdt.PrivateAttr(default=None)

    def __enter__(self) -> "Strategy":
        """
        Enter method for context manager.
        """
        # You can initialize resources here if needed
        return self

    def __exit__(
        self,
        exc_type: T.Type[BaseException],
        exc_value: BaseException,
        traceback: T.Any,
    ) -> None:
        """
        Exit method for context manager.
        """
        pass

    @property
    def position_monitor(self) -> PositionMonitor:
        """
        Get or create the position monitor service.

        Returns:
            PositionMonitor instance configured for this strategy
        """
        if self._position_monitor is None:
            self._position_monitor = PositionMonitor(
                exchange_service=self.exchange_service,
                notifier_service=self.notifier_service,
                database_service=self.database_service,
                strategy_name=self.strategy_params.name,
            )
        return self._position_monitor

    def position_opening_available(self, max_simultaneous_positions: int) -> bool:
        """
        Check if a new position can be opened based on current positions and orders.

        Args:
            max_simultaneous_positions: Maximum allowed simultaneous positions

        Returns:
            True if a new position can be opened, False otherwise
        """
        open_positions = len(self.exchange_service.session.fetch_positions())
        open_orders = len(self.exchange_service.session.fetch_open_orders())
        return open_positions + open_orders < max_simultaneous_positions

    @abc.abstractmethod
    async def run(self) -> T.Any:
        """
        Abstract method to run the strategy. Must be implemented by subclasses.
        """
        pass
