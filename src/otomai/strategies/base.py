# %% IMPORTS

import abc
import asyncio
import typing as T
import re
import time

import pydantic as pdt
from pydantic import PrivateAttr

from otomai.logger import Logger
from otomai.core import utils
from otomai.core.models import Position
from otomai.services import (
    ExchangeServiceKind,
    NotifierServiceKind,
    DatabaseService,
    DynamoDB,
)
from otomai.core.parameters import TradingParams, StrategyParams

# %% VARIABLES

SYMBOL_REGEX: re.Pattern = re.compile(r"^[A-Z0-9]+/[A-Z0-9]+(:[A-Z0-9]+)?$")

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
    notifier_service: NotifierServiceKind = pdt.Field(..., discriminator="KIND")
    database_service: DatabaseService = DynamoDB()
    strategy_params: StrategyParams = pdt.Field(...)
    trading_params: TradingParams = pdt.Field(...)

    _logger: T.Optional[Logger] = PrivateAttr(default=None)

    def __init__(self, **data):
        super().__init__(**data)
        # Initialize logger with strategy name
        self._logger = Logger(__name__, strategy_name=self.strategy_params.name)

    @property
    def logger(self) -> Logger:
        """Get the strategy logger."""
        if self._logger is None:
            self._logger = Logger(__name__, strategy_name=self.strategy_params.name)
        return self._logger

    def __enter__(self) -> "Strategy":
        """
        Enter method for context manager.
        """
        # Log strategy startup
        self.logger.info(f"Starting strategy: {self.strategy_params.name}")
        if self.symbol:
            self.logger.info(f"Trading symbol: {self.symbol}")
        self.logger.info(f"Strategy params: {self.strategy_params.model_dump()}")
        self.logger.info(f"Trading params: {self.trading_params.model_dump()}")
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
        self.logger.info(f"Stopping strategy: {self.strategy_params.name}")

    def position_opening_available(self, max_simultaneous_positions: int) -> bool:
        open_positions = len(self.exchange_service.session.fetch_positions())
        open_orders = len(self.exchange_service.session.fetch_open_orders())
        return open_positions + open_orders < max_simultaneous_positions

    async def monitor_position_opening(self, symbol, order_timeout: int = 600):
        open_position = {}
        start_time = time.time()

        while not open_position:
            open_position = self.exchange_service.session.fetch_position(symbol)
            if open_position:
                await self.notifier_service.send_message(
                    message=f"### {self.strategy_params.name} ### \n\n✅ Position successfully open for {symbol}."
                )
                return

            if time.time() - start_time > order_timeout:
                await self.notifier_service.send_message(
                    message=f"### {self.strategy_params.name} ### \n\n⚠️ Timeout: Failed to open position for {symbol} within {order_timeout} seconds."
                )
                return

            await asyncio.sleep(1)

    async def monitor_position_closing(
        self,
        symbol: str,
        open_date: str,
    ):
        sleep_time = 60
        while True:
            positions_history = self.exchange_service.session.fetch_positions_history(
                symbols=[symbol], since=utils.get_ts_in_ms_from_date(open_date)
            )

            if positions_history:
                position_history = positions_history[0]
                position_history_info = position_history.get("info", {})
                net_profit = position_history_info.get("netProfit")

                if net_profit is not None:
                    try:
                        position = Position(
                            symbol=symbol,
                            net_profit=str(net_profit),
                            open_price=str(position_history_info.get("openAvgPrice")),
                            close_price=str(position_history_info.get("closeAvgPrice")),
                            hold_side=str(position_history_info.get("holdSide")),
                            open_date=str(
                                utils.get_date_from_ts_in_ms(
                                    int(position_history_info["ctime"])
                                )
                            ),
                            close_date=str(
                                utils.get_date_from_ts_in_ms(
                                    int(position_history_info["utime"])
                                )
                            ),
                            strategy_params=str(self.strategy_params),
                        )
                        self.database_service.insert_position(position)
                        self.logger.info(
                            f"Position for {symbol} saved successfully with net profit: {net_profit}"
                        )
                        await self.notifier_service.send_message(
                            message=(
                                f"### {self.strategy_params.name} ###\n\n"
                                f"Position successfully closed for {symbol} with {position.net_profit}$ net profit"
                            )
                        )
                        return
                    except Exception as e:
                        self.logger.error(
                            f"Failed to insert position for {symbol}: {e}"
                        )
                        raise RuntimeError(
                            f"Error inserting position for {symbol}"
                        ) from e
                else:
                    self.logger.info(
                        f"No net profit available yet for {symbol}, retrying in {sleep_time} seconds..."
                    )

            await asyncio.sleep(sleep_time)

    async def monitor_position(self, symbol: str, open_date: str):
        await self.monitor_position_opening(symbol)
        await self.monitor_position_closing(symbol, open_date)

    @abc.abstractmethod
    async def run(self) -> T.Any:
        """
        Abstract method to run the strategy. Must be implemented by subclasses.
        """
        pass
