import pydantic as pdt
import typing as T
from otomai.strategies.mrat_zscore import MratZscoreStrategy
from otomai.strategies.listing_backrun import ListingBackrunStrategy
from otomai.strategies.dumb_rsi import DumbRSIStrategy

StrategyKind = T.Union[MratZscoreStrategy, ListingBackrunStrategy, DumbRSIStrategy]


class Settings(pdt.BaseModel):
    strategy: StrategyKind = pdt.Field(..., discriminator="KIND")


__all__ = [
    "MratZscoreStrategy",
    "ListingBackrunStrategy",
    "DumbRSIStrategy",
]
