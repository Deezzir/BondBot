#!/usr/bin/env python3

"""Bot application."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bonk_bond_scrapper import BonkBondScrapper
from constants import (
    BONK_GROUP_ID,
    BONK_TOPIC_ID,
    BOT_TOKEN,
    PUMP_GROUP_ID,
    PUMP_TOPIC_ID,
    X_GROUP_ID,
)
from pump_bond_scrapper import PumpBondScrapper
from x_scrapper import XScrapper

# Globals
BOT: Bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
DISPATCHER: Dispatcher = Dispatcher()
PUMP_SCRAPPER: PumpBondScrapper = PumpBondScrapper(
    bot=BOT, chat_id=PUMP_GROUP_ID, topic_id=PUMP_TOPIC_ID
)
BONK_SCRAPPER: BonkBondScrapper = BonkBondScrapper(
    bot=BOT, chat_id=BONK_GROUP_ID, topic_id=BONK_TOPIC_ID
)
X_SCRAPPER: XScrapper = XScrapper(bot=BOT, chat_id=X_GROUP_ID, topic_id=None)


async def main() -> None:
    """Bot main."""
    asyncio.create_task(PUMP_SCRAPPER.start())
    asyncio.create_task(BONK_SCRAPPER.start())
    asyncio.create_task(X_SCRAPPER.start())
    await DISPATCHER.start_polling(BOT)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(main())
