from otomai.strategies.dumb_rsi import DumbRSIStrategy
from otomai.strategies.mrat_zscore import MratZscoreStrategy

StrategyKind = MratZscoreStrategy | DumbRSIStrategy

__all__ = [
    "DumbRSIStrategy",
    "MratZscoreStrategy",
    "StrategyKind",
]
