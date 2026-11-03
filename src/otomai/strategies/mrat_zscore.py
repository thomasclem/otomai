# %% IMPORTS

import asyncio
import typing as T
from datetime import UTC, datetime

import pandas as pd
import pandera.pandas as pa
import pydantic as pdt
import ta
from pandera.typing import DataFrame
from pydantic import Field, model_validator

from otomai.core.enums import OrderSide, OrderType
from otomai.core.indicators import MRAT
from otomai.core.parameters import StrategyParams, TradingParams
from otomai.core.schemas import OHLCVSchema
from otomai.logger import Logger
from otomai.services import orders
from otomai.strategies.base import Strategy

logger = Logger(__name__)

SCAN_INTERVAL_SECONDS = 60
OHLCV_WINDOW = 200

# %% PARAMS


class MratZscoreStrategyParams(StrategyParams):
    name: str = Field(default="mrat_zscore", description="Strategy name")
    fast_ma_length: int = Field(default=9, description="Fast moving average length.")
    slow_ma_length: int = Field(default=51, description="Slow moving average length.")
    filter_ma_length: int = Field(default=100, description="Filter moving average length.")
    z_score_threshold_buy: float = Field(
        default=2.5, description="Threshold of the MRAT Z score to buy."
    )
    z_score_threshold_sell: float = Field(
        default=2.0, description="Threshold of the MRAT Z score to sell."
    )
    z_score_lookback_window: int = Field(default=10, description="MRAT Z-score lookback window")
    tp_z_score_threshold: float = Field(
        default=2.0, description="Take profit percentage if z_score threshold is overcome."
    )
    timeframe: T.Literal["1m", "5m", "15m", "30m", "1h", "4h"] = Field(
        default="1h", description="Timeframe symbol"
    )

    @model_validator(mode="after")
    def validate_moving_average_lengths(self):
        if not (self.fast_ma_length < self.slow_ma_length < self.filter_ma_length):
            raise ValueError(
                "Invalid moving average lengths: "
                "fast_ma_length must be < slow_ma_length and slow_ma_length must be < filter_ma_length."
            )
        return self


MratZscoreKpiSchema = OHLCVSchema.add_columns(
    {
        "filter_ma": pa.Column(float, nullable=True, coerce=True),
        "slow_ma": pa.Column(float, nullable=True, coerce=True),
        "mrat": pa.Column(float, nullable=True, coerce=True),
        "mean_mrat": pa.Column(float, nullable=True, coerce=True),
        "stdev_mrat": pa.Column(float, nullable=True, coerce=True),
        "z_score_mrat": pa.Column(float, nullable=True, coerce=True),
    }
)

# %% STRATEGY


