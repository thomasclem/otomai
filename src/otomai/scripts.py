"""Configuration-driven strategy entrypoint."""

import argparse
import asyncio

from otomai import configs, settings
from otomai.configs import logger

parser = argparse.ArgumentParser(description="Run trading bot strategy from YAML/JSON configs")
parser.add_argument("--files", nargs="*", help="Config files for the strategy to run")
parser.add_argument(
    "--check-config",
    action="store_true",
    help="Validate settings without entering the strategy or submitting orders",
)


def main(argv: list[str] | None = None):
    args = parser.parse_args(argv)
    configs.load_env()
    files = [configs.parse_file(file) for file in (args.files or [])]
    if not files:
        raise RuntimeError("No config provided")
    setting = settings.MainSettings.model_validate(configs.to_object(configs.merge_configs(files)))
    strategy = setting.strategy
    if args.check_config:
        logger.info(f"Configuration valid: {strategy.strategy_params.name} ({strategy.KIND})")
        return
    with strategy as runner:
        logger.info(f"Starting strategy: {runner.strategy_params.name} ({runner.KIND})")
        asyncio.run(runner.run())


if __name__ == "__main__":
    main()
