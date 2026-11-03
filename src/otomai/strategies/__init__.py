import pydantic as pdt
import typing as T
from otomai.strategies.mrat_zscore import MratZscoreStrategy
from otomai.strategies.dumb_rsi import DumbRSIStrategy

StrategyKind = T.Union[MratZscoreStrategy, DumbRSIStrategy]


class Settings(pdt.BaseModel):
    strategy: StrategyKind = pdt.Field(..., discriminator="KIND")


__all__ = [
    "MratZscoreStrategy",
    "DumbRSIStrategy",
]
