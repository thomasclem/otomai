"""Parameters shared by every strategy. Strategy-specific parameters live next to their strategy."""

# %% IMPORTS

import typing as T

from pydantic import BaseModel, ConfigDict, Field

from otomai.core.enums import OrderMarginMode, OrderSide, OrderType

# %% STRATEGY PARAMS


class StrategyParams(BaseModel):
    """Base class of every strategy's signal parameters."""

    name: str = Field(description="Strategy name")


# %% TRADING PARAMS


class TradingRiskParams(BaseModel):
    """Shared equity allocation and position-risk configuration, in percent units."""

    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    stop_loss_pct: float = Field(
        default=6, description="Stop loss percentage (e.g., 6 for 6%).", ge=0, le=100
    )
    take_profit_pct: float = Field(
        default=10, description="Take profit percentage (e.g., 6 for 6%).", ge=0, le=100
    )
    max_simultaneous_positions: int = Field(
        default=1, description="Maximum number of simultaneous open positions."
    )
    equity_trade_pct: float = Field(
        default=100, description="Percentage of equity to be invested in a new trade", ge=0, le=100
    )


class TradingParams(TradingRiskParams):
    """Order placement parameters of the single-order strategies."""

    model_config = ConfigDict(
        title="Trading Parameters", validate_assignment=True, allow_inf_nan=False
    )

    allowed_order_sides: set[str] = Field(
        default_factory=lambda: {OrderSide.SELL.value},
        description="Allowed order sides to be used.",
    )
    leverage: int = Field(default=1, ge=1, description="Leverage to be applied in trading.")
    sizing_basis: T.Literal["available", "equity"] = Field(
        default="available", description="Allocation base; available preserves legacy sizing."
    )
    order_type: str = Field(
        default=OrderType.MARKET.value, description="Order type: Market or Limit"
    )
    margin_mode: str = Field(
        default=OrderMarginMode.ISOLATED.value, description="Order margin mode: cross or isolated"
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
    max_retries: int = Field(default=1, description="Max order attempts", ge=1)
