# %% IMPORTS

import asyncio
import typing as T
from datetime import datetime, timezone

import pandas as pd
import ta
from pandera.typing import DataFrame

from otomai.core.enums import OrderSide, TradeSide
from otomai.core.parameters import MratZscoreStrategyParams, TradingParams
from otomai.core.schemas import OHLCVSchema, MratZscoreKpiSchema
from otomai.core.indicators import MRAT
from otomai.strategies.base import Strategy

# %% STRATEGY


class MratZscoreStrategy(Strategy):
    KIND: T.Literal["MratZscoreStrategy"] = "MratZscoreStrategy"

    strategy_params: MratZscoreStrategyParams

    @staticmethod
    def _create_indicators(
        df: DataFrame[OHLCVSchema],
        slow_ma_length: int,
        fast_ma_length: int,
        filter_ma_length: int,
    ) -> DataFrame[MratZscoreKpiSchema]:
        mrat = MRAT(
            slow_ma_length,
            fast_ma_length,
            df["close"],
        )
        df["filter_ma"] = ta.trend.sma_indicator(
            close=df["close"], window=filter_ma_length
        )
        df["slow_ma"] = ta.trend.sma_indicator(close=df["close"], window=slow_ma_length)
        df["mrat"] = mrat.calculate_mrat()
        df["mean_mrat"] = ta.trend.sma_indicator(
            close=df["mrat"], window=slow_ma_length
        )
        df["stdev_mrat"] = df["mrat"].rolling(slow_ma_length).std(ddof=0)
        df["z_score_mrat"] = (df["mrat"] - df["mean_mrat"]) / df["stdev_mrat"]

        return df

    def _fetch_and_prepare_data(
        self,
        symbol: str,
        ohlcv_timeframe: str,
        ohlcv_window: int,
        strategy_params: MratZscoreStrategyParams,
    ) -> DataFrame[MratZscoreKpiSchema]:
        df = self.exchange_service.fetch_ohlcv_df(
            symbol=symbol,
            timeframe=ohlcv_timeframe,
            window=ohlcv_window,
        )
        df = OHLCVSchema.validate(df)

        return self._create_indicators(
            df=df,
            slow_ma_length=strategy_params.slow_ma_length,
            fast_ma_length=strategy_params.fast_ma_length,
            filter_ma_length=strategy_params.filter_ma_length,
        )

    @staticmethod
    def _is_buy_signal(
        df: pd.DataFrame, z_score_threshold: float, z_score_lookback_window: int
    ) -> bool:
        """
        Check if buy conditions are met.

        Args:
            df: DataFrame with OHLCV data and indicators
            z_score_threshold: Z-score threshold value (positive, will be negated)
            z_score_lookback_window: Number of candles to look back for z-score threshold

        Returns:
            True if buy conditions are met
        """
        under_z_score_threshold = (
            len(
                df.iloc[-z_score_lookback_window:].loc[
                    df["z_score_mrat"] <= -z_score_threshold
                ]
            )
            > 0
        )

        has_rebound = (
            df.iloc[-2]["close"] > df.iloc[-3]["open"]
            and df.iloc[-2]["high"] > df.iloc[-3]["high"]
        )

        filter_ma_under_slow_ma = df.iloc[-1]["filter_ma"] < df.iloc[-1]["slow_ma"]

        return under_z_score_threshold and has_rebound and filter_ma_under_slow_ma

    @staticmethod
    def _is_sell_signal(
        df: pd.DataFrame,
        z_score_lookback_window: int,
        z_score_threshold: float,
    ) -> bool:
        """
        Check if sell conditions are met.

        Args:
            df: DataFrame with OHLCV data and indicators
            z_score_threshold: Z-score threshold for selling

        Returns:
            True if sell conditions are met
        """
        above_z_score_threshold = (
            len(
                df.iloc[-z_score_lookback_window:].loc[
                    df["z_score_mrat"] >= z_score_threshold
                ]
            )
            > 0
        )
        candle_condition = df.iloc[-2]["high"] < df.iloc[-3]["high"]

        return above_z_score_threshold and candle_condition

    def _check_signals(
        self,
        df: DataFrame[MratZscoreKpiSchema],
        strategy_params: MratZscoreStrategyParams,
    ) -> OrderSide:
        if self._is_sell_signal(
            df=df,
            z_score_lookback_window=strategy_params.z_score_lookback_window,
            z_score_threshold=strategy_params.z_score_threshold_sell,
        ):
            return OrderSide.SELL
        elif self._is_buy_signal(
            df=df,
            z_score_lookback_window=strategy_params.z_score_lookback_window,
            z_score_threshold=strategy_params.z_score_threshold_buy,
        ):
            return OrderSide.BUY

        return OrderSide.NONE

    def _process_signal(
        self, symbol: str, signal: OrderSide, trading_params: TradingParams
    ):
        if self.position_opening_available(
            max_simultaneous_positions=trading_params.max_simultaneous_positions
        ):
            if (signal == OrderSide.BUY and trading_params.long_enabled) or (
                signal == OrderSide.SELL and trading_params.short_enabled
            ):
                open_date_str = str(datetime.now(timezone.utc))
                order = self.exchange_service.open_future_order(
                    symbol=symbol,
                    equity_trade_pct=trading_params.equity_trade_pct,
                    order_type=trading_params.order_type,
                    order_side=signal,
                    margin_mode=trading_params.margin_mode,
                    leverage=trading_params.leverage,
                    take_profit_pct=trading_params.take_profit_pct,
                    stop_loss_pct=trading_params.stop_loss_pct,
                )
                print(order, open_date_str)
        return

    def _should_close_position(
        self,
        symbol: str,
        z_score_lookback_window: int,
        z_score_threshold: float,
        tp_z_score_threshold: float,
        df: DataFrame[MratZscoreKpiSchema],
    ) -> bool:
        """
        Check if position should be closed based on new logic.

        Args:
            symbol: Trading symbol
            df: DataFrame with indicators

        Returns:
            True if position should be closed
        """
        position = self.exchange_service.session.fetch_position(symbol=symbol)

        if not position or not position.get("unrealizedPnl"):
            return False

        if len(self.exchange_service.session.fetch_open_orders(symbol=self.symbol)) > 0:
            return False

        return self._is_sell_signal(
            df,
            z_score_lookback_window,
            z_score_threshold,
        )

    def _close_position_order(
        self, symbol: str, order_type: str, margin_mode: str
    ) -> T.Dict:
        pos = self.exchange_service.session.fetch_position(symbol=symbol)
        return self.exchange_service.create_order(
            symbol=symbol,
            side=OrderSide.BUY,
            amount=pos["contracts"],
            type=order_type,
            margin_mode=margin_mode,
            trade_side=TradeSide.CLOSE,
            reduce=True,
        )

    async def run(self):
        while True:
            try:
                df = self._fetch_and_prepare_data(
                    symbol=self.symbol,
                    ohlcv_timeframe=self.strategy_params.timeframe,
                    ohlcv_window=self.strategy_params.filter_ma_length + 1,
                    strategy_params=self.strategy_params,
                )

                signal = self._check_signals(
                    df=df, strategy_params=self.strategy_params
                )

                print(signal)

                await asyncio.sleep(60)

            except Exception as e:
                self.logger.error(f"Error in run loop: {e}")
                await asyncio.sleep(60)
