"""Database operations."""

import datetime
from typing import Optional

from pymongo import ASCENDING, MongoClient, errors
from pymongo.collection import Collection
from pymongo.database import Database

from constants import MONGODB_COLLECTION_NAME, MONGODB_DB_NAME, MONGODB_URI
from utils import TweetData

_client: Optional[MongoClient] = None
_db: Optional[Database] = None
_coll: Optional[Collection] = None


def _get_client() -> MongoClient:
    """Get the MongoDB client instance."""
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        _client.admin.command("ping")
    return _client


def _get_db() -> Database:
    """Get the MongoDB database instance."""
    global _db
    if _db is None:
        _db = _get_client()[MONGODB_DB_NAME]
    return _db


def _ensure_tweets_collection() -> Collection:
    """Ensure the tweets collection exists with the proper schema and indexes."""
    global _coll
    if _coll is not None:
        return _coll

    db = _get_db()

    validator = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["user", "post_id", "created_at", "post_text"],
            "properties": {
                "user": {"bsonType": "object"},
                "post_id": {"bsonType": "string"},
                "post_text": {"bsonType": "string"},
                "post_views": {"bsonType": "int"},
                "post_likes": {"bsonType": "int"},
                "post_replies": {"bsonType": "int"},
                "post_retweets": {"bsonType": "int"},
                "created_at": {"bsonType": "date"},
                "media": {"bsonType": "array"},
                "review": {
                    "bsonType": "object",
                    "properties": {
                        "status": {"enum": ["queued", "recheck", "posted", "discarded"]},
                        "next_check_at": {"bsonType": ["date", "null"]},
                        "retries": {"bsonType": "int"},
                    },
                    "additionalProperties": True,
                },
            },
            "additionalProperties": True,
        }
    }

    if MONGODB_COLLECTION_NAME in db.list_collection_names():
        _coll = db.get_collection(MONGODB_COLLECTION_NAME)
        try:
            db.command("collMod", MONGODB_COLLECTION_NAME, validator=validator)
        except errors.OperationFailure:
            pass
    else:
        _coll = db.create_collection(MONGODB_COLLECTION_NAME, validator=validator)

    _coll.create_index("post_id", unique=True)
    _coll.create_index("user.username")
    _coll.create_index("created_at")
    _coll.create_index([("review.next_check_at", ASCENDING)])

    return _coll


def insert_tweet_if_not_exists(tweet: TweetData) -> bool:
    """Insert a tweet into the database if it does not already exist.

    Args:
        tweet (TweetData): The tweet data to insert.

    Returns:
        bool: True if the tweet was inserted, False if it already exists.
    """
    coll = _ensure_tweets_collection()
    try:
        coll.insert_one(tweet.model_dump())
        return True
    except errors.DuplicateKeyError:
        return False


def get_tweets(
    offset: int = 0, limit: int = 20, db_filter: Optional[dict] = None
) -> list[TweetData]:
    """Retrieve all tweets from the database.

    Args:
        offset (int): The number of tweets to skip. Defaults to 0.
        limit (int): The maximum number of tweets to retrieve. Defaults to 20.
        db_filter (Optional[dict]): Optional filter to apply to the query.

    Returns:
        list[TweetData]: A list of all tweets in the database.
    """
    coll = _ensure_tweets_collection()
    tweets = coll.find(filter=db_filter, skip=offset, limit=limit).sort("created_at", ASCENDING)
    return [TweetData(**tweet) for tweet in tweets]


def update_tweets(tweets: list[TweetData]) -> None:
    """Update tweets in the database.

    Args:
        tweets (list[TweetData]): The list of tweets to update.
    """
    coll = _ensure_tweets_collection()
    for tweet in tweets:
        coll.update_one({"post_id": tweet.post_id}, {"$set": tweet.model_dump()}, upsert=False)


def queue_tweet_review(tweet: TweetData, delay_seconds: int) -> None:
    """Queue a tweet for review."""
    coll = _ensure_tweets_collection()
    now = datetime.datetime.now(datetime.timezone.utc)
    coll.update_one(
        {"post_id": tweet.post_id},
        {
            "$set": {
                "review": {
                    "status": "queued",
                    "next_check_at": now + datetime.timedelta(seconds=delay_seconds),
                    "retries": 0,
                }
            }
        },
        upsert=False,
    )


def get_tweet_due_reviews(limit: int = 100) -> list[TweetData]:
    """Get tweets that are due for review."""
    coll = _ensure_tweets_collection()
    now = datetime.datetime.now(datetime.timezone.utc)
    cur = (
        coll.find(
            {
                "review.status": {"$in": ["queued", "recheck"]},
                "review.next_check_at": {"$lte": now},
            }
        )
        .sort("review.next_check_at", ASCENDING)
        .limit(limit)
    )
    return [TweetData(**d) for d in cur]


def mark_tweet_recheck(post_id: str, delay_seconds: int) -> None:
    """Mark a tweet for recheck after a delay."""
    coll = _ensure_tweets_collection()
    now = datetime.datetime.now(datetime.timezone.utc)
    coll.update_one(
        {"post_id": post_id},
        {
            "$set": {
                "review.status": "recheck",
                "review.next_check_at": now + datetime.timedelta(seconds=delay_seconds),
            },
            "$inc": {"review.retries": 1},
        },
    )


def mark_tweet_posted(post_id: str) -> None:
    """Mark a tweet as posted."""
    coll = _ensure_tweets_collection()
    coll.update_one(
        {"post_id": post_id},
        {"$set": {"review.status": "posted", "review.next_check_at": None}},
    )


def mark_tweet_discarded(post_id: str) -> None:
    """Mark a tweet as discarded."""
    coll = _ensure_tweets_collection()
    coll.update_one(
        {"post_id": post_id},
        {"$set": {"review.status": "discarded", "review.next_check_at": None}},
    )