class MratZscoreStrategy(Strategy):
    KIND: T.Literal["MratZscoreStrategy"] = "MratZscoreStrategy"

    symbol: str = pdt.Field(
        pattern=r"^[A-Z0-9]+/USDT:USDT$",
        description="Trading pair symbol in the format BASE/QUOTE:SETTLE (e.g., ETH/USDT:USDT)",
    )
    strategy_params: MratZscoreStrategyParams
    trading_params: TradingParams

    def _create_indicators(self, df: DataFrame[OHLCVSchema]) -> DataFrame[MratZscoreKpiSchema]:
        p = self.strategy_params
        mrat = MRAT(p.slow_ma_length, p.fast_ma_length, df["close"])
        df["filter_ma"] = ta.trend.sma_indicator(close=df["close"], window=p.filter_ma_length)
        df["slow_ma"] = ta.trend.sma_indicator(close=df["close"], window=p.slow_ma_length)
        df["mrat"] = mrat.calculate_mrat()
        df["mean_mrat"] = ta.trend.sma_indicator(close=df["mrat"], window=p.slow_ma_length)
        df["stdev_mrat"] = df["mrat"].rolling(p.slow_ma_length).std(ddof=0)
        df["z_score_mrat"] = (df["mrat"] - df["mean_mrat"]) / df["stdev_mrat"]
        return df

    @staticmethod
    def _is_buy_signal(
        df: pd.DataFrame, z_score_threshold: float, z_score_lookback_window: int
    ) -> bool:
        """A recent z-score dip below -threshold, a rebound candle and a falling trend filter."""
        recent = df.iloc[-z_score_lookback_window:]
        under_z_score_threshold = bool((recent["z_score_mrat"] <= -z_score_threshold).any())
        has_rebound = (
            df.iloc[-2]["close"] > df.iloc[-3]["open"] and df.iloc[-2]["high"] > df.iloc[-3]["high"]
        )
        filter_ma_under_slow_ma = df.iloc[-1]["filter_ma"] < df.iloc[-1]["slow_ma"]
        logger.info(
            f"Z score under threshold: {under_z_score_threshold}, "
            f"has rebound: {has_rebound}, filter MA under slow MA: {filter_ma_under_slow_ma}"
        )
        return under_z_score_threshold and has_rebound and filter_ma_under_slow_ma

    @staticmethod
    def _is_sell_signal(
        df: pd.DataFrame,
        z_score_lookback_window: int,
        z_score_threshold: float,
        position_percentage: float,
        tp_z_score_threshold: float,
    ) -> bool:
        """A recent z-score above threshold, enough profit and a lower-high candle."""
        recent = df.iloc[-z_score_lookback_window:]
        above_z_score_threshold = bool((recent["z_score_mrat"] >= z_score_threshold).any())
        position_condition = position_percentage >= tp_z_score_threshold
        candle_condition = df.iloc[-2]["high"] < df.iloc[-3]["high"]
        return above_z_score_threshold and position_condition and candle_condition

    def _should_open_position(
        self,
        df: DataFrame[MratZscoreKpiSchema],
        z_score_lookback_window: int,
        z_score_threshold: float,
    ) -> bool:
        """Buy signal on a free symbol whose last position closed long enough ago."""
        x = self.exchange_service
        if x.positions(symbols=[self.symbol]) or x.open_orders(symbol=self.symbol):
            return False
        history = x.position_history(symbols=[self.symbol])
        if history:
            opened = datetime.fromtimestamp(history[0]["timestamp"] / 1000, UTC)
            hours_since = round((datetime.now(UTC) - opened).total_seconds() / 3600)
            if hours_since < z_score_lookback_window:
                logger.info(f"Previous position is too recent: {hours_since} hours ago")
                return False
        return self._is_buy_signal(df, z_score_threshold, z_score_lookback_window)

    def _should_close_position(
        self,
        symbol: str,
        z_score_lookback_window: int,
        z_score_threshold: float,
        tp_z_score_threshold: float,
        df: DataFrame[MratZscoreKpiSchema],
    ) -> bool:
        position = self.exchange_service.position(symbol=symbol)
        if position is None or position.get("unrealizedPnl") is None:
            return False
        if self.exchange_service.open_orders(symbol=symbol):
            return False
        return self._is_sell_signal(
            df,
            z_score_lookback_window,
            z_score_threshold,
            float(position.get("percentage") or 0.0),
            tp_z_score_threshold,
        )

    async def _tick(self) -> bool:
        """One evaluation; False when the exchange returned no candles."""
        p = self.strategy_params
        df = self.exchange_service.fetch_ohlcv_df(
            symbol=self.symbol, timeframe=p.timeframe, window=OHLCV_WINDOW
        )
        if df.empty:
            logger.warning("No data fetched from the exchange. Retrying...")
            return False
        df = self._create_indicators(OHLCVSchema.validate(df))
        z_score = df.iloc[-1]["z_score_mrat"]
        if self._should_open_position(df, p.z_score_lookback_window, p.z_score_threshold_buy):
            logger.info(f"Buy signal detected for {self.symbol}. Z-Score: {z_score}")
            await self.open_position(self.symbol, OrderSide.BUY)
        elif self._should_close_position(
            self.symbol,
            p.z_score_lookback_window,
            p.z_score_threshold_sell,
            p.tp_z_score_threshold,
            df,
        ):
            logger.info(f"Sell signal detected for {self.symbol}. Z-Score: {z_score}; closing.")
            orders.close_position(
                self.exchange_service,
                self.symbol,
                OrderType.MARKET.value,
                self.trading_params.margin_mode,
            )
        else:
            logger.info(f"No signal for {self.symbol}. Z-Score: {z_score:.4f}")
        return True

    async def run(self):
        while True:
            try:
                fetched = await self._tick()
            except Exception as e:
                logger.error(f"Error in MRATStrategy run loop: {e}")
                fetched = True
            await asyncio.sleep(SCAN_INTERVAL_SECONDS if fetched else 1)
