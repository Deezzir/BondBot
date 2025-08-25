"""X Scrapper module."""

import asyncio
import logging
import time
from datetime import datetime
from typing import List, Optional

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from constants import (
    X_FILTER_POST_MIN_VIEWS,
    X_FILTER_USER_MAX_FOLLOWERS,
    X_SCRAPPER_FETCH_INTERVAL,
    X_SCRAPPER_MAX_FAVES,
    X_SCRAPPER_MAX_REPLIES,
    X_SCRAPPER_MAX_RETWEETS,
    X_SCRAPPER_MIN_FAVES,
    X_SCRAPPER_MIN_REPLIES,
    X_SCRAPPER_MIN_RETWEETS,
)
from db import insert_tweet_if_not_exists
from scrapper import Scrapper
from utils import (
    TweetData,
    build_media_group,
    escape_markdown_v2,
    fetch_tweets,
    send_message,
    send_photo,
    send_video,
    utc_aware,
)

LOGGER: logging.Logger = logging.getLogger(__name__)


class XScrapper(Scrapper):
    """X Scrapper class."""

    name: str = "X Scrapper"
    query_format: str = (
        "min_retweets:{min_retweets} "
        "min_faves:{min_faves} "
        "min_replies:{min_replies} "
        "-min_replies:{max_replies} "
        "-min_retweets:{max_retweets} "
        "-min_faves:{max_faves} "
        "-filter:nativeretweets "
        "-filter:retweets "
        "-filter:replies "
        "within_time:60min "
        "filter:media "
        "lang:en"
    )

    def __init__(self, bot: Bot, chat_id: int, topic_id: Optional[int]) -> None:
        """Initialize X Scrapper."""
        super().__init__(bot, chat_id, topic_id)
        self.query = self.query_format.format(
            min_faves=X_SCRAPPER_MIN_FAVES,
            min_replies=X_SCRAPPER_MIN_REPLIES,
            min_retweets=X_SCRAPPER_MIN_RETWEETS,
            max_replies=X_SCRAPPER_MAX_REPLIES,
            max_retweets=X_SCRAPPER_MAX_RETWEETS,
            max_faves=X_SCRAPPER_MAX_FAVES,
        )

    async def _task(self) -> None:
        """X Post Scrapper task."""
        LOGGER.info("Starting X Scrapper task")
        while True:
            current_cursor = None
            while True:
                try:

                    cursor, tweets = await fetch_tweets(
                        self.query, search_type="top", cursor=current_cursor
                    )
                    if not tweets:
                        LOGGER.info("No new tweets found.")
                        break

                    LOGGER.info("Fetched %d new tweets.", len(tweets))
                    filtered_tweets = await self._filter_tweets(tweets)
                    LOGGER.info("Filtered down to %d tweets.", len(filtered_tweets))
                    await self._process_tweets(filtered_tweets)

                    current_cursor = cursor
                except Exception as e:  # pylint: disable=broad-except
                    LOGGER.error("Error fetching tweets: %s", e)
            LOGGER.info(
                "Waiting for %d seconds before next fetch", X_SCRAPPER_FETCH_INTERVAL
            )
            await asyncio.sleep(X_SCRAPPER_FETCH_INTERVAL)

    async def _filter_tweets(self, tweets: list[TweetData]) -> list[TweetData]:
        """Filter tweets based on criteria and sort by creation date."""
        for t in tweets:
            t.created_at = utc_aware(t.created_at)

        tweets.sort(key=lambda x: x.created_at)

        out: List[TweetData] = []
        unique_tweets = list({t.post_id: t for t in tweets}.values())

        for tweet in unique_tweets:
            if tweet.user.user_followers > X_FILTER_USER_MAX_FOLLOWERS:
                continue
            if tweet.post_views < X_FILTER_POST_MIN_VIEWS:
                continue
            out.append(tweet)

        return out

    async def _process_tweets(self, tweets: List[TweetData]) -> None:
        """Process new tweets."""
        for tweet in tweets:
            if not insert_tweet_if_not_exists(tweet):
                continue
            LOGGER.info("New tweet found: %s", tweet.post_url)
            await self._post_new_tweet(tweet)
            await asyncio.sleep(3)

    async def _post_new_tweet(self, tweet: TweetData) -> None:
        """Post a new tweet to the chat."""
        if not self.task or not self.bot or not self.chat_id:
            return

        keyboard_buttons: List[List[InlineKeyboardButton]] = []
        title = escape_markdown_v2("- NEW TWEET -")
        username = escape_markdown_v2(tweet.user.username)
        user_link = f"[{username}](https://x.com/{username})"
        tweet_date_for = tweet.created_at.strftime("%b %d, %y @ %I:%M %p")
        tweet_date_for += (
            f" ({int((time.time() - tweet.created_at.timestamp()) / 60)}m ago)"
        )
        tweet_date_for = escape_markdown_v2(tweet_date_for)
        tweet_text = escape_markdown_v2(tweet.post_text)
        user_followers = escape_markdown_v2(f"({tweet.user.user_followers})")
        media = tweet.media or []

        payload = (
            f"*{title}*\n\n"
            f"­🦸‍ {user_link} ✦ {user_followers}\n"
            f"­🗓️ {tweet_date_for}\n"
            f"­💬`{tweet.post_likes}` 🔁`{tweet.post_retweets}` "
            f"❤️`{tweet.post_replies}` 👁️`{tweet.post_views}`\n\n"
            f"{tweet_text}\n\n"
        )

        keyboard_buttons.append(
            [
                InlineKeyboardButton(
                    text="🔗 View Tweet",
                    url=f"{tweet.post_url}",
                )
            ]
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        if not media:
            await send_message(
                self.bot,
                self.chat_id,
                text=payload,
                keyboard=keyboard,
                parse_mode=ParseMode.MARKDOWN_V2,
                topic_id=self.topic_id,
                disable_web_page_preview=True,
            )
            return

        if len(media) == 1:
            type_of_media = media[0].type
            url = media[0].url
            if type_of_media == "photo":
                await send_photo(
                    self.bot,
                    self.chat_id,
                    photo=url,
                    caption=payload,
                    keyboard=keyboard,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    topic_id=self.topic_id,
                )
            else:
                await send_video(
                    self.bot,
                    self.chat_id,
                    video_url=url,
                    caption=payload,
                    keyboard=keyboard,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    topic_id=self.topic_id,
                )
            return
        media_group = build_media_group(
            media=media,
            caption=payload,
            parse_mode=ParseMode.MARKDOWN_V2,
            max_items=10,
        )
        await self.bot.send_media_group(
            chat_id=self.chat_id,
            message_thread_id=self.topic_id,
            media=media_group,
        )
        await asyncio.sleep(1)
