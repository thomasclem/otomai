# %% IMPORTS

import asyncio
import typing as T
from datetime import datetime, timezone, timedelta

import ta
from pandera.typing import DataFrame

from otomai.core.enums import OrderSide, TradeSide, OrderType
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
        df["abs_diff_rsi"] = (df["rsi"] - df["rsi_lag"]).abs()

        return df

    @staticmethod
    def _create_signals(df: DataFrame[RsiDailyKpiSchema], rsi_threshold: float):
        rsi_filter = df["rsi"] >= rsi_threshold
        rsi_lag_filter = df["rsi_lag"] <= 72
        rsi_lag_inferior_filter = df["rsi"] >= df["rsi_lag"]
        return df.loc[rsi_filter & rsi_lag_filter & rsi_lag_inferior_filter]

    def _should_open_position(self, symbol: str):
        return (
            (len(self.exchange_service.session.fetch_positions(symbols=[symbol])) == 0)
            and (self.exchange_service.fetch_free_amount_in_balance() > 3)
            and (
                len(self.exchange_service.session.fetch_positions())
                <= self.trading_params.max_simultaneous_positions
            )
        )

    def _open_position_order(
        self,
        symbol: str,
        size: float,
        order_side: OrderSide,
        order_type: str,
        margin_mode: str,
        reduce: bool,
    ):
        ticker = self.exchange_service.session.fetch_ticker(symbol=symbol)
        last_price = float(ticker["info"]["lastPr"])
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
        self, symbol: str, order_type: str, margin_mode: str, contracts: float
    ) -> T.Dict:
        return self.exchange_service.create_order(
            symbol=symbol,
            side=OrderSide.BUY,
            amount=contracts,
            type=order_type,
            margin_mode=margin_mode,
            trade_side=TradeSide.CLOSE,
            reduce=True,
        )

    async def _process_signal(self, symbol: str, rsi: float, signal_number: int):
        if self._should_open_position(symbol=symbol):
            logger.info(f"Buy signal detected for {self.symbol}. RSI: {rsi}")
            open_date_str = str(datetime.now(timezone.utc))
            size = self.get_order_creation_amount(
                self.trading_params.equity_trade_pct, signal_number
            )
            self._open_position_order(
                symbol=self.symbol,
                size=size,
                order_side=OrderSide.BUY,
                order_type=self.trading_params.order_type,
                margin_mode=self.trading_params.margin_mode,
                reduce=False,
            )
            position = await self.monitor_position_opening(
                symbol=self.symbol,
            )

            asyncio.create_task(self.monitor_position_closing(symbol, open_date_str))

            return position
        return None

    def _monitor_running_position(
        self,
        symbol: str,
        max_position_open_days: int,
        target_intermediate_pnl_pct: float,
        intermediate_tp_size_to_close_pct: float,
    ):
        position_id = ""
        position_closed_for_exceeded_max_open_time = False
        position_closed_for_intermediate_tp = False
        while position_id:
            position = self.exchange_service.session.fetch_position(symbol)
            position_id = position.get("id", None)
            position_size = position.get("contracts", 0)
            position_ctime_utc = datetime.fromtimestamp(
                int(position["timestamp"]) / 1000
            ).replace(tzinfo=timezone.utc)
            position_pnl_percentage = position.get("percentage", 0)
            if not position_closed_for_exceeded_max_open_time:
                position_closed_for_exceeded_max_open_time = (
                    self._close_position_max_open_time(
                        symbol=symbol,
                        position_ctime_utc=position_ctime_utc,
                        position_size=position_size,
                        max_days=max_position_open_days,
                    )
                )
            if not position_closed_for_intermediate_tp:
                position_closed_for_intermediate_tp = (
                    self._close_position_intermediate_pnl_percentage(
                        symbol=symbol,
                        position_pnl_percentage=position_pnl_percentage,
                        target_pnl_percentage=target_intermediate_pnl_pct,
                        size_to_close=position_size * intermediate_tp_size_to_close_pct,
                    )
                )

    def _close_position_max_open_time(
        self,
        symbol: str,
        position_ctime_utc: datetime,
        position_size: float,
        max_days: int = 7,
    ):
        """Monitor and close positions that have been open too long."""
        try:
            if (datetime.now(timezone.utc) - position_ctime_utc) >= timedelta(
                days=max_days
            ):
                logger.info(f"Closing {symbol} due to max open time exceeded")
                self._close_position_order(
                    symbol=symbol,
                    order_type=OrderType.MARKET.value,
                    margin_mode=self.trading_params.margin_mode,
                    contracts=position_size,
                )
                return True
            return False
        except Exception as e:
            logger.error(f"Error monitoring position open delay for {symbol}: {e}")
            return False

    def _close_position_intermediate_pnl_percentage(
        self,
        symbol: str,
        position_pnl_percentage: float,
        target_pnl_percentage: float,
        size_to_close: float,
    ):
        try:
            if position_pnl_percentage >= target_pnl_percentage:
                logger.info(
                    f"Closing {symbol} due to intermediate TP: {position_pnl_percentage}%"
                )
                self._close_position_order(
                    symbol=symbol,
                    order_type=OrderType.MARKET.value,
                    margin_mode=self.trading_params.margin_mode,
                    contracts=size_to_close,
                )
                return True
            return False
        except Exception as e:
            logger.error(f"Error monitoring position PnL percentage for {symbol}: {e}")
            return False

    async def run(self):
        while True:
            try:
                df = await self.exchange_service.fetch_all_symbols_ohlcv(
                    timeframe=self.strategy_params.timeframe,
                    ohlcv_window=self.strategy_params.rsi_window + 1,
                )
                df_indicators = self._create_indicators(
                    df, rsi_window=self.strategy_params.rsi_window
                )
                df_indicators_current = (
                    df_indicators.groupby("symbol").last().reset_index()
                )
                df_signals = self._create_signals(
                    df=df_indicators_current,
                    rsi_threshold=self.strategy_params.rsi_threshold,
                )
                remaining_position_number_to_open = (
                    self.get_remaining_position_number_to_open()
                )
                df_signals_sorted = df_signals.iloc[
                    :remaining_position_number_to_open
                ].sort_values("abs_diff_rsi", ascending=False)

                for i, row in df_signals_sorted:
                    await self._process_signal(
                        symbol=row["symbol"],
                        rsi=row["rsi"],
                        signal_number=df_signals_sorted.shape[0],
                    )

            except Exception as e:
                logger.error(f"Error in MRATStrategy run loop: {e}")
                await asyncio.sleep(60)
