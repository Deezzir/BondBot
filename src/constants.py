"""Constants to be used by the bot."""

from os import getenv
from typing import Optional

from dotenv import load_dotenv
from solders.pubkey import Pubkey

load_dotenv()

PUMP_MIGRATION_ADDRESS: Pubkey = Pubkey.from_string(
    "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg",
)
SOL_MINT_ADDRESS: Pubkey = Pubkey.from_string(
    "So11111111111111111111111111111111111111112",
)
ASSOCIATED_TOKEN_PROGRAM_ID: Pubkey = Pubkey.from_string(
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
)
TOKEN_PROGRAM_ID: Pubkey = Pubkey.from_string(
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
)
PUMP_AMM_ADDRESS: Pubkey = Pubkey.from_string(
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
)
LAUNCHLAB_MIGRATION_ADDRESS: Pubkey = Pubkey.from_string(
    "LockrWmn6K5twhz3y9w1dQERbmgSaRkfnTeTKbpofwE",
)
BONK_CONFIG_1: Pubkey = Pubkey.from_string(
    "FfYek5vEz23cMkWsdJwG2oa6EphsvXSHrGpdALN4g6W1",
)
BONK_CONFIG_2: Pubkey = Pubkey.from_string(
    "BuM6KDpWiTcxvrpXywWFiw45R2RNH8WURdvqoTDV1BW4",
)
BONK_CONFIG_3: Pubkey = Pubkey.from_string(
    "8pCtbn9iatQ8493mDQax4xfEUjhoVBpUWYVQoRU18333",
)

NOT_FOUND_IMAGE_URL: str = "https://i.ibb.co/fzyGtQ3k/not-found.jpg"
MAX_FETCH_RETRIES: int = 3
PUMP_API: str = "https://frontend-api-v3.pump.fun"
LAUNCHLAB_API: str = "https://launch-mint-v1.raydium.io/get/by/mints"
JUPITER_API: str = "https://lite-api.jup.ag/tokens/v2/search"
RPC: str = getenv("RPC", "")
BOT_TOKEN: str = getenv("BOT_TOKEN", "")
PUMP_GROUP_ID: int = int(getenv("PUMP_GROUP_ID", ""))
BONK_GROUP_ID: int = int(getenv("BONK_GROUP_ID", ""))
PUMP_TOPIC_ID: Optional[int] = (
    int(getenv("PUMP_TOPIC_ID", "")) if getenv("PUMP_TOPIC_ID", "").isdigit() else None
)
BONK_TOPIC_ID: Optional[int] = (
    int(getenv("BONK_TOPIC_ID", "")) if getenv("BONK_TOPIC_ID", "").isdigit() else None
)
