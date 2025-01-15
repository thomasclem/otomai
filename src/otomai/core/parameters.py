# %% IMPORTS

import abc
import typing as T

from pydantic import BaseModel, Field, model_validator

from src.otomai.core.enums import OrderType, OrderMarginMode

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
    order_type: str = Field(default=OrderType.MARKET.value, description="Order type: Market or Limit")
    margin_mode: str = Field(
        default=OrderMarginMode.ISOLATED.value, description="Order margin mode: cross or isolated"
    )
    equity_trade_pct: float = Field(
        default=100, description="Percentage of equity to be invested in a new trade", ge=0, le=100
    )

    class Config:
        title = "Trading Parameters"
        description = "Settings for managing trading risk and rewards."
        validate_assignment = True

# %% STRATEGY PARAMS


class MratZscoreStrategyParams(abc.ABC, BaseModel):
    name: str = Field(default="mrat_zscore", description="Strategy name")
    fast_ma_length: int = Field(default=9, description="Fast moving average length.")
    slow_ma_length: int = Field(default=51, description="Slow moving average length.")
    filter_ma_length: int = Field(default=100, description="Filter moving average length.")
    z_score_threshold: float = Field(default=2.22, description="Fast moving average length.")
    timeframe: T.Literal["1m", "5m", "15m", "30m", "1h", "4h"] = Field(default="1h", description="Timeframe symbol")

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


StrategyParams = T.Union[
    MratZscoreStrategyParams
]
