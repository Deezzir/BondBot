#!/usr/bin/env python3

"""Bot application."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bonds import BondScrapper
from constants import BOT_TOKEN, MAIN_GROUP_ID

# Globals
BOT: Bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
DISPATCHER: Dispatcher = Dispatcher()
SCRAPPER: BondScrapper = BondScrapper(bot=BOT, chat_id=MAIN_GROUP_ID)


async def main() -> None:
    """Bot main."""
    asyncio.create_task(SCRAPPER.start())
    await DISPATCHER.start_polling(BOT)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(main())
