#!/usr/bin/env python3

"""Bot application."""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from bonds import BondScrapper
from constants import ADMIN_ID, BOT_TOKEN, MAIN_GROUP_ID

# Globals
BOT: Bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
DISPATCHER: Dispatcher = Dispatcher()
SCRAPPER: BondScrapper = BondScrapper(bot=BOT, chat_id=MAIN_GROUP_ID)


@DISPATCHER.message(Command("runbonds"))
async def command_run_bonds_handler(message: Message) -> None:
    """Handle messages with `/runbonds` command."""
    if not message.from_user:
        return

    if message.from_user.id != ADMIN_ID:
        await message.answer(
            "You must be an admin to start the Bond Scrapper.", show_alert=True
        )
        return

    asyncio.create_task(SCRAPPER.start(message.chat.id))


@DISPATCHER.message(Command("stopbonds"))
async def command_stop_bonds_handler(message: Message) -> None:
    """Handle messages with `/stopbonds` command."""
    if not message.from_user:
        return

    if message.from_user.id != ADMIN_ID:
        await message.answer(
            "You must be an admin to start the Bond Scrapper.", show_alert=True
        )
        return

    await SCRAPPER.stop(message.chat.id)


async def main() -> None:
    """Bot main."""
    await DISPATCHER.start_polling(BOT)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(main())
