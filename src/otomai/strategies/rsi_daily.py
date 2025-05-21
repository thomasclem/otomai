# %% IMPORTS

import asyncio
import typing as T
from datetime import datetime, timezone

import ta
from pandera.typing import DataFrame

from otomai.core.enums import OrderSide, TradeSide
from otomai.core import utils
from otomai.core.parameters import RsiDailyStrategyParams
from otomai.core.schemas import OHLCVSchema, RsiDailyKpiSchema
from otomai.logger import Logger
from otomai.strategies.base import Strategy

logger = Logger(__name__)

# %% STRATEGY


class RsiDailyStrategy(Strategy):
    KIND: T.Literal["RsiDailyStrategy"] = "RsiDailyStrategy"

    strategy_params: RsiDailyStrategyParams

    @staticmethod
    def _create_indicators(
        df: DataFrame[OHLCVSchema], rsi_window: int
    ) -> DataFrame[RsiDailyKpiSchema]:
        df["rsi"] = df.groupby("symbol")["close"].transform(
            lambda x: ta.momentum.rsi(close=x, window=rsi_window)
        )
        df["rsi_lag"] = df.groupby("symbol")["rsi"].shift()

        return df

    @staticmethod
    def _create_signals(df: DataFrame[RsiDailyKpiSchema], rsi_threshold: float):
        rsi_filter = df["rsi"] >= rsi_threshold
        rsi_lag_filter = df["rsi_lag"] < 72
        rsi_lag_inferior_filter = df["rsi"] >= df["rsi_lag"]
        return df.loc[rsi_filter & rsi_lag_filter & rsi_lag_inferior_filter]

    def _should_open_position(self, symbol: str):
        return (
            len(self.exchange_service.session.fetch_positions(symbols=[symbol])) == 0
        ) and (self.exchange_service.fetch_free_amount_in_balance() > 3)

    def _open_position_order(
        self,
        symbol: str,
        order_side: OrderSide,
        order_type: str,
        margin_mode: str,
        reduce: bool,
    ):
        ticker = self.exchange_service.session.fetch_ticker(symbol=symbol)
        last_price = float(ticker["info"]["lastPr"])
        size = self._get_order_creation_amount(self.trading_params.equity_trade_pct)
        amount = size / last_price

        take_profit_price = utils.calculate_take_profit_price(
            last_price,
            order_side,
            self.trading_params.take_profit_pct,
            self.trading_params.leverage,
        )
        stop_loss_price = utils.calculate_stop_loss_price(
            last_price,
            order_side,
            self.trading_params.stop_loss_pct,
            self.trading_params.leverage,
        )
        try:
            self.exchange_service.set_margin_mode_and_leverage(
                symbol=symbol,
                margin_mode=self.trading_params.margin_mode,
                leverage=self.trading_params.leverage,
            )
            order = self.exchange_service.create_order(
                symbol=symbol,
                side=order_side,
                amount=amount,
                type=order_type,
                margin_mode=margin_mode,
                trade_side=TradeSide.OPEN,
                take_profit_price=take_profit_price,
                stop_loss_price=stop_loss_price,
                reduce=reduce,
            )
            logger.info(f"Order placed successfully: {order}")

            return order
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}")
            raise

    def _process_signal(self, symbol: str, rsi: float):
        if self._should_open_position(symbol=symbol):
            logger.info(f"Buy signal detected for {self.symbol}. RSI: {rsi}")
            open_date_str = str(datetime.now(timezone.utc))
            self._open_position_order(
                symbol=self.symbol,
                order_side=OrderSide.BUY,
                order_type=self.trading_params.order_type,
                margin_mode=self.trading_params.margin_mode,
                reduce=False,
            )
            asyncio.create_task(
                self.monitor_position(
                    symbol=self.symbol,
                    open_date=open_date_str,
                )
            )

    async def run(self):
        while True:
            df = await self.exchange_service.fetch_all_symbols_ohlcv(
                timeframe=self.strategy_params.timeframe,
                ohlcv_window=self.strategy_params.rsi_window + 1,
            )
            df_indicators = self._create_indicators(df, self.strategy_params.rsi_window)
            df_indicators_current = df_indicators.groupby("symbol").last().reset_index()
            df_signals = self._create_signals(
                df_indicators_current, self.strategy_params.rsi_threshold
            )

            for row in df_signals.iterrows():
                self._process_signal(row["symbol"], row["rsi"])
