import abc
import os
import typing as T

import telegram
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
    bot: T.Any = telegram.Bot(token=os.getenv(f"{KIND.upper()}_API_KEY"))

    async def send_message(self, message: str):
        await self.bot.send_message(chat_id=self.chat_id, text=message)

    async def send_image(self, image, message: str):
        """
        Send the notification message
        :return:
        """
        await self.bot.send_photo(chat_id=self.chat_id, photo=image, caption=message)

