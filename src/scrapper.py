"""Base class for scrappers."""

import asyncio
import logging
from abc import ABC
from typing import Any, Optional

from aiogram import Bot

LOGGER: logging.Logger = logging.getLogger(__name__)


class Scrapper(ABC):
    """Base class for scrappers."""

    name: str

    def __init__(self, bot: Bot, chat_id: int, topic_id: Optional[int]) -> None:
        """Initialize the Scrapper."""
        self.task: Optional[asyncio.Task[Any]] = None
        self.bot = bot
        self.chat_id = chat_id
        self.topic_id = topic_id

    async def start(self) -> None:
        """Start the Scrapper."""
        if self.task:
            return

        LOGGER.info("Starting Scrapper for %s", self.name)
        task = asyncio.create_task(self._task())
        self.task = task
        await task

    async def stop(self) -> None:
        """Stop the Bond Scrapper."""
        if self.task:
            self.task.cancel()

            try:
                await self.task
            except asyncio.CancelledError:
                pass
            finally:
                LOGGER.info("Scrapper Task was successfully cancelled for %s", self.name)
                self.task = None
        else:
            if not self.chat_id:
                return
            # await self.bot.send_message(chat_id, "Bond Scrapper is not running.")

    async def _task(self) -> None:
        """Task to be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement the _task method.")
