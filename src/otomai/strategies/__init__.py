import pydantic as pdt
import typing as T
from otomai.strategies.mrat_zscore import MratZscoreStrategy
from otomai.strategies.listing_backrun import ListingBackrunStrategy

StrategyKind = T.Union[MratZscoreStrategy, ListingBackrunStrategy]


class Settings(pdt.BaseModel):
    strategy: StrategyKind = pdt.Field(..., discriminator="KIND")


__all__ = [
    "MratZscoreStrategy",
    "ListingBackrunStrategy",
]
