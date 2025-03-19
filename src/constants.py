"""Constants to be used by the bot."""

from dataclasses import dataclass
from os import getenv
from typing import Optional

from dotenv import load_dotenv
from solders.pubkey import Pubkey
from solders.signature import Signature

load_dotenv()

PUMP_MIGRATION_ADDRESS: Pubkey = Pubkey.from_string(
    "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg",
)
ASSOCIATED_TOKEN_PROGRAM_ID: Pubkey = Pubkey.from_string(
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
)
TOKEN_PROGRAM_ID: Pubkey = Pubkey.from_string(
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
)

MAX_FETCH_RETRIES: int = 3
PUMP_API: str = "https://frontend-api-v3.pump.fun"
RPC: str = getenv("RPC", "")
BOT_TOKEN: str = getenv("BOT_TOKEN", "")
MAIN_GROUP_ID: int = int(getenv("MAIN_GROUP_ID", ""))
ADMIN_ID: int = int(getenv("ADMIN_ID", ""))

@dataclass
class RawTx:
    signature: Signature
    err: Optional[str]
    logs: list[str]
TEST_RAW_TX: RawTx = RawTx(
    signature=Signature.from_string("651FphAJcdZ92KKqeYJ8mcsaS1r6igtAaq6rFvP8bcnEv3b1sVJ6uyhWhGiGncxY7aW3FjzF4P5ebiCcW1FoTVNj"),
    err=None,
    logs=[
        "Program log: Instruction: Withdraw",
    ],
)
