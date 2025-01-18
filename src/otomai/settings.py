# %% IMPORTS

import pydantic as pdt
import pydantic_settings as pdts

from otomai import strategies


# %% SETTINGS


class Settings(pdts.BaseSettings, strict=True, frozen=True, extra="forbid"):
    """ """


class MainSettings(Settings):
    strategy: strategies.StrategyKind = pdt.Field(..., discriminator="KIND")
