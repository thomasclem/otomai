# %% IMPORTS

import abc
import asyncio
import typing as T
from datetime import UTC, datetime

import pydantic as pdt

from otomai.adapters import ConsoleNotifier, DatabaseKind, ExchangeKind, NotifierKind, SQLiteDB
from otomai.core.enums import OrderSide
from otomai.core.parameters import StrategyParams, TradingRiskParams
from otomai.services import orders
from otomai.services.position_monitor import PositionMonitor

# %% STRATEGY


class Strategy(abc.ABC, pdt.BaseModel, strict=True, extra="forbid"):
    """A strategy is configured from YAML; adapters are chosen by their `KIND`."""

    KIND: str

    exchange_service: ExchangeKind = pdt.Field(..., discriminator="KIND")
    notifier_service: NotifierKind = pdt.Field(
        default_factory=ConsoleNotifier, discriminator="KIND"
    )
    database_service: DatabaseKind | None = None
    strategy_params: StrategyParams
    trading_params: TradingRiskParams

    _position_monitor: PositionMonitor | None = pdt.PrivateAttr(default=None)

    def __enter__(self) -> "Strategy":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        pass

    @property
    def position_monitor(self) -> PositionMonitor:
        """Lazily built so that strategies which never trade need no database."""
        if self._position_monitor is None:
            if self.database_service is None:
                self.database_service = SQLiteDB()
            self._position_monitor = PositionMonitor(
                exchange_service=self.exchange_service,
                notifier_service=self.notifier_service,
                database_service=self.database_service,
                strategy_name=self.strategy_params.name,
            )
        return self._position_monitor

    def position_opening_available(self, max_simultaneous_positions: int) -> bool:
        """True while open positions plus pending entry orders stay under the limit."""
        open_positions = len(self.exchange_service.positions())
        open_orders = sum(
            o.get("reduceOnly") is not True for o in self.exchange_service.open_orders()
        )
        return open_positions + open_orders < max_simultaneous_positions

    async def open_position(self, symbol: str, side: OrderSide) -> None:
        """Place an entry sized by `trading_params` (a `TradingParams`), notify, then monitor
        it: an entry that does not fill within `order_timeout` seconds ends the monitoring."""
        open_date = datetime.now(UTC).isoformat()
        order = await asyncio.to_thread(
            orders.open_position, self.exchange_service, symbol, side, self.trading_params
        )
        await self.notifier_service.send_message(
            f"### {self.strategy_params.name} ###\n\n"
            f"✅ Order successfully posted for {symbol}.\n\n"
            f"ℹ️ Order info: {order}.\n\n"
            f"⏭️ Start monitoring position opening.."
        )
        asyncio.create_task(
            self.position_monitor.monitor_position(
                symbol=symbol,
                open_date=open_date,
                opening_timeout=self.trading_params.order_timeout,
            )
        )

    @abc.abstractmethod
    async def run(self) -> T.Any:
        """Run the strategy loop."""
