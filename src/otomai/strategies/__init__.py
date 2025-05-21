import pydantic as pdt
import typing as T
from otomai.strategies.mrat_zscore import MratZscoreStrategy
from otomai.strategies.rsi_daily import RsiDailyStrategy

StrategyKind = T.Union[MratZscoreStrategy, RsiDailyStrategy]


class Settings(pdt.BaseModel):
    strategy: StrategyKind = pdt.Field(..., discriminator="KIND")


__all__ = ["MratZscoreStrategy", "RsiDailyStrategy"]
