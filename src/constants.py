"""Constants to be used by the bot."""

from os import getenv

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

NOT_FOUND_IMAGE_URL: str = "https://i.ibb.co/fzyGtQ3k/not-found.jpg"
MAX_FETCH_RETRIES: int = 3
PUMP_API: str = "https://frontend-api-v3.pump.fun"
RPC: str = getenv("RPC", "")
BOT_TOKEN: str = getenv("BOT_TOKEN", "")
MAIN_GROUP_ID: int = int(getenv("MAIN_GROUP_ID", ""))
ADMIN_ID: int = int(getenv("ADMIN_ID", ""))
