import abc
import os
import typing as T

import telegram
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import pydantic as pdt

from otomai.logger import Logger

logger = Logger(__name__)

# %% NOTIFIER


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


MessagingNotifierKind = T.Union[TelegramNotifier]
# %% LISTENER


class Listener(abc.ABC, pdt.BaseModel):
    """
    Abstract base class for listeners.
    Subclasses must implement a method for starting the listening process.
    """

    KIND: str

    @abc.abstractmethod
    async def start_listening(self):
        """Starts listening to the configured source (e.g., channel, queue)."""
        raise NotImplementedError("Subclasses must implement `start_listening`.")


class TelegramListener(Listener):
    """
    Concrete implementation of Listener for Telegram channels.
    Uses the python-telegram-bot library to listen for messages in a channel.
    """

    KIND: T.Literal["Telegram"] = "Telegram"

    channel_id: T.Union[str, int] = "@wublockchainenglish"
    bot_token: str = pdt.Field(
        default_factory=lambda: os.getenv(f"{TelegramListener.KIND.upper()}_API_KEY")
    )

    on_message: T.Optional[T.Callable[[str], T.Awaitable[None]]] = None

    _application: T.Optional[Application] = pdt.PrivateAttr(default=None)

    async def _handle_channel_message(
        self, update: telegram.Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """
        Internal handler for processing incoming channel messages.
        Calls the user-provided on_message callback if set.
        """
        if (
            update.channel_post and update.channel_post.text
        ):  # Ensure it's a channel post with text
            message_text = update.channel_post.text
            logger.info(
                f"Received message in channel {self.channel_id}: {message_text[:100]}..."
            )  # Log snippet

            if self.on_message:
                try:
                    await self.on_message(message_text)
                except Exception as e:
                    logger.error(
                        f"Error processing message with on_message callback: {e}",
                        exc_info=True,
                    )
            else:
                logger.debug("No on_message callback set for TelegramListener.")

    async def start_listening(self):
        """
        Starts the Telegram bot to listen for messages in the configured channel.
        """
        if not self.bot_token:
            logger.error(
                f"Telegram bot token not provided or found in {self.KIND.upper()}_API_KEY environment variable."
            )
            raise ValueError(
                f"Telegram bot token not provided or found in {self.KIND.upper()}_API_KEY environment variable."
            )

        self._application = Application.builder().token(self.bot_token).build()

        channel_message_handler = MessageHandler(
            filters.Chat(chat_id=self.channel_id) & filters.TEXT,
            self._handle_channel_message,
        )
        self._application.add_handler(channel_message_handler)

        logger.info(f"Starting Telegram listener for channel: {self.channel_id}")
        try:
            await self._application.run_polling(poll_interval=3.0, stop_signals=None)
        except Exception as e:
            logger.critical(
                f"Telegram listener encountered a critical error: {e}", exc_info=True
            )
        finally:
            logger.info(f"Telegram listener for channel {self.channel_id} stopped.")


MessagingListenerKind = T.Union[TelegramListener]
