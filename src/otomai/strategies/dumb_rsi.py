import asyncio
import ta
import typing as T
from datetime import datetime, timezone

import pandas as pd

from otomai.strategies.base import Strategy
from otomai.core.parameters import DumbRSIStrategyParams, TradingParams
from otomai.core.enums import OrderSide
from otomai.logger import Logger

logger = Logger(__name__)

SCAN_INTERVAL_SECONDS = 60


class DumbRSIStrategy(Strategy):
    KIND: T.Literal["DumbRSIStrategy"] = "DumbRSIStrategy"

    strategy_params: DumbRSIStrategyParams

    # --- DATA ---

    async def _fetch_data(
        self, ohlcv_tf: str, ohlcv_window: int
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data for all symbols and compute RSI.
        Returns one row per symbol (the latest candle).
        """
        df = await self.exchange_service.fetch_all_symbols_ohlcv_df(
            timeframe=ohlcv_tf, ohlcv_window=ohlcv_window
        )

        df = df[df["volume"] > 0]

        df["rsi"] = df.groupby("symbol")["close"].transform(
            lambda x: ta.momentum.rsi(x, window=self.strategy_params.rsi_window)
        )

        return df.groupby("symbol").last().reset_index()

    # --- SIGNALS ---

    @staticmethod
    def _check_signal(
        row: pd.Series,
        rsi_oversold_threshold: float,
        rsi_overbought_threshold: float,
    ) -> OrderSide:
        """
        Check RSI signal for a single symbol row.
        """
        if row["rsi"] < rsi_oversold_threshold:
            return OrderSide.SELL
        elif row["rsi"] > rsi_overbought_threshold:
            return OrderSide.BUY
        return OrderSide.NONE

    def _find_candidates(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Find all candidate symbols with an active signal, sorted by signal strength.
        For SELL: lowest RSI first. For BUY: highest RSI first.
        """
        df = df.dropna(subset=["rsi"]).copy()
        df["signal"] = df.apply(
            lambda row: self._check_signal(
                row,
                rsi_oversold_threshold=self.strategy_params.rsi_oversold_threshold,
                rsi_overbought_threshold=self.strategy_params.rsi_overbought_threshold,
            ),
            axis=1,
        )
        candidates = df[df["signal"] != OrderSide.NONE].copy()
        # Sort: oversold (SELL) by lowest RSI first, overbought (BUY) by highest RSI first
        candidates = candidates.sort_values(by="rsi", ascending=True)
        logger.info(f"Df sample: {df.sort_values(by="rsi", ascending=True).head(5)}")
        return candidates.iloc[:1]

    # --- ORDER PROCESSING ---

    async def _process_signal(
        self, symbol: str, signal: OrderSide, trading_params: TradingParams
    ):
        """
        Open an order if the signal is in allowed_order_sides, then monitor the position.
        """
        if signal == OrderSide.NONE:
            return
        if str(signal.value) not in trading_params.allowed_order_sides:
            logger.info(f"Signal {signal.value} for {symbol} not in allowed_order_sides, skipping.")
            return

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
            safety_margin=trading_params.safety_margin,
            max_retries=trading_params.max_retries,
        )

        await self.notifier_service.send_message(
            message=(
                f"### {self.strategy_params.name} ###\n\n"
                f"✅ Order successfully posted for {symbol}.\n\n"
                f"ℹ️ Order info: {order}.\n\n"
                f"⏭️ Start monitoring position opening.."
            )
        )

        asyncio.create_task(
            self.position_monitor.monitor_position(
                symbol=symbol,
                open_date=open_date_str,
            )
        )

    async def _process_candidate_symbol(
        self,
        symbol: str,
        signal: OrderSide,
        rsi_value: float,
        strategy_params: DumbRSIStrategyParams,
        trading_params: TradingParams,
    ):
        """
        Process a single candidate symbol: log KPIs, then open the order.
        """
        await self.notifier_service.send_message(
            message=(
                f"### {strategy_params.name} ###\n\n"
                f"Candidate {symbol} KPIs:\n"
                f"- RSI: {rsi_value:.2f}\n"
                f"- Signal: {signal.value}\n"
                f"- Threshold (oversold): {strategy_params.rsi_oversold_threshold}\n"
                f"- Threshold (overbought): {strategy_params.rsi_overbought_threshold}"
            )
        )

        await self._process_signal(
            symbol=symbol, signal=signal, trading_params=trading_params
        )

    # --- RUN LOOP ---

    async def run(self):
        while True:
            try:
                logger.info("Scanning for RSI signals...")
                df = await self._fetch_data(
                    ohlcv_tf=self.strategy_params.rsi_timeframe,
                    ohlcv_window=self.strategy_params.rsi_window,
                )

                candidates = self._find_candidates(df)

                if candidates.empty:
                    logger.info(
                        f"No candidates found "
                        f"(oversold<{self.strategy_params.rsi_oversold_threshold} "
                        f"/ overbought>{self.strategy_params.rsi_overbought_threshold})"
                    )
                else:
                    logger.info(
                        f"Found {len(candidates)} candidate(s):\n"
                        f"{candidates[['symbol', 'rsi', 'close', 'signal']].to_string()}"
                    )

                    for _, row in candidates.iterrows():
                        if not self.position_opening_available(
                            self.trading_params.max_simultaneous_positions
                        ):
                            logger.info("Max simultaneous positions reached, stopping candidate processing.")
                            break

                        asyncio.create_task(
                            self._process_candidate_symbol(
                                symbol=row["symbol"],
                                signal=row["signal"],
                                rsi_value=row["rsi"],
                                strategy_params=self.strategy_params,
                                trading_params=self.trading_params,
                            )
                        )

            except Exception as e:
                logger.error(f"Error in DumbRSI run loop: {e}")

            await asyncio.sleep(SCAN_INTERVAL_SECONDS)
