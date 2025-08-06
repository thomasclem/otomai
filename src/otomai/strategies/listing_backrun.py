import typing as T
import asyncio

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
        df["volume_btc_usdt"] = (
            (df["close_btc"] + df["open_btc"]) / 2 * df["volume_btc"]
        )
        df["volume_usdt_btc_prop"] = df["volume_usdt"] / df["volume_btc_usdt"] * 100
        df["btc_vol"] = (df["close_btc"] - df["open_btc"]) / df["open_btc"] * 100
        df.set_index("date", inplace=True, drop=True)

        return df.drop(
            ["volume_btc", "open_btc", "close_btc", "volume_usdt", "volume_btc_usdt"],
            axis=1,
        )

    @staticmethod
    def _is_sell_signal(
        row: pd.DataFrame,
        short_price_volatility_threshold: float,
        short_btc_volatility_threshold: float,
        volume_usdt_btc_prop_threshold: float,
    ) -> bool:
        below_price_drop_threshold = (row["low"] - row["open"]) / row[
            "open"
        ] * 100 <= short_price_volatility_threshold
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
        row: pd.DataFrame,
        long_price_volatility_threshold: float,
        long_btc_volatility_threshold: float,
        volume_usdt_btc_prop_threshold: float,
    ) -> bool:
        above_price_jump_threshold = (row["low"] - row["open"]) / row[
            "open"
        ] * 100 >= long_price_volatility_threshold
        below_btc_jump_threshold = row["btc_vol"] <= long_btc_volatility_threshold
        above_volume_usdt_btc_prop_threshold = (
            row["volume_usdt_btc_prop"] >= volume_usdt_btc_prop_threshold
        )

        return (
            above_price_jump_threshold
            & below_btc_jump_threshold
            & above_volume_usdt_btc_prop_threshold
        )

    async def _process_candidate_symbol(
        self,
        symbol: str,
        ohlcv_tf: str,
        ohlcv_window: int,
        short_price_volatility_threshold: float,
        long_price_volatility_threshold: float,
        short_btc_volatility_threshold: float,
        long_btc_volatility_threshold: float,
        volume_usdt_btc_prop_threshold: float,
        trading_params: TradingParams,
    ):
        df = self._fetch_symbol_data(
            symbol=symbol, ohlcv_tf=ohlcv_tf, ohlcv_window=ohlcv_window
        )

        while len(df) <= 2:
            df = self._fetch_symbol_data(
                symbol=symbol, ohlcv_tf=ohlcv_tf, ohlcv_window=ohlcv_window
            )
            if self._is_sell_signal(
                row=df.iloc[0],
                short_price_volatility_threshold=short_price_volatility_threshold,
                short_btc_volatility_threshold=short_btc_volatility_threshold,
                volume_usdt_btc_prop_threshold=volume_usdt_btc_prop_threshold,
            ):
                self.exchange_service.open_future_order(
                    symbol=symbol,
                    equity_trade_pct=trading_params.equity_trade_pct,
                    order_type=trading_params.order_type,
                    order_side=OrderSide.BUY,
                    margin_mode=trading_params.margin_mode,
                    leverage=trading_params.leverage,
                    take_profit_pct=trading_params.take_profit_pct,
                    stop_loss_pct=trading_params.stop_loss_pct,
                )

            if self._is_buy_signal(
                row=df.iloc[0],
                long_price_volatility_threshold=long_price_volatility_threshold,
                long_btc_volatility_threshold=long_btc_volatility_threshold,
                volume_usdt_btc_prop_threshold=volume_usdt_btc_prop_threshold,
            ):
                self.exchange_service.open_future_order(
                    symbol=symbol,
                    equity_trade_pct=trading_params.equity_trade_pct,
                    order_type=trading_params.order_type,
                    order_side=OrderSide.SELL,
                    margin_mode=trading_params.margin_mode,
                    leverage=trading_params.leverage,
                    take_profit_pct=trading_params.take_profit_pct,
                    stop_loss_pct=trading_params.stop_loss_pct,
                )

    async def run(self):
        exchange_symbols = self.exchange_service.fetch_all_futures_symbol_names()

        while True:
            try:
                exchange_update_symbols = (
                    self.exchange_service.fetch_all_futures_symbol_names()
                )
                exchange_new_symbols = list(
                    set(exchange_update_symbols) - set(exchange_symbols[:-1])
                )

                if exchange_new_symbols:
                    exchange_symbols = exchange_update_symbols
                    # await self.notifier_service.send_message(
                    #    message=(
                    #        f"### {self.strategy_params.name} ###\n\n"
                    #        f"New candidate symbols found: {''.join(exchange_new_symbols)}"
                    #    )
                    # )
                    logger.info(
                        f"Candidates future symbols : {''.join(exchange_new_symbols)}"
                    )

                    for symbol in exchange_new_symbols:
                        asyncio.create_task(
                            self._process_candidate_symbol(
                                symbol=symbol,
                                ohlcv_tf=self.strategy_params.ohlcv_timeframe,
                                ohlcv_window=self.strategy_params.ohlcv_window,
                                short_price_volatility_threshold=self.strategy_params.short_price_volatility_threshold,
                                long_price_volatility_threshold=self.strategy_params.long_price_volatility_threshold,
                                short_btc_volatility_threshold=self.strategy_params.short_btc_volatility_threshold,
                                long_btc_volatility_threshold=self.strategy_params.long_btc_volatility_threshold,
                                volume_usdt_btc_prop_threshold=self.strategy_params.volume_usdt_btc_prop_threshold,
                                trading_params=self.trading_params,
                            )
                        )

            except Exception as e:
                logger.error(f"Error in run loop: {e}")
                raise Exception
