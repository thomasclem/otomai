# %% IMPORTS

import asyncio
import typing as T
from datetime import datetime, timezone

import pandas as pd
import ta
from pandera.typing import DataFrame

from otomai.core.enums import OrderSide, TradeSide, OrderType
from otomai.core import utils
from otomai.core.parameters import MratZscoreStrategyParams
from otomai.core.schemas import OHLCVSchema, MratZscoreKpiSchema
from otomai.core.indicators import MRAT
from otomai.logger import Logger
from otomai.strategies.base import Strategy

logger = Logger(__name__)

# %% STRATEGY


class MratZscoreStrategy(Strategy):
    KIND: T.Literal["MratZscoreStrategy"] = "MratZscoreStrategy"

    strategy_params: MratZscoreStrategyParams

    def _create_indicators(
        self, df: DataFrame[OHLCVSchema]
    ) -> DataFrame[MratZscoreKpiSchema]:
        mrat = MRAT(
            self.strategy_params.slow_ma_length,
            self.strategy_params.fast_ma_length,
            df["close"],
        )
        df["filter_ma"] = ta.trend.sma_indicator(
            close=df["close"], window=self.strategy_params.filter_ma_length
        )
        df["slow_ma"] = ta.trend.sma_indicator(
            close=df["close"], window=self.strategy_params.slow_ma_length
        )
        df["mrat"] = mrat.calculate_mrat()
        df["mean_mrat"] = ta.trend.sma_indicator(
            close=df["mrat"], window=self.strategy_params.slow_ma_length
        )
        df["stdev_mrat"] = (
            df["mrat"].rolling(self.strategy_params.slow_ma_length).std(ddof=0)
        )
        df["z_score_mrat"] = (df["mrat"] - df["mean_mrat"]) / df["stdev_mrat"]

        return df

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
        position_percentage: float,
        tp_z_score_threshold: float,
    ) -> bool:
        """
        Check if sell conditions are met.

        Args:
            df: DataFrame with OHLCV data and indicators
            z_score_threshold: Z-score threshold for selling
            position_percentage: Current position percentage
            tp_z_score_threshold: Take profit z-score threshold

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
        position_condition = position_percentage >= tp_z_score_threshold
        candle_condition = df.iloc[-2]["high"] < df.iloc[-3]["high"]

        return above_z_score_threshold and position_condition and candle_condition

    def _get_order_creation_amount(self, equity_trade_pct: float) -> float:
        try:
            balance = self.exchange_service.session.fetch_balance()
            free_amount = balance["USDT"]["free"]
            return free_amount * equity_trade_pct / 100
        except Exception as e:
            logger.error(f"Error calculating new position amount: {e}")
            return 0.0

    def _should_open_position(
        self,
        df: DataFrame[MratZscoreKpiSchema],
        z_score_lookback_window: int,
        z_score_threshold: float,
    ) -> bool:
        """
        Check if position should be opened based on new logic.

        Args:
            df: DataFrame with indicators
            z_score_lookback_window: Window size for z-score threshold check

        Returns:
            True if position should be opened
        """
        position_history = self.exchange_service.session.fetch_positions_history(
            symbols=[self.symbol]
        )

        if not position_history:
            logger.info("No previous positions found, eligible to open a new one.")
            return self._is_buy_signal(df, z_score_threshold, z_score_lookback_window)

        last_position = position_history[0]
        hours_since_last_position = round(
            (
                datetime.utcnow()
                - datetime.utcfromtimestamp(last_position[0]["timestamp"] / 1000)
            ).total_seconds()
            / 3600
        )

        if hours_since_last_position < z_score_lookback_window:
            logger.info(
                f"Can't open new position, previous position is too recent: {hours_since_last_position} hours ago"
            )
            return False

        if (
            len(self.exchange_service.session.fetch_positions(symbols=[self.symbol]))
            > 0
        ):
            logger.info("Can't open new position as positions are currently running")
            return False

        if len(self.exchange_service.session.fetch_open_orders(symbol=self.symbol)) > 0:
            logger.info("Can't open new position as orders are currently running")
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

        position_percentage = float(position.get("percentage", 0.0))

        return self._is_sell_signal(
            df,
            z_score_lookback_window,
            z_score_threshold,
            position_percentage,
            tp_z_score_threshold,
        )

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
                # Fetch data
                df = self.exchange_service.fetch_ohlcv_df(
                    symbol=self.symbol,
                    timeframe=self.strategy_params.timeframe,
                    window=200,
                )
                df = OHLCVSchema.validate(df)

                if df.empty:
                    logger.warning("No data fetched from the exchange. Retrying...")
                    await asyncio.sleep(1)
                    continue

                # Create indicators
                df_kpis = self._create_indicators(df)
                current_row = df_kpis.iloc[-1]

                # Check signals with new logic
                if self._should_open_position(
                    df=df_kpis,
                    z_score_lookback_window=self.strategy_params.z_score_lookback_window,
                    z_score_threshold=self.strategy_params.z_score_threshold_buy,
                ):
                    logger.info(
                        f"Buy signal detected for {self.symbol}. Z-Score: {current_row['z_score_mrat']}"
                    )
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
                elif self._should_close_position(
                    symbol=self.symbol,
                    z_score_lookback_window=self.strategy_params.z_score_lookback_window,
                    z_score_threshold=self.strategy_params.z_score_threshold_sell,
                    tp_z_score_threshold=self.strategy_params.tp_z_score_threshold,
                    df=df_kpis,
                ):
                    logger.info(
                        f"Sell signal detected for {self.symbol}. Z-Score: {current_row['z_score_mrat']}"
                    )
                    logger.info("Closing position..")
                    self._close_position_order(
                        symbol=self.symbol,
                        order_type=OrderType.MARKET.value,
                        margin_mode=self.trading_params.margin_mode,
                    )
                else:
                    logger.info(
                        f"No signal for {self.symbol}. Z-Score: {current_row['z_score_mrat']:.4f}"
                    )

                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Error in MRATStrategy run loop: {e}")
                await asyncio.sleep(60)
