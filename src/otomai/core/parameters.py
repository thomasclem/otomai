# %% IMPORTS

import abc
import typing as T

from pydantic import BaseModel, Field, model_validator

from otomai.core.enums import OrderType, OrderMarginMode

# %% TRADING PARAMS


class TradingParams(abc.ABC, BaseModel):
    """
    Model for trading parameters configuration.
    """

    leverage: int = Field(default=1, description="Leverage to be applied in trading.")
    stop_loss_pct: float = Field(
        default=6, description="Stop loss percentage (e.g., 6 for 6%).", ge=0, le=100
    )
    take_profit_pct: float = Field(
        default=10, description="Take profit percentage (e.g., 6 for 6%).", ge=0, le=100
    )
    max_simultaneous_positions: int = Field(
        default=1, description="Maximum number of simultaneous open positions."
    )
    order_type: str = Field(
        default=OrderType.MARKET.value, description="Order type: Market or Limit"
    )
    margin_mode: str = Field(
        default=OrderMarginMode.ISOLATED.value,
        description="Order margin mode: cross or isolated",
    )
    equity_trade_pct: float = Field(
        default=100,
        description="Percentage of equity to be invested in a new trade",
        ge=0,
        le=100,
    )
    order_timeout: int = Field(
        default=3600,
        description="Amount of seconds before cancelling the order if not filled",
        ge=0,
    )
    safety_margin: float = Field(
        default=0.02,
        description="Margin to be substract the initial order amount because of slippage",
        ge=0,
    )
    max_retries: int = Field(
        default=1,
        description="Max order attempts",
        ge=0,
    )

    class Config:
        title = "Trading Parameters"
        description = "Settings for managing trading risk and rewards."
        validate_assignment = True


# %% STRATEGY PARAMS


class MratZscoreStrategyParams(BaseModel):
    name: str = Field(default="mrat_zscore", description="Strategy name")
    fast_ma_length: int = Field(default=9, description="Fast moving average length.")
    slow_ma_length: int = Field(default=51, description="Slow moving average length.")
    filter_ma_length: int = Field(
        default=100, description="Filter moving average length."
    )
    z_score_threshold_buy: float = Field(
        default=2.5, description="Threshold of the MRAT Z score to buy."
    )
    z_score_threshold_sell: float = Field(
        default=2.0, description="Threshold of the MRAT Z score to sell."
    )
    z_score_lookback_window: int = Field(
        default=10, description="MRAT Z-score lookback window"
    )
    tp_z_score_threshold: float = Field(
        default=2.0,
        description="Take profit percentage if z_score threshold is overcome.",
    )
    timeframe: T.Literal["1m", "5m", "15m", "30m", "1h", "4h"] = Field(
        default="1h", description="Timeframe symbol"
    )

    @model_validator(mode="before")
    def validate_moving_average_lengths(cls, values):
        fast_ma_length = values.get("fast_ma_length")
        slow_ma_length = values.get("slow_ma_length")
        filter_ma_length = values.get("filter_ma_length")

        if not (fast_ma_length < slow_ma_length < filter_ma_length):
            raise ValueError(
                "Invalid moving average lengths: "
                "fast_ma_length must be < slow_ma_length and slow_ma_length must be < filter_ma_length."
            )
        return values


class ListingBackrunStrategyParams(BaseModel):
    name: str = Field(default="listing_backrun", description="Strategy name")
    ohlcv_timeframe: T.Literal["1m", "5m", "15m", "30m", "1h", "4h"] = Field(
        default="1h", description="Timeframe for the OHLCV data"
    )
    ohlcv_window: int = Field(default=1, description="Depth for OHLCV data")
    short_price_volatility_threshold: float = Field(
        default=-20.0, description="Minimum price volatility for sell signal"
    )
    long_price_volatility_threshold: float = Field(
        default=20.0, description="Minimum price volatility for buy signal"
    )
    short_btc_volatility_threshold: float = Field(
        default=-0.3, description="Minimum BTC volatility for sell signal"
    )
    long_btc_volatility_threshold: float = Field(
        default=0.3, description="Maximum BTC volatility for buy signal"
    )
    volume_usdt_btc_prop_threshold: float = Field(
        default=0.5,
        description="Minimum volume percentage of BTC volume for sell signal",
    )


StrategyParams = T.Union[MratZscoreStrategyParams, ListingBackrunStrategyParams]
