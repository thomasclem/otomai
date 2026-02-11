"""
Position monitoring service.

This service handles all position monitoring logic, extracting infrastructure
concerns from strategy classes to promote separation of concerns.
"""

import asyncio
import time
import typing as T

import pydantic as pdt

from otomai.configs import logger
from otomai.core import utils
from otomai.core.constants import (
    POSITION_CLOSING_CHECK_INTERVAL,
    POSITION_CLOSING_MAX_TIMEOUT,
    POSITION_OPENING_CHECK_INTERVAL,
    POSITION_OPENING_TIMEOUT,
)
from otomai.core.exceptions import PositionMonitoringError, PositionTimeoutError
from otomai.core.models import Position
from otomai.services.database import DatabaseService
from otomai.services.notifier import NotifierService


if T.TYPE_CHECKING:
    from otomai.services.exchange import ExchangeKind


class PositionMonitor(pdt.BaseModel):
    """
    Service for monitoring trading positions.

    This service is responsible for tracking position lifecycle from opening
    to closing, saving position data, and sending notifications.
    """

    KIND: T.Literal["PositionMonitor"] = "PositionMonitor"
    exchange_service: "ExchangeKind"
    notifier_service: NotifierService
    database_service: DatabaseService
    strategy_name: str

    model_config = pdt.ConfigDict(arbitrary_types_allowed=True)

    async def monitor_position_opening(
        self,
        symbol: str,
        order_timeout: int = POSITION_OPENING_TIMEOUT,
    ) -> bool:
        """
        Monitor a position until it opens or times out.

        Args:
            symbol: Trading pair symbol
            order_timeout: Maximum time to wait for position to open (seconds)

        Returns:
            True if position opened successfully, False if timed out

        Raises:
            PositionTimeoutError: If position doesn't open within timeout
        """
        start_time = time.time()

        while True:
            try:
                open_position = self.exchange_service.session.fetch_position(symbol)

                if open_position:
                    await self.notifier_service.send_message(
                        message=(
                            f"### {self.strategy_name} ### \n\n"
                            f"✅ Position successfully opened for {symbol}."
                        )
                    )
                    logger.info(f"Position opened successfully for {symbol}")
                    return True

                elapsed_time = time.time() - start_time
                if elapsed_time > order_timeout:
                    error_msg = (
                        f"Timeout: Failed to open position for {symbol} "
                        f"within {order_timeout} seconds."
                    )
                    logger.warning(error_msg)
                    await self.notifier_service.send_message(
                        message=f"### {self.strategy_name} ### \n\n⚠️ {error_msg}"
                    )
                    raise PositionTimeoutError(error_msg)

                await asyncio.sleep(POSITION_OPENING_CHECK_INTERVAL)

            except PositionTimeoutError:
                raise
            except Exception as e:
                logger.error(f"Error monitoring position opening for {symbol}: {e}")
                raise PositionMonitoringError(
                    f"Failed to monitor position opening for {symbol}"
                ) from e

    async def monitor_position_closing(
        self,
        symbol: str,
        open_date: str,
        max_timeout: int = POSITION_CLOSING_MAX_TIMEOUT,
    ) -> None:
        """
        Monitor a position until it closes.

        Args:
            symbol: Trading pair symbol
            open_date: ISO format date when position was opened
            max_timeout: Maximum time to monitor before giving up (seconds)

        Raises:
            PositionMonitoringError: If monitoring fails
            PositionTimeoutError: If position doesn't close within max_timeout
        """
        start_time = time.time()

        while True:
            try:
                elapsed_time = time.time() - start_time
                if elapsed_time > max_timeout:
                    error_msg = (
                        f"Position monitoring timeout for {symbol} "
                        f"after {max_timeout} seconds"
                    )
                    logger.error(error_msg)
                    raise PositionTimeoutError(error_msg)

                positions_history = self.exchange_service.session.fetch_positions_history(
                    symbols=[symbol],
                    since=utils.get_ts_in_ms_from_date(open_date),
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
                                close_price=str(
                                    position_history_info.get("closeAvgPrice")
                                ),
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
                                strategy_params=self.strategy_name,
                            )

                            self.database_service.insert_position(position)
                            logger.info(
                                f"Position for {symbol} saved successfully "
                                f"with net profit: {net_profit}"
                            )

                            await self.notifier_service.send_message(
                                message=(
                                    f"### {self.strategy_name} ###\n\n"
                                    f"Position successfully closed for {symbol} "
                                    f"with {position.net_profit}$ net profit"
                                )
                            )
                            return

                        except Exception as e:
                            logger.error(f"Failed to insert position for {symbol}: {e}")
                            raise PositionMonitoringError(
                                f"Error inserting position for {symbol}"
                            ) from e
                    else:
                        logger.debug(
                            f"No net profit available yet for {symbol}, "
                            f"retrying in {POSITION_CLOSING_CHECK_INTERVAL} seconds..."
                        )

                await asyncio.sleep(POSITION_CLOSING_CHECK_INTERVAL)

            except (PositionMonitoringError, PositionTimeoutError):
                raise
            except Exception as e:
                logger.error(f"Unexpected error monitoring position for {symbol}: {e}")
                raise PositionMonitoringError(
                    f"Failed to monitor position closing for {symbol}"
                ) from e

    async def monitor_position(
        self,
        symbol: str,
        open_date: str,
        opening_timeout: int = POSITION_OPENING_TIMEOUT,
        closing_max_timeout: int = POSITION_CLOSING_MAX_TIMEOUT,
    ) -> None:
        """
        Monitor complete position lifecycle (opening and closing).

        Args:
            symbol: Trading pair symbol
            open_date: ISO format date when position was opened
            opening_timeout: Max time to wait for position to open
            closing_max_timeout: Max time to wait for position to close

        Raises:
            PositionMonitoringError: If monitoring fails
            PositionTimeoutError: If position doesn't open/close within timeout
        """
        try:
            await self.monitor_position_opening(symbol, opening_timeout)
            await self.monitor_position_closing(symbol, open_date, closing_max_timeout)
        except Exception as e:
            logger.error(f"Position monitoring failed for {symbol}: {e}")
            raise
