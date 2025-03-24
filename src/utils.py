"""Utility functions and data classes that are used throughout the bot."""

import asyncio
import logging
from dataclasses import dataclass, fields
from datetime import datetime
from typing import List, Optional, Union

import aiohttp
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    ForceReply,
    InlineKeyboardMarkup,
    InputFile,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from solders.pubkey import Pubkey

from constants import (
    ASSOCIATED_TOKEN_PROGRAM_ID,
    MAX_FETCH_RETRIES,
    PUMP_API,
    TOKEN_PROGRAM_ID,
)

LOGGER: logging.Logger = logging.getLogger(__name__)


@dataclass
class Holder:
    """Data class to represent a holder of a token."""

    address: str
    allocation: int


@dataclass
class HoldersInfo:
    """Data class to represent the holders of a token."""

    top_holders: List[Holder]
    dev_allocation: int
    top_holders_allocation: int


@dataclass
class AssetData:
    """Data class to represent the data of a token."""

    dev_wallet: str
    dev_alloc: int
    top_holders: List[Holder]
    top_holders_allocation: int
    ca: str
    img_url: str
    name: str
    fill_time: str
    symbol: str
    twitter: Optional[str]
    telegram: Optional[str]
    website: Optional[str]
    pump: Optional[str]
    dex: str


@dataclass
class PumpCoin:
    """Data class to represent a pump coin."""

    mint: str
    name: str
    symbol: str
    description: Optional[str]
    image_uri: str
    metadata_uri: str
    twitter: Optional[str]
    telegram: Optional[str]
    bonding_curve: str
    associated_bonding_curve: str
    creator: str
    created_timestamp: int
    raydium_pool: str
    complete: bool
    virtual_sol_reserves: float
    virtual_token_reserves: float
    total_supply: float
    website: Optional[str]
    market_cap: float
    market_id: str
    usd_market_cap: float

    @classmethod
    def from_dict(cls, data: dict) -> "PumpCoin":
        """Create a PumpCoin object from a dictionary."""
        field_names = {field.name for field in fields(cls)}
        filtered_data = {
            key: value for key, value in data.items() if key in field_names
        }
        return cls(**filtered_data)


async def send_photo(
    bot: Bot,
    chat_id: int,
    photo: Union[InputFile, str],
    caption: str,
    keyboard: Optional[
        Union[
            InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply
        ]
    ] = None,
    parse_mode: ParseMode = ParseMode.HTML,
) -> Optional[Message]:
    """Send a photo to a chat with a caption and a keyboard."""
    attempts = 0
    max_attempts = MAX_FETCH_RETRIES

    while attempts < max_attempts:
        try:
            msg = await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode=parse_mode,
                reply_markup=keyboard,
            )
            return msg
        except TelegramAPIError as e:
            LOGGER.error(f"Failed to send photo: {e}")
            attempts += 1
            await asyncio.sleep(1)
    return None


async def fetch_pump_coin(mint: str) -> Optional[PumpCoin]:
    """Fetch the metadata of a pump coin from the Pump API."""
    attempts = 0
    max_attempts = MAX_FETCH_RETRIES
    url = f"{PUMP_API}/coins/{mint}"

    async with aiohttp.ClientSession() as session:
        while attempts < max_attempts:
            try:
                async with session.get(url) as response:
                    if not response.ok:
                        raise Exception(f"HTTP error! Status: {response.status}")

                    data = await response.json()
                    if not data.get("mint", None):
                        raise Exception("Invalid Data")
                    return PumpCoin.from_dict(data)
            except Exception as e:
                LOGGER.error(f"Failed to get Pump Metadata: {e}")
                attempts += 1
                await asyncio.sleep(5)
        return None


def get_token_wallet(owner: Pubkey, mint: Pubkey) -> Pubkey:
    """Get the token wallet of an owner for a given mint."""
    return Pubkey.find_program_address(
        [bytes(owner), bytes(TOKEN_PROGRAM_ID), bytes(mint)],
        ASSOCIATED_TOKEN_PROGRAM_ID,
    )[0]


def calculate_fill_time(timestamp: int) -> str:
    """Calculate the time difference between the current time and a given timestamp."""
    current_time_seconds = datetime.now().timestamp()

    time_difference_seconds = current_time_seconds - timestamp / 1000

    if time_difference_seconds >= 86400:
        time_difference_days = time_difference_seconds / 86400
        return (
            f"{int(time_difference_days)} days" if time_difference_days > 1 else "1 day"
        )
    elif time_difference_seconds >= 3600:
        time_difference_hours = time_difference_seconds / 3600
        return (
            f"{int(time_difference_hours)} hours"
            if time_difference_hours > 1
            else "1 hour"
        )
    else:
        time_difference_minutes = time_difference_seconds / 60
        return (
            f"{int(time_difference_minutes)} minutes"
            if time_difference_minutes > 1
            else "1 minute"
        )
