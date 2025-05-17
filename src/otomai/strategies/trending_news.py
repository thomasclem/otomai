# %% IMPORTS

import typing as T

from otomai.core.parameters import TrendingNewsStrategyParams
from otomai.logger import Logger
from otomai.services.messaging import MessagingListenerKind
from otomai.strategies.base import Strategy

logger = Logger(__name__)

# %% STRATEGY


class TrendingNewsStrategy(Strategy):
    KIND: T.Literal["TrendingNewsStrategy"] = "TrendingNewsStrategy"

    strategy_params: TrendingNewsStrategyParams
    news_listener: MessagingListenerKind

    async def handle_news_listener_message(message: str):
        result = ""
        logger.info(result)

    async def run(self):
        while True:
            self.news_listener.on_message = self.handle_news_listener_message
            await self.telegram_listener.start_listening()
            break
