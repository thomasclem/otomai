"""
Position monitoring service.

This service handles all position monitoring logic, extracting infrastructure
concerns from strategy classes to promote separation of concerns.
"""

import asyncio
import time
import typing as T
from datetime import datetime, timezone

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
from otomai.core.models import Trade
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
        hold_side: T.Optional[str] = None,
        max_timeout: int = POSITION_CLOSING_MAX_TIMEOUT,
    ) -> None:
        """
        Monitor a position until it closes.

        Args:
            symbol: Trading pair symbol
            open_date: ISO format date when position was opened
            hold_side: 'long' or 'short'. Used to filter closing trades (opposite side).
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


                # Use fetch_my_trades (Fill History) to check for closing execution
                # We fetch all trades since the position open time
                trades = self.exchange_service.session.fetch_my_trades(
                    symbol=symbol,
                    since=utils.get_ts_in_ms_from_date(open_date),
                )
                
                # Logic to identify the closing trade(s) for THIS position:
                # 1. Must be for the correct symbol.
                # 2. Must be OPPOSITE to the hold_side (if known).
                #    Long Position -> Closing Trade is 'sell'
                #    Short Position -> Closing Trade is 'buy'
                # 3. Must have 'profit' (Realized PnL) != 0 (Strong confirmation).
                
                required_trade_side = None
                if hold_side:
                    s = hold_side.lower()
                    if s == 'long':
                        required_trade_side = 'sell'
                    elif s == 'short':
                        required_trade_side = 'buy'

                closing_trades = []
                for t in trades:
                    info = t.get("info", {})
                    # Ensure symbol matches
                    if t.get("symbol") != symbol:
                        continue
                    
                    # Check Side (if we know what to look for)
                    if required_trade_side and t.get("side") != required_trade_side:
                        continue

                    # Check for realized profit (Bitget specific)
                    # This is the most reliable way to ignore entry fills which usually have 0 profit.
                    if "profit" in info and float(info["profit"]) != 0:
                         closing_trades.append(t)

                if closing_trades:
                    # If multiple closing trades found (e.g. partial fills), we should ideally aggregate them.
                    # For now, we take the most recent one or aggregate if they happened recently.
                    # Assumption: The strategy closes in one go or we want to record the cumulative result.
                    # Let's sum up the profit and amount for the "Trade" record if we consider the position closed.
                    
                    # Check if position is actually closed on exchange to confirm valid aggregation?
                    # Or just record the fills.
                    # Simplification: Take the last one (most recent) or sum them?
                    # The user wants "the info from the trade you are monitoring".
                    # Let's aggregate PnL and Size from all detected closing fills since open.
                    
                    total_pnl = 0.0
                    total_size = 0.0
                    last_trade = closing_trades[-1]
                    last_info = last_trade.get("info", {})
                    
                    for ct in closing_trades:
                        i = ct.get("info", {})
                        total_pnl += float(i.get("profit", 0))
                        total_size += float(i.get("baseVolume", i.get("size", 0)))

                    info = last_trade.get("info", {})
                    
                    # Extract timestamps from the last trade
                    ctime = int(info.get("cTime", 0))
                    close_date_str = (
                        str(utils.get_date_from_ts_in_ms(ctime))
                        if ctime
                        else str(datetime.now(timezone.utc))
                    )

                    trade = Trade(
                        symbol=symbol,
                        net_profit=str(total_pnl),
                        open_price=str(last_trade.get("price")), # Use last close price
                        close_price=str(last_trade.get("price")),
                        hold_side=str(info.get("side")),
                        open_date=open_date,
                        close_date=close_date_str,
                        amount=str(total_size),
                        strategy=self.strategy_name,
                    )


                    self.database_service.insert_trade(trade)
                    logger.info(
                        f"Trade for {symbol} saved successfully "
                        f"with net profit: {total_pnl}"
                    )

                    await self.notifier_service.send_message(
                        message=(
                            f"### {self.strategy_name} ###\n\n"
                            f"Position successfully closed for {symbol} "
                            f"with {trade.net_profit}$ net profit"
                        )
                    )
                    return

                
                # If no closing trade found, wait and retry
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
            # 1. Wait for position to open
            await self.monitor_position_opening(symbol, opening_timeout)
            
            # 2. Fetch active position details to get the side (Long/Short)
            # This is crucial to distinguish closing trades (opposite side) from opening trades.
            position = self.exchange_service.session.fetch_position(symbol)
            hold_side = None
            if position:
                # Bitget/CCXT standard: info['holdSide'] is usually 'long' or 'short'
                # or side is 'long'/'short' in the main dict structure
                hold_side = position.get("side") or position.get("info", {}).get("holdSide")
            
            # 3. Monitor for closing
            await self.monitor_position_closing(
                symbol, 
                open_date, 
                hold_side=hold_side,
                max_timeout=closing_max_timeout
            )
            
        except Exception as e:
            logger.error(f"Position monitoring failed for {symbol}: {e}")
            raise
