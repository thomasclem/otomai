import logging


class Logger(logging.Logger):
    def __init__(self, name: str, level=logging.INFO):
        super().__init__(name, level)

        # Add a formatter
        formatter = logging.Formatter(
            fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Add a stream handler
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        self.addHandler(handler)
        self.propagate = False
        asyncio_logger = logging.getLogger("asyncio")
        if asyncio_logger.level != logging.ERROR:
            asyncio_logger.setLevel(logging.ERROR)
