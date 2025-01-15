import pydantic as pdt
import typing as T
from src.otomai.strategies.mrat_zscore import MratZscoreStrategy

StrategyKind = T.Union[MratZscoreStrategy]


class Settings(pdt.BaseModel):
    strategy: StrategyKind = pdt.Field(..., discriminator="KIND")


__all__ = [
    "MratZscoreStrategy",
]
