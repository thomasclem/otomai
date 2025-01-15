# %% IMPORTS

import pydantic as pdt
import pydantic_settings as pdts

from src.otomai.strategies import StrategyKind


# %% SETTINGS

class Settings(pdts.BaseSettings, strict=True, frozen=True, extra="forbid"):
    """
    """


class MainSettings(Settings):
    strategy: StrategyKind = pdt.Field(..., discriminator="KIND")
