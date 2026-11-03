"""Notifier adapters: console logs and Telegram."""

import os
import typing as T

import pydantic as pdt
import telegram
from telegram.request import HTTPXRequest

from otomai.ports.notifier import Notifier


class ConsoleNotifier(Notifier):
    """Credential-free notifier that writes to the logs."""

    KIND: T.Literal["Console"] = "Console"

    async def send_message(self, message: str):
        print(message)

    async def send_image(self, image, caption: str):
        print(f"{caption}: {image}")


class TelegramNotifier(Notifier):
    KIND: T.Literal["Telegram"] = "Telegram"

    chat_id: str | int = "5609154988"
    bot: T.Any = pdt.Field(default=None, repr=False, exclude=True)

    def _get_bot(self):
        if self.bot is None:
            request_config = HTTPXRequest(connection_pool_size=20, pool_timeout=60.0)
            self.bot = telegram.Bot(
                token=os.getenv(f"{self.KIND.upper()}_API_KEY"), request=request_config
            )
        return self.bot

    async def send_message(self, message: str):
        try:
            await self._get_bot().send_message(chat_id=self.chat_id, text=message)
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
            await self._get_bot().send_photo(chat_id=self.chat_id, photo=image, caption=message)
        except telegram.error.TimedOut:
            pass
        except Exception as e:
            print(f"Telegram error: {e}")


NotifierKind = ConsoleNotifier | TelegramNotifier
