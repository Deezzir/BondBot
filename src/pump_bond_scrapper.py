"""Module for Pump Bond Scrapper."""

import logging
from typing import Optional

from aiogram import Bot
from solders.pubkey import Pubkey
from solders.transaction_status import EncodedConfirmedTransactionWithStatusMeta

from bond_scrapper import BondScrapper
from constants import PUMP_MIGRATION_ADDRESS
from utils import (
    TokenAssetData,
    calculate_fill_time,
    escape_markdown_v2,
    fetch_pump_coin,
    fetch_token_stats,
)

LOGGER: logging.Logger = logging.getLogger(__name__)


class PumpBondScrapper(BondScrapper):
    """Bond Scrapper class."""

    name: str = "Pump Bond Scrapper"

    def __init__(self, bot: Bot, chat_id: int, topic_id: Optional[int]) -> None:
        """Initialize Pump Bond scrapper."""
        super().__init__(bot, chat_id, topic_id)
        self.platform = "💊 Pump Fun"
        self.migration_address = PUMP_MIGRATION_ADDRESS

    def _compress_dev_link(self, dev: str) -> str:
        """Compress the dev wallet link."""
        compressed_string = escape_markdown_v2(dev[:4] + "..." + dev[-4:])
        profile_link = f"[{compressed_string}](https://pump.fun/profile/{dev})"
        return profile_link

    def _is_migrate_tx_logs(self, logs: list[str]) -> bool:
        """Check if logs contain both 'Migrate' and 'Burn' entries."""
        has_migrate = any("migrate" in log.lower() for log in logs)
        is_second = any("already migrated" in log.lower() for log in logs)
        return has_migrate and not is_second

    def _is_migrate_tx(self, tx: EncodedConfirmedTransactionWithStatusMeta) -> bool:
        """Check if transaction is a migration."""
        return True

    async def _get_asset_info(self, mint: Pubkey) -> Optional[TokenAssetData]:
        if not self.task:
            return None

        asset = await fetch_pump_coin(str(mint))
        if not asset:
            return None

        fill_time = calculate_fill_time(asset.created_timestamp)
        asset_stats = await fetch_token_stats(str(mint))
        alloc_info = await self._get_allocation_info(
            mint,
            Pubkey.from_string(asset.creator),
        )

        return TokenAssetData(
            dev_wallet=asset.creator,
            fill_time=fill_time,
            dev_alloc=alloc_info.dev_allocation if alloc_info else 0,
            top_holders=alloc_info.top_holders if alloc_info else [],
            top_holders_allocation=(
                alloc_info.top_holders_allocation if alloc_info else 0
            ),
            ca=asset.mint,
            name=asset.name,
            symbol=asset.symbol,
            twitter=asset.twitter,
            img_url=asset.image_uri,
            telegram=asset.telegram,
            website=asset.website,
            platform=f"https://pump.fun/{mint}",
            dex=f"https://dexscreener.com/solana/{mint}",
            stats=asset_stats,
        )
