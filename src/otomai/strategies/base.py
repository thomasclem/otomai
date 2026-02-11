# %% IMPORTS

import abc
import asyncio
import typing as T
import re
import time

import pydantic as pdt

from otomai.configs import logger
from otomai.core import utils
from otomai.core.models import Trade
from otomai.services import (
    ExchangeServiceKind,
    NotifierServiceKind,
    DatabaseService,
    DynamoDB,
    SQLiteDB,
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
    database_service: DatabaseService = pdt.Field(default_factory=SQLiteDB, discriminator="KIND")
    strategy_params: StrategyParams = pdt.Field(...)
    trading_params: TradingParams = pdt.Field(...)

    async def __aenter__(self):
        # Async context manager entry
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Async context manager exit
        if hasattr(self.exchange_service, "close_session"):
            await self.exchange_service.close_session()

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
        # If we were using sync context manager, we might need to handle cleanup differently.
        # But since we are moving to async, we prefer __aenter__ and __aexit__.
        pass

    async def position_opening_available(self, max_simultaneous_positions: int) -> bool:
        open_positions = len(await self.exchange_service.session.fetch_positions())
        open_orders = len(await self.exchange_service.session.fetch_open_orders())
        return open_positions + open_orders < max_simultaneous_positions

    async def monitor_position_opening(self, symbol, order_timeout: int = 600):
        open_position = {}
        start_time = time.time()

        while not open_position:
            open_position = await self.exchange_service.session.fetch_position(symbol)
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
            # The user indicated the response comes from /api/v2/mix/order/fill-history
            # In CCXT, this is typically accessed via fetch_my_trades
            trades = await self.exchange_service.session.fetch_my_trades(
                symbol=symbol, since=utils.get_ts_in_ms_from_date(open_date)
            )

            # We look for a trade that represents the closing (has profit/loss)
            # The opening trade might appear with profit=0.
            # We iterate to find a trade with non-zero profit or deduce it's the closing one.
            # Based on user feedback, we use 'profit' and 'baseVolume'.
            
            closing_trade = None
            for t in trades:
                info = t.get("info", {})
                # Check if this looks like a closing trade
                # Note: "profit" field in Bitget fill-history seems to be the realized PnL
                if "profit" in info and float(info["profit"]) != 0:
                     closing_trade = t
                     break
                # Fallback: if we only have one trade and we know we are closed? 
                # Ideally check position status too, but let's trust the profit signal for now.

            if closing_trade:
                info = closing_trade.get("info", {})
                net_profit = info.get("profit")
                
                if net_profit is not None:
                    try:
                        # Extract timestamps
                        ctime = int(info.get("cTime", 0))
                        
                        trade = Trade(
                            symbol=symbol,
                            net_profit=str(net_profit),
                            open_price=str(closing_trade.get("price")), # Or info.get("price")
                            close_price=str(closing_trade.get("price")), # Approx close price
                            hold_side=str(info.get("side")), # sell/buy
                            open_date=open_date, # Keep original open date
                            close_date=str(utils.get_date_from_ts_in_ms(ctime)) if ctime else str(datetime.now(timezone.utc)),
                            amount=str(info.get("baseVolume", "0")),
                            strategy=self.strategy_params.name,
                        )
                        self.database_service.insert_trade(trade)
                        logger.info(
                            f"Position for {symbol} saved successfully with net profit: {net_profit}"
                        )
                        await self.notifier_service.send_message(
                            message=(
                                f"### {self.strategy_params.name} ###\n\n"
                                f"Position successfully closed for {symbol} with {trade.net_profit}$ net profit"
                            )
                        )
                        return
                    except Exception as e:
                        logger.error(f"Failed to insert position for {symbol}: {e}")
                        raise RuntimeError(
                            f"Error inserting position for {symbol}"
                        ) from e
            else:
                logger.info(
                    f"No closing trade found yet for {symbol}, retrying in {sleep_time} seconds..."
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
