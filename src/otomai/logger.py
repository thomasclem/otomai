import logging


class Logger(logging.Logger):
    def __init__(self, name: str, level=logging.INFO, strategy_name: str = None):
        super().__init__(name, level)

        self.strategy_name = strategy_name

        if strategy_name:
            fmt = f"%(asctime)s - %(levelname)s - [{strategy_name}] - %(name)s - %(message)s"
        else:
            fmt = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"

        formatter = logging.Formatter(
            fmt=fmt,
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        self.addHandler(handler)
        self.propagate = False
        asyncio_logger = logging.getLogger("asyncio")
        if asyncio_logger.level != logging.ERROR:
            asyncio_logger.setLevel(logging.ERROR)
