import os
import typing as T

import omegaconf as oc
from dotenv import dotenv_values

from otomai.logger import Logger

logger = Logger(__name__)

# %% TYPES

Config = oc.DictConfig | oc.ListConfig

# %% PARSERS


def parse_file(path: str) -> Config:
    import cloudpathlib as cpl

    any_path = cpl.AnyPath(path)
    text: str = any_path.read_text()
    return oc.OmegaConf.create(text)


def parse_string(string: str) -> Config:
    return oc.OmegaConf.create(string)


# %% MERGERS


def merge_configs(configs: T.Sequence[Config]) -> Config:
    return oc.OmegaConf.merge(*configs)


# %% CONVERTERS


def to_object(config: Config, resolve: bool = True) -> object:
    return oc.OmegaConf.to_container(config, resolve=resolve)


# %% ENVIRONMENT


def load_env():
    """Merge optional environment files without overriding injected process values."""
    import pathlib

    env_root = pathlib.Path(
        os.getenv("OTOMAI_ENV_DIR", pathlib.Path(__file__).parent.parent.parent / "env")
    )
    base = dotenv_values(env_root / "base.env")
    strategy = os.getenv("STRATEGY", base.get("STRATEGY") or "mrat_zscore")
    environment = os.getenv("ENV", base.get("ENV") or "dev")
    specific = dotenv_values(env_root / strategy / f"{environment}.env")
    for name, value in {**base, **specific}.items():
        if value is not None:
            os.environ.setdefault(name, value)
