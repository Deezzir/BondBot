"""Utility functions and data classes that are used throughout the bot."""

import asyncio
import logging
import re
from dataclasses import dataclass
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
from pydantic import BaseModel, Field
from solders.pubkey import Pubkey

from constants import (
    ASSOCIATED_TOKEN_PROGRAM_ID,
    JUPITER_API,
    LAUNCHLAB_API,
    MAX_FETCH_RETRIES,
    NOT_FOUND_IMAGE_URL,
    PUMP_API,
    TOKEN_PROGRAM_ID,
)

LOGGER: logging.Logger = logging.getLogger(__name__)


class FetchError(Exception):
    """Custom exception for Pump API errors."""


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


class TradeStats(BaseModel):
    """Data class to represent the trade statistics of a token."""

    price_change: float = Field(0, alias="priceChange")
    holder_change: float = Field(0, alias="holderChange")
    liquidity_change: float = Field(0, alias="liquidityChange")
    buy_volume: float = Field(0, alias="buyVolume")
    sell_volume: float = Field(0, alias="sellVolume")
    buy_organic_volume: float = Field(0, alias="buyOrganicVolume")
    sell_organic_volume: float = Field(0, alias="sellOrganicVolume")
    num_buys: int = Field(0, alias="numBuys")
    num_sells: int = Field(0, alias="numSells")
    num_traders: int = Field(0, alias="numTraders")
    num_organic_buyers: int = Field(0, alias="numOrganicBuyers")
    num_net_buyers: int = Field(0, alias="numNetBuyers")


class TokenStats(BaseModel):
    """Data class to represent the statistics of a token."""

    circ_supply: float = Field(..., alias="circSupply")
    total_supply: float = Field(..., alias="totalSupply")
    launchpad: str = Field(..., alias="launchpad")
    holder_count: int = Field(..., alias="holderCount")
    organic_score_label: str = Field(..., alias="organicScoreLabel")
    stats_1h: Optional[TradeStats] = Field(None, alias="stats1h")
    stats_6h: Optional[TradeStats] = Field(None, alias="stats6h")
    stats_24h: Optional[TradeStats] = Field(None, alias="stats24h")


class TokenAssetData(BaseModel):
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
    platform: Optional[str]
    dex: str
    stats: Optional[TokenStats] = None


class LaunchLabCoin(BaseModel):
    """Data class to represent a LaunchLab coin."""

    mint: str = Field(..., alias="mint")
    name: str = Field(..., alias="name")
    symbol: str = Field(..., alias="symbol")
    description: Optional[str] = Field(None, alias="description")
    pool_id: str = Field(..., alias="poolId")
    creator: str = Field(..., alias="creator")
    created_at: int = Field(..., alias="createAt")
    img_url: str = Field(..., alias="imgUrl")
    metadata_url: str = Field(..., alias="metadataUrl")
    website: Optional[str] = Field(None, alias="website")
    twitter: Optional[str] = Field(None, alias="twitter")
    telegram: Optional[str] = Field(None, alias="telegram")


class PumpCoin(BaseModel):
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
    raydium_pool: Optional[str]
    complete: bool
    virtual_sol_reserves: float
    virtual_token_reserves: float
    total_supply: float
    website: Optional[str]
    market_cap: float
    market_id: Optional[str]
    usd_market_cap: float


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
    topic_id: Optional[int] = None,
) -> Optional[Message]:
    """Send a photo to a chat with a caption and a keyboard."""
    attempts = 0
    max_attempts = MAX_FETCH_RETRIES

    while attempts < max_attempts:
        try:
            msg = await bot.send_photo(
                chat_id=chat_id,
                message_thread_id=topic_id,
                photo=photo,
                caption=caption,
                parse_mode=parse_mode,
                reply_markup=keyboard,
            )
            return msg
        except TelegramAPIError as e:
            LOGGER.error("Failed to send photo: %s", e)
            if "ClientOSError: [Errno -2]" in e.message:
                photo = NOT_FOUND_IMAGE_URL
                LOGGER.warning("Using default image URL.")
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
                    if response.status != 200:
                        raise FetchError(f"HTTP error! Status: {response.status}")

                    data = await response.json()
                    if not data.get("mint"):
                        raise FetchError("Invalid data: missing 'mint' field")

                    return PumpCoin.model_validate(data)

            except (aiohttp.ClientError, FetchError, asyncio.TimeoutError) as e:
                LOGGER.error(
                    "Failed to get Pump Metadata (attempt %d): %s", attempts + 1, e
                )
                attempts += 1
                await asyncio.sleep(5)
    return None


async def fetch_launchlab_coin(mint: str) -> Optional[LaunchLabCoin]:
    """Fetch the metadata of a LaunchLab coin."""
    attempts = 0
    max_attempts = MAX_FETCH_RETRIES
    url = f"{LAUNCHLAB_API}?ids={mint}"

    async with aiohttp.ClientSession() as session:
        while attempts < max_attempts:
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise FetchError(f"HTTP error! Status: {response.status}")

                    data = await response.json()
                    if data.get("success") is False:
                        raise FetchError(
                            "API error: " + data.get("error", "Unknown error")
                        )
                    if data.get("data") is None:
                        raise FetchError("No data found for the given mint")

                    token_data = data["data"]["rows"][0]
                    return LaunchLabCoin.model_validate(token_data)

            except (aiohttp.ClientError, FetchError, asyncio.TimeoutError) as e:
                LOGGER.error(
                    "Failed to get LaunchLab Metadata (attempt %d): %s", attempts + 1, e
                )
                attempts += 1
                await asyncio.sleep(5)
    return None


async def fetch_token_stats(mint: str) -> Optional[TokenStats]:
    """Fetch token statistics from the LaunchLab API."""
    attempts = 0
    max_attempts = MAX_FETCH_RETRIES
    url = f"{JUPITER_API}?query={mint}"

    async with aiohttp.ClientSession() as session:
        while attempts < max_attempts:
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise FetchError(f"HTTP error! Status: {response.status}")

                    data = await response.json()
                    if len(data) == 0:
                        raise FetchError("No data found for the given mint")
                    return TokenStats.model_validate(data[0])

            except (aiohttp.ClientError, FetchError, asyncio.TimeoutError) as e:
                LOGGER.error(
                    "Failed to get Token Stats (attempt %d): %s", attempts + 1, e
                )
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
    if time_difference_seconds >= 3600:
        time_difference_hours = int(time_difference_seconds / 3600)
        return (
            f"{time_difference_hours} hours" if time_difference_hours > 1 else "1 hour"
        )
    time_difference_minutes = time_difference_seconds / 60
    return (
        f"{int(time_difference_minutes)} minutes"
        if time_difference_minutes > 1
        else "1 minute"
    )


def escape_markdown_v2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2 parse mode."""
    escape_chars = r"_*\[\]()~`>#+-=|{}.!"
    return re.sub(rf"([{re.escape(escape_chars)}])", r"\\\1", text)


def format_currency(value: float) -> str:
    """Format a float into a currency string."""
    return f"{value:,.2f}"
