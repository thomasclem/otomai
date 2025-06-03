# %% IMPORTS

import abc
import asyncio
import typing as T
import re

import pydantic as pdt

from otomai.configs import logger
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

    symbol: str = pdt.Field(
        pattern=r"^[A-Z0-9]+/USDT:USDT$",
        description="Trading pair symbol in the format BASE/QUOTE[:EXCHANGE] (e.g., ETH/USDT:USDT)",
        strict=True,
    )
    exchange_service: ExchangeServiceKind = pdt.Field(..., discriminator="KIND")
    notifier_service: NotifierServiceKind = pdt.Field(..., discriminator="KIND")
    database_service: DatabaseService = DynamoDB()
    strategy_params: StrategyParams = pdt.Field(...)
    trading_params: TradingParams = pdt.Field(...)

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

    async def monitor_position_opening(self, symbol):
        open_position = {}
        while not open_position:
            open_position = self.exchange_service.session.fetch_position(symbol)
            await asyncio.sleep(1)

        await self.notifier_service.send_message(
            message=f"### {self.strategy_params.name} ### \n\n Position successfully open for {symbol}."
        )

        return open_position

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
                        logger.info(
                            f"Position for {symbol} saved successfully with net profit: {net_profit}"
                        )
                        await self.notifier_service.send_message(
                            message=(
                                f"### {self.strategy_params.name} ###\n\n"
                                f"Position successfully closed for {symbol} with {position.net_profit}$ net profit"
                            )
                        )
                        break
                    except Exception as e:
                        logger.error(f"Failed to insert position for {symbol}: {e}")
                        raise RuntimeError(
                            f"Error inserting position for {symbol}"
                        ) from e
                else:
                    logger.info(
                        f"No net profit available yet for {symbol}, retrying in {sleep_time} seconds..."
                    )

            await asyncio.sleep(sleep_time)

    async def monitor_position_opening_and_closing(self, symbol: str, open_date: str):
        await self.monitor_position_opening(symbol)
        await self.monitor_position_closing(symbol, open_date)

    def get_order_creation_amount(
        self, equity_trade_pct: float, postions_nb_to_open: int
    ) -> float:
        try:
            free_amount = self.exchange_service.fetch_free_amount_in_balance()
            return free_amount * equity_trade_pct / 100 / postions_nb_to_open
        except Exception as e:
            logger.error(f"Error calculating new position amount: {e}")
            return 0.0

    def get_remaining_position_number_to_open(self):
        return self.trading_params.max_simultaneous_positions - len(
            self.exchange_service.session.fetch_positions()
        )

    @abc.abstractmethod
    async def run(self) -> T.Any:
        """
        Abstract method to run the strategy. Must be implemented by subclasses.
        """
        pass
