import abc
import os
import typing as T

import telegram
from telegram.request import HTTPXRequest
import pydantic as pdt


class Notifier(abc.ABC, pdt.BaseModel):
    KIND: str

    @abc.abstractmethod
    async def send_message(self, message: str):
        raise NotImplementedError("Subclasses must implement `send_message`.")

    @abc.abstractmethod
    async def send_image(self, image, caption: str):
        raise NotImplementedError("Subclasses must implement `send_image`.")


class TelegramNotifier(Notifier):
    KIND: T.Literal["Telegram"] = "Telegram"

    chat_id: T.Union[str, int] = "5609154988"
    bot: T.Any = None

    def __init__(self, **data):
        super().__init__(**data)

        request_config = HTTPXRequest(
            connection_pool_size=20,
            pool_timeout=60.0,
        )

        self.bot = telegram.Bot(
            token=os.getenv(f"{self.KIND.upper()}_API_KEY"), request=request_config
        )

    async def send_message(self, message: str):
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=message)
        except telegram.error.TimedOut:
            pass
        except Exception as e:
            print(f"Telegram error: {e}")

    async def send_image(self, image, message: str):
        """
        Send the notification message
        :return:
        """
        try:
            await self.bot.send_photo(
                chat_id=self.chat_id, photo=image, caption=message
            )
        except telegram.error.TimedOut:
            pass
        except Exception as e:
            print(f"Telegram error: {e}")
