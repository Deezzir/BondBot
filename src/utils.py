"""Utility functions and data classes that are used throughout the bot."""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Literal, Optional, Tuple, Union

import aiohttp
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import (
    ForceReply,
    InlineKeyboardMarkup,
    InputFile,
    InputMediaAudio,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, computed_field, field_validator
from solders.pubkey import Pubkey
from tenacity import retry, stop_after_attempt, wait_fixed

from constants import (
    ASSOCIATED_TOKEN_PROGRAM_ID,
    JUPITER_API,
    LAUNCHLAB_API,
    MAX_FETCH_RETRIES,
    PUMP_API,
    RAPIDAPI_KEY,
    TOKEN_PROGRAM_ID,
    X_API_URL,
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
    twitter: Optional[str] = None
    telegram: Optional[str] = None
    website: Optional[str] = None
    bonding_curve: str
    associated_bonding_curve: str
    creator: str
    created_timestamp: int
    complete: bool
    virtual_sol_reserves: float
    virtual_token_reserves: float
    total_supply: float
    market_cap: float
    pool_address: Optional[str]
    usd_market_cap: float

    @field_validator("twitter", "telegram", "website", mode="before")
    @classmethod
    def _empty_string_to_none(cls, v: Any) -> Optional[str]:
        """Convert empty strings to None."""
        if not isinstance(v, str):
            return None
        return None if v.strip() == "" else v


class XUserInfo(BaseModel):
    """Data class to represent a user on X (Twitter)."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )

    username: str = Field(..., alias="screen_name")
    user_id: str = Field(..., alias="rest_id")
    user_followers: int = Field(..., validation_alias=AliasChoices("followers_count", "sub_count"))
    user_following: int = Field(alias="friends_count", default=0)
    verified: bool = Field(..., validation_alias=AliasChoices("verified", "blue_verified"))


class MediaLink(BaseModel):
    """Data class to represent a media link."""

    type: Literal["photo", "video"]
    url: str


class TweetData(BaseModel):
    """Data class to represent a tweet."""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
    )

    user: XUserInfo = Field(..., validation_alias=AliasChoices("user_info", "author"))
    post_views: int = Field(..., alias="views")
    post_likes: int = Field(..., validation_alias=AliasChoices("favorites", "likes"))
    post_replies: int = Field(..., alias="replies")
    post_retweets: int = Field(..., alias="retweets")
    post_text: str = Field(..., alias="text")
    post_id: str = Field(..., validation_alias=AliasChoices("tweet_id", "conversation_id"))
    created_at: datetime = Field(..., alias="created_at")
    media: List[MediaLink] = Field(default_factory=list, alias="media")
    review: dict = Field(default_factory=dict, alias="review")

    @classmethod
    def _pick_video(cls, variants: Any) -> Optional[str]:
        """Pick the lowest-bitrate MP4 variant."""
        if not isinstance(variants, list):
            return None
        mp4s = [
            v
            for v in variants
            if isinstance(v, dict)
            and v.get("content_type") == "video/mp4"
            and isinstance(v.get("bitrate"), int)
            and isinstance(v.get("url"), str)
        ]
        if not mp4s:
            return None
        return min(mp4s, key=lambda v: v["bitrate"])["url"]

    @field_validator("created_at", mode="before")
    @classmethod
    def _parse_twitter_dt(cls, v: Any) -> datetime:
        if isinstance(v, datetime):
            return (
                v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)
            )
        dt = datetime.strptime(str(v), "%a %b %d %H:%M:%S %z %Y")
        return dt.astimezone(timezone.utc)

    @field_validator("media", mode="before")
    @classmethod
    def _pre_media(cls, v: Any) -> List[MediaLink] | Any:
        if isinstance(v, list) and (not v or isinstance(v[0], (MediaLink, dict))):
            return v

        if not v or not isinstance(v, dict):
            return []

        out: List[MediaLink] = []

        for p in v.get("photo") or []:
            if isinstance(p, dict):
                src = p.get("media_url_https") or p.get("url")
                if isinstance(src, str):
                    out.append(MediaLink(type="photo", url=src))

        for vid in v.get("video") or []:
            if isinstance(vid, dict):
                src = cls._pick_video(vid.get("variants"))
                if isinstance(src, str):
                    out.append(MediaLink(type="video", url=src))

        return out

    @property
    @computed_field
    def post_url(self) -> str:
        """Generate the URL of the tweet."""
        return f"https://twitter.com/{self.user.username}/status/{self.post_id}"


@retry(stop=stop_after_attempt(MAX_FETCH_RETRIES), wait=wait_fixed(5), reraise=True)
async def send_video(
    bot: Bot,
    chat_id: int,
    video_url: str,
    caption: str,
    keyboard: Optional[InlineKeyboardMarkup] = None,
    parse_mode: ParseMode = ParseMode.MARKDOWN_V2,
    topic_id: Optional[int] = None,
) -> Message:
    """Send a video to a chat with a caption and a keyboard."""
    caption = cap_media_caption(caption)
    return await bot.send_video(
        chat_id=chat_id,
        message_thread_id=topic_id,
        video=video_url,
        caption=caption,
        parse_mode=parse_mode,
        reply_markup=keyboard,
    )


@retry(stop=stop_after_attempt(MAX_FETCH_RETRIES), wait=wait_fixed(5), reraise=True)
async def send_photo(
    bot: Bot,
    chat_id: int,
    photo: Union[InputFile, str],
    caption: str,
    keyboard: Optional[
        Union[InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply]
    ] = None,
    parse_mode: ParseMode = ParseMode.HTML,
    topic_id: Optional[int] = None,
) -> Optional[Message]:
    """Send a photo to a chat with a caption and a keyboard."""
    caption = cap_media_caption(caption)
    return await bot.send_photo(
        chat_id=chat_id,
        message_thread_id=topic_id,
        photo=photo,
        caption=caption,
        parse_mode=parse_mode,
        reply_markup=keyboard,
    )


@retry(stop=stop_after_attempt(MAX_FETCH_RETRIES), wait=wait_fixed(5), reraise=True)
async def send_message(
    bot: Bot,
    chat_id: int,
    text: str,
    keyboard: Optional[
        Union[InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, ForceReply]
    ] = None,
    parse_mode: ParseMode = ParseMode.HTML,
    topic_id: Optional[int] = None,
    disable_web_page_preview: bool = False,
) -> Optional[Message]:
    """Send a message to a chat with a keyboard."""
    text = cap_message_caption(text)
    return await bot.send_message(
        chat_id=chat_id,
        message_thread_id=topic_id,
        text=text,
        parse_mode=parse_mode,
        reply_markup=keyboard,
        disable_web_page_preview=disable_web_page_preview,
    )


def build_media_group(
    media: List[MediaLink],
    caption: str,
    parse_mode: ParseMode,
    max_items: int = 10,
) -> List[InputMediaAudio | InputMediaDocument | InputMediaPhoto | InputMediaVideo]:
    """Build a media group from a list of media links."""
    media_group: List[
        Union[InputMediaAudio, InputMediaDocument, InputMediaPhoto, InputMediaVideo]
    ] = []
    items = media[:max_items]

    for i, m in enumerate(items):
        with_caption = i == 0
        if m.type == "photo":
            media_group.append(
                InputMediaPhoto(
                    media=m.url,
                    caption=caption if with_caption else None,
                    parse_mode=parse_mode if with_caption else None,
                )
            )
        elif m.type == "video":
            media_group.append(
                InputMediaVideo(
                    media=m.url,
                    caption=caption if with_caption else None,
                    parse_mode=parse_mode if with_caption else None,
                )
            )
    return media_group


@retry(stop=stop_after_attempt(MAX_FETCH_RETRIES), wait=wait_fixed(5), reraise=True)
async def send_media_group(
    bot: Bot,
    chat_id: int,
    caption: str,
    media: List[MediaLink],
    parse_mode: ParseMode = ParseMode.HTML,
    topic_id: Optional[int] = None,
) -> List[Message]:
    """Send a media group to a chat."""
    caption = cap_media_caption(caption)
    media_group = build_media_group(
        media=media,
        caption=caption,
        parse_mode=ParseMode.MARKDOWN_V2,
        max_items=10,
    )
    return await bot.send_media_group(
        chat_id=chat_id,
        message_thread_id=topic_id,
        media=media_group,
    )


@retry(stop=stop_after_attempt(MAX_FETCH_RETRIES), wait=wait_fixed(5), reraise=True)
async def fetch_pump_coin(mint: str) -> Optional[PumpCoin]:
    """Fetch the metadata of a pump coin from the Pump API."""
    url = f"{PUMP_API}/coins/{mint}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise FetchError(f"HTTP error! Status: {response.status}")

            data = await response.json()
            if not data.get("mint"):
                raise FetchError("Invalid data: missing 'mint' field")

            return PumpCoin.model_validate(data)


@retry(stop=stop_after_attempt(MAX_FETCH_RETRIES), wait=wait_fixed(5), reraise=True)
async def fetch_launchlab_coin(mint: str) -> Optional[LaunchLabCoin]:
    """Fetch the metadata of a LaunchLab coin."""
    url = f"{LAUNCHLAB_API}?ids={mint}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise FetchError(f"HTTP error! Status: {response.status}")

            data = await response.json()
            if data.get("success") is False:
                raise FetchError("API error: " + data.get("error", "Unknown error"))
            if data.get("data") is None:
                raise FetchError("No data found for the given mint")

            token_data = data["data"]["rows"][0]
            return LaunchLabCoin.model_validate(token_data)


@retry(stop=stop_after_attempt(MAX_FETCH_RETRIES), wait=wait_fixed(5), reraise=True)
async def fetch_token_stats(mint: str) -> Optional[TokenStats]:
    """Fetch token statistics from the LaunchLab API."""
    url = f"{JUPITER_API}?query={mint}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise FetchError(f"HTTP error! Status: {response.status}")

            data = await response.json()
            if len(data) == 0:
                raise FetchError("No data found for the given mint")

            return TokenStats.model_validate(data[0])


@retry(stop=stop_after_attempt(2), wait=wait_fixed(1), reraise=True)
async def fetch_tweet(tweet_id: str) -> Optional[TweetData]:
    """Fetch a tweet info from Twitter API."""
    url = f"{X_API_URL}/tweet.php"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "twitter-api45.p.rapidapi.com",
    }
    params = {
        "id": tweet_id,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            if response.status != 200:
                raise FetchError(f"HTTP error! Status: {response.status}")

            data = await response.json()
            status = data.get("status")
            if status in ["error", "protected", "suspended"]:
                return None
            return TweetData.model_validate(data)


@retry(stop=stop_after_attempt(MAX_FETCH_RETRIES), wait=wait_fixed(2), reraise=True)
async def fetch_tweets(
    query: str, search_type: Literal["latest", "popular", "top"], cursor: Optional[str]
) -> Tuple[Optional[str], List[TweetData]]:
    """Fetch tweets from Twitter API."""
    url = f"{X_API_URL}/search.php"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "twitter-api45.p.rapidapi.com",
    }
    params = {
        "query": query,
        "search_type": search_type,
    }
    if cursor:
        params["cursor"] = cursor

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            if response.status != 200:
                raise FetchError(f"HTTP error! Status: {response.status}")

            data = await response.json()
            timeline = data.get("timeline") or []
            tweets = [
                TweetData.model_validate(tweet)
                for tweet in timeline
                if tweet.get("type", "") == "tweet"
            ]
            cursor = data.get("next_cursor", None)
            return cursor, tweets


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
        return f"{int(time_difference_days)} days" if time_difference_days > 1 else "1 day"
    if time_difference_seconds >= 3600:
        time_difference_hours = int(time_difference_seconds / 3600)
        return f"{time_difference_hours} hours" if time_difference_hours > 1 else "1 hour"
    time_difference_minutes = time_difference_seconds / 60
    return f"{int(time_difference_minutes)} minutes" if time_difference_minutes > 1 else "1 minute"


def escape_markdown_v2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2 parse mode."""
    escape_chars = r"_*\[\]()~`>#+-=|{}.!"
    return re.sub(rf"([{re.escape(escape_chars)}])", r"\\\1", text)


def format_currency(value: float) -> str:
    """Format a float into a currency string."""
    return f"{value:,.2f}"


def utc_aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware in UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def cap_media_caption(caption: str, max_length: int = 1024) -> str:
    """Cap the vide caption to a maximum length."""
    if len(caption) <= max_length:
        return caption
    return caption[: max_length - 3] + "..."


def cap_message_caption(caption: str, max_length: int = 4096) -> str:
    """Cap the message caption to a maximum length."""
    if len(caption) <= max_length:
        return caption
    return caption[: max_length - 3] + "..."
