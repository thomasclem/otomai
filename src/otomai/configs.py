import os
import typing as T
from otomai.logger import Logger

import omegaconf as oc
import cloudpathlib as cpl
from dotenv import load_dotenv

logger = Logger(__name__)

# %% TYPES

Config = oc.DictConfig | oc.ListConfig

# %% PARSERS


def parse_file(path: str) -> Config:
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
    """
    Load environment variables from base and specific environment files.
    """
    base_env_path = "env/base.env"
    specific_env_path = f"env/{os.getenv('ENV', 'dev')}.env"

    load_dotenv(dotenv_path=base_env_path)

    if os.path.exists(specific_env_path):
        load_dotenv(dotenv_path=specific_env_path, override=True)
    else:
        logger.error(f"{specific_env_path} do not exist.")
