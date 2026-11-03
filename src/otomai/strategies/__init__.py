from otomai.strategies.dumb_rsi import DumbRSIStrategy
from otomai.strategies.listing_volume_short import ListingVolumeShortStrategy
from otomai.strategies.mrat_zscore import MratZscoreStrategy

StrategyKind = MratZscoreStrategy | DumbRSIStrategy | ListingVolumeShortStrategy

__all__ = [
    "DumbRSIStrategy",
    "ListingVolumeShortStrategy",
    "MratZscoreStrategy",
    "StrategyKind",
]
