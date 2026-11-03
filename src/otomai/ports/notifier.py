import abc

import pydantic as pdt


class Notifier(abc.ABC, pdt.BaseModel):
    """Sends human-readable messages about the bot's activity."""

    KIND: str

    @abc.abstractmethod
    async def send_message(self, message: str) -> None: ...

    @abc.abstractmethod
    async def send_image(self, image, caption: str) -> None: ...
