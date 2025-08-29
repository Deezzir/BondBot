"""Database operations."""

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
                "changes": {"bsonType": "object"},
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
    offset: int = 0, limit: int = 20, filter: Optional[dict] = None
) -> list[TweetData]:
    """Retrieve all tweets from the database.

    Args:
        offset (int): The number of tweets to skip. Defaults to 0.
        limit (int): The maximum number of tweets to retrieve. Defaults to 20.

    Returns:
        list[TweetData]: A list of all tweets in the database.
    """
    coll = _ensure_tweets_collection()
    tweets = coll.find(filter=filter, skip=offset, limit=limit).sort(
        "created_at", ASCENDING
    )
    return [TweetData(**tweet) for tweet in tweets]


def update_tweets(tweets: list[TweetData]) -> None:
    """Update tweets in the database.

    Args:
        tweets (list[TweetData]): The list of tweets to update.
    """
    coll = _ensure_tweets_collection()
    for tweet in tweets:
        coll.update_one(
            {"post_id": tweet.post_id}, {"$set": tweet.model_dump()}, upsert=False
        )
