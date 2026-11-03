"""Configuration of the listing-volume short."""

from pydantic import ConfigDict, Field, field_validator, model_validator

from otomai.core.parameters import StrategyParams, TradingRiskParams


class ListingVolumeStrategyParams(StrategyParams):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    name: str = "listing_volume_short"
    decision_hours: int = Field(default=4, ge=1, le=24)
    volume_multiplier: float = Field(default=2.0, gt=0)
    reference_listings: int = Field(default=30, ge=10, le=100)
    min_reference_listings: int = Field(default=10, ge=1)
    entry_grace_seconds: int = Field(default=120, ge=1, le=600)
    holding_hours: int = Field(default=504, ge=1)
    poll_seconds: float = Field(default=30, ge=1)
    history_batch_size: int = Field(default=10, ge=1, le=100)
    bootstrap_listings: int = Field(default=60, ge=30, le=1000)
    # Research universe: crypto perpetuals only. Exchange-flagged TradFi contracts are
    # always excluded; these commodity-pegged tokens are excluded by base asset.
    excluded_bases: tuple[str, ...] = ("PAXG", "XAUT")
    # Trading before the launch hour marks a relaunch or early start, not a new listing.
    prelisting_lookback_hours: int = Field(default=24, ge=1, le=168)
    state_path: str = "data/listing_volume_short.live.sqlite"

    @field_validator("excluded_bases")
    @classmethod
    def normalize_bases(cls, bases):
        return tuple(sorted({b.strip().upper() for b in bases}))

    @model_validator(mode="after")
    def validate_reference_window(self):
        if self.min_reference_listings > self.reference_listings:
            raise ValueError("min_reference_listings must not exceed reference_listings")
        if self.bootstrap_listings < self.reference_listings:
            raise ValueError("bootstrap_listings must cover reference_listings")
        return self


class ListingVolumeRiskParams(TradingRiskParams):
    """Size is entry notional, not margin; caps apply when a position is admitted."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    equity_trade_pct: float = Field(default=5, gt=0, le=100)
    max_simultaneous_positions: int = Field(default=6, ge=1)
    stop_loss_pct: float = Field(default=20, gt=0, lt=100)
    take_profit_pct: float = Field(default=60, gt=0, lt=100)
    max_gross_exposure_pct: float = Field(default=30, gt=0, le=100)
    max_listing_day_pct: float = Field(default=10, gt=0, le=100)
    max_spread_bps: float = Field(default=50, gt=0)
    max_book_participation: float = Field(default=0.01, gt=0, le=1)
    max_entry_slippage_bps: float = Field(default=50, gt=0)
