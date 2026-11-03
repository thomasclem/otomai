import asyncio
import typing as T

import pandas as pd
import ta
from pydantic import Field

from otomai.core.enums import OrderSide
from otomai.core.parameters import StrategyParams, TradingParams
from otomai.logger import Logger
from otomai.strategies.base import Strategy

logger = Logger(__name__)

SCAN_INTERVAL_SECONDS = 60

# %% PARAMS


class DumbRSIStrategyParams(StrategyParams):
    name: str = Field(default="dumb_rsi", description="Strategy name")
    ohlcv_window: int = Field(default=1, description="Depth for OHLCV data")
    rsi_window: int = Field(default=14, description="RSI window")
    rsi_overbought_threshold: int = Field(default=70, description="RSI overbought threshold")
    rsi_oversold_threshold: int = Field(default=30, description="RSI oversold threshold")
    rsi_timeframe: T.Literal["1m", "5m", "15m", "30m", "1h", "4h"] = Field(
        default="1h", description="Timeframe for the RSI data"
    )


# %% STRATEGY


class DumbRSIStrategy(Strategy):
    KIND: T.Literal["DumbRSIStrategy"] = "DumbRSIStrategy"

    strategy_params: DumbRSIStrategyParams
    trading_params: TradingParams

    # --- DATA ---

    async def _fetch_data(self, ohlcv_tf: str, ohlcv_window: int) -> pd.DataFrame:
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
        """The single symbol with the lowest RSI among those with a signal."""
        df = df.dropna(subset=["rsi"]).copy()
        df["signal"] = df.apply(
            lambda row: self._check_signal(
                row,
                rsi_oversold_threshold=self.strategy_params.rsi_oversold_threshold,
                rsi_overbought_threshold=self.strategy_params.rsi_overbought_threshold,
            ),
            axis=1,
        )
        candidates = df[df["signal"] != OrderSide.NONE].sort_values(by="rsi", ascending=True)
        logger.info(f"Df sample: {df.sort_values(by='rsi', ascending=True).head(5)}")
        return candidates.iloc[:1]

    # --- ORDER PROCESSING ---

    async def _process_signal(self, symbol: str, signal: OrderSide, trading_params: TradingParams):
        """Open a position if the signal side is allowed; the base class monitors it."""
        if signal == OrderSide.NONE:
            return
        if str(signal.value) not in trading_params.allowed_order_sides:
            logger.info(f"Signal {signal.value} for {symbol} not in allowed_order_sides, skipping.")
            return
        await self.open_position(symbol, signal)

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

        await self._process_signal(symbol=symbol, signal=signal, trading_params=trading_params)

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
                            logger.info(
                                "Max simultaneous positions reached, stopping candidate processing."
                            )
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
