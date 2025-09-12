import typing as T
import asyncio
from datetime import datetime, timezone

import pandas as pd
from pandera.typing import DataFrame

from otomai.core.enums import OrderSide
from otomai.core.parameters import ListingBackrunStrategyParams, TradingParams
from otomai.core.schemas import ListingBackrunKpiSchema
from otomai.strategies.base import Strategy
from otomai.logger import Logger

logger = Logger(__name__)

# %% STRATEGY


class ListingBackrunStrategy(Strategy):
    KIND: T.Literal["ListingBackrunStrategy"] = "ListingBackrunStrategy"

    strategy_params: ListingBackrunStrategyParams

    def _fetch_symbol_data(
        self, symbol: str, ohlcv_tf: str, ohlcv_window: int
    ) -> DataFrame[ListingBackrunKpiSchema]:
        df_candidate = self.exchange_service.fetch_ohlcv_df(
            symbol=symbol, timeframe=ohlcv_tf, window=ohlcv_window
        )
        df_btc = self.exchange_service.fetch_ohlcv_df(
            symbol="BTC/USDT:USDT", timeframe=ohlcv_tf, window=ohlcv_window
        )

        df_candidate = df_candidate.reset_index()
        df_btc = (
            df_btc[["volume", "open", "close"]]
            .rename(
                {"volume": "volume_btc", "open": "open_btc", "close": "close_btc"},
                axis=1,
            )
            .reset_index()
        )

        df = pd.merge(df_candidate, df_btc, "left", "date")
        df["volume_usdt"] = (df["close"] + df["open"]) / 2 * df["volume"]
        df["vol_open_low"] = (df["low"] - df["open"]) / df["open"] * 100
        df["vol_open_high"] = (df["high"] - df["open"]) / df["open"] * 100
        df["vol_high_low"] = (df["high"] - df["low"]) / df["low"] * 100
        df["volume_btc_usdt"] = (
            (df["close_btc"] + df["open_btc"]) / 2 * df["volume_btc"]
        )
        df["volume_usdt_btc_prop"] = df["volume_usdt"] / df["volume_btc_usdt"] * 100
        df["btc_vol"] = (df["close_btc"] - df["open_btc"]) / df["open_btc"] * 100
        df.set_index("date", inplace=True, drop=True)
        df_wo_ghost_candles = df.loc[df["vol_high_low"] >= 0.5]

        if not df_wo_ghost_candles.empty:
            return df_wo_ghost_candles.drop(
                [
                    "volume_btc",
                    "open_btc",
                    "close_btc",
                    "volume_usdt",
                    "volume_btc_usdt",
                    "vol_high_low",
                ],
                axis=1,
            )
        return pd.DataFrame()

    @staticmethod
    def _is_sell_signal(
        row: pd.Series,
        short_price_volatility_threshold: float,
        short_btc_volatility_threshold: float,
        volume_usdt_btc_prop_threshold: float,
    ) -> bool:
        below_price_drop_threshold = (
            row["vol_open_low"] <= short_price_volatility_threshold
        )
        above_btc_drop_threshold = row["btc_vol"] >= short_btc_volatility_threshold
        above_volume_usdt_btc_prop_threshold = (
            row["volume_usdt_btc_prop"] >= volume_usdt_btc_prop_threshold
        )

        return (
            below_price_drop_threshold
            & above_btc_drop_threshold
            & above_volume_usdt_btc_prop_threshold
        )

    @staticmethod
    def _is_buy_signal(
        row: pd.Series,
        long_price_volatility_threshold: float,
        long_btc_volatility_threshold: float,
        volume_usdt_btc_prop_threshold: float,
    ) -> bool:
        above_price_jump_threshold = (
            row["vol_open_high"] >= long_price_volatility_threshold
        )
        below_btc_jump_threshold = row["btc_vol"] <= long_btc_volatility_threshold
        above_volume_usdt_btc_prop_threshold = (
            row["volume_usdt_btc_prop"] >= volume_usdt_btc_prop_threshold
        )

        return (
            above_price_jump_threshold
            & below_btc_jump_threshold
            & above_volume_usdt_btc_prop_threshold
        )

    def _check_signals(
        self, row: pd.Series, strategy_params: ListingBackrunStrategyParams
    ) -> OrderSide:
        if self._is_sell_signal(
            row=row,
            short_price_volatility_threshold=strategy_params.short_price_volatility_threshold,
            short_btc_volatility_threshold=strategy_params.short_btc_volatility_threshold,
            volume_usdt_btc_prop_threshold=strategy_params.volume_usdt_btc_prop_threshold,
        ):
            return OrderSide.SELL
        elif self._is_buy_signal(
            row=row,
            long_price_volatility_threshold=strategy_params.long_price_volatility_threshold,
            long_btc_volatility_threshold=strategy_params.long_btc_volatility_threshold,
            volume_usdt_btc_prop_threshold=strategy_params.volume_usdt_btc_prop_threshold,
        ):
            return OrderSide.BUY
        else:
            return OrderSide.NONE

    async def _process_signal(
        self, symbol: str, signal: OrderSide, trading_params: TradingParams
    ):
        if signal != OrderSide.NONE:
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
                self.monitor_position(
                    symbol=symbol,
                    open_date=open_date_str,
                )
            )
            return
        return

    async def _process_candidate_symbol(
        self,
        symbol: str,
        strategy_params: ListingBackrunStrategyParams,
        trading_params: TradingParams,
    ):
        df = pd.DataFrame()
        signal = OrderSide.NONE

        while len(df) <= 1 and signal == OrderSide.NONE:
            df = self._fetch_symbol_data(
                symbol=symbol,
                ohlcv_tf=strategy_params.ohlcv_timeframe,
                ohlcv_window=strategy_params.ohlcv_window,
            )

            signal = self._check_signals(
                row=df.iloc[0], strategy_params=strategy_params
            )

            await self._process_signal(
                symbol=symbol, signal=signal, trading_params=trading_params
            )

        await self.notifier_service.send_message(
            message=(
                f"### {self.strategy_params.name} ###\n\n"
                f"Candidate {symbol} final KPIs:\n"
                f"- Open : {df.iloc[0]['open']}" + "\n"
                f"- Close : {df.iloc[0]['close']}" + "\n"
                f"- High : {df.iloc[0]['high']}" + "\n"
                f"- Low : {df.iloc[0]['low']}" + "\n"
                f"- Volatility (Open-Low) : {df.iloc[0]['vol_open_low']}" + "\n"
                f"- Volatility (Open-High) : {df.iloc[0]['vol_open_high']}" + "\n"
                f"- BTC Volatility (Open-Close) : {df.iloc[0]['btc_vol']}" + "\n"
                f"- BTC Volume proportion : {df.iloc[0]['volume_usdt_btc_prop']}"
            )
        )
        return

    async def run(self):
        exchange_symbols = await self.exchange_service.fetch_all_futures_symbol_names()

        while True:
            await asyncio.sleep(10)
            try:
                exchange_update_symbols = (
                    await self.exchange_service.fetch_all_futures_symbol_names()
                )
                exchange_new_symbols = list(
                    set(exchange_update_symbols) - set(exchange_symbols)
                )

                if exchange_new_symbols:
                    exchange_symbols = exchange_update_symbols
                    await self.notifier_service.send_message(
                        message=(
                            f"### {self.strategy_params.name} ###\n\n"
                            f"New candidate symbols found: {', '.join(exchange_new_symbols)}"
                        )
                    )
                    logger.info(
                        f"Candidates future symbols : {', '.join(exchange_new_symbols)}"
                    )

                    await asyncio.sleep(60)

                    for symbol in exchange_new_symbols:
                        if self.position_opening_available(
                            self.trading_params.max_simultaneous_positions
                        ):
                            asyncio.create_task(
                                self._process_candidate_symbol(
                                    symbol=symbol,
                                    strategy_params=self.strategy_params,
                                    trading_params=self.trading_params,
                                )
                            )

            except Exception as e:
                logger.error(f"Error in run loop: {e}")
                raise Exception
