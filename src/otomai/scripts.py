# %% IMPORTS
import argparse

import settings
import configs

# %% PARSER


parser = argparse.ArgumentParser(
    description="Run trading bot strategy from YAML/JSON configs"
)
parser.add_argument("files", nargs="*", help="Config files for the strategy to run")

# %% SCRIPTS


async def main(argv: list[str] | None = None):
    args = parser.parse_args(argv)
    configs.load_dotenv()
    files = [configs.parse_file(file) for file in args.files]
    if len(files) == 0:
        raise RuntimeError("No config provided")
    config = configs.merge_configs(files)
    object_ = configs.to_object(config)
    setting = settings.MainSettings.model_validate(object_)
    with setting.strategy as runner:
        await runner.run()
