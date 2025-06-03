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
    def _is_buy_signal(row: pd.Series, z_score_threshold: float) -> bool:
        return (row["z_score_mrat"] <= -z_score_threshold) and (
            row["filter_ma"] < row["slow_ma"]
        )

    def _is_sell_signal(
        self,
        symbol: str,
        row: pd.Series,
        z_score_threshold: float,
        tp_z_score_threshold: float,
    ) -> bool:
        position = self.exchange_service.session.fetch_position(symbol=symbol)
        position_percentage = float(position.get("percentage", 0.0))
        return (row["z_score_mrat"] >= z_score_threshold) and (
            position_percentage >= tp_z_score_threshold
        )

    def _get_order_creation_amount(self, equity_trade_pct: float) -> float:
        try:
            balance = self.exchange_service.session.fetch_balance()
            free_amount = balance["USDT"]["free"]
            return free_amount * equity_trade_pct / 100
        except Exception as e:
            logger.error(f"Error calculating new position amount: {e}")
            return 0.0

    def _should_open_position(self, current_row: pd.Series, z_score_threshold: float):
        return (
            self._is_buy_signal(current_row, z_score_threshold)
            # open if no position exist
            and len(
                self.exchange_service.session.fetch_positions(symbols=[self.symbol])
            )
            == 0
            # open if no creation order exist
            and len(self.exchange_service.session.fetch_open_orders(symbol=self.symbol))
            == 0
        )

    def _should_close_position(
        self,
        symbol: str,
        current_row: pd.Series,
        z_score_threshold: float,
        tp_z_score_threshold: float,
    ):
        return (
            self._is_sell_signal(
                symbol=symbol,
                row=current_row,
                z_score_threshold=z_score_threshold,
                tp_z_score_threshold=tp_z_score_threshold,
            )
            # close if a position exist only
            and len(
                self.exchange_service.session.fetch_positions(symbols=[self.symbol])
            )
            == 1
            # close if there is no current closing order
            and len(self.exchange_service.session.fetch_open_orders(symbol=self.symbol))
            == 0
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

                # Check signals
                if self._should_open_position(
                    current_row, self.strategy_params.z_score_threshold
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
                    row=current_row,
                    z_score_threshold=self.strategy_params.z_score_threshold,
                    tp_z_score_threshold=self.strategy_params.tp_z_score_threshold,
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
                        f"No signal for {self.symbol}. Z-Score: {current_row['z_score_mrat']}"
                    )

                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Error in MRATStrategy run loop: {e}")
                await asyncio.sleep(60)
