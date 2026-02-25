"""Module for Bonk Bond Scrapper."""

import logging
from typing import Optional

from aiogram import Bot
from solders.pubkey import Pubkey
from solders.transaction_status import EncodedConfirmedTransactionWithStatusMeta

from bond_scrapper import BondScrapper
from constants import BONK_CONFIG_1, BONK_CONFIG_2, BONK_CONFIG_3, LAUNCHLAB_MIGRATION_ADDRESS
from utils import (
    TokenAssetData,
    calculate_fill_time,
    escape_markdown_v2,
    fetch_launchlab_coin,
    fetch_token_stats,
)

LOGGER: logging.Logger = logging.getLogger(__name__)


class BonkBondScrapper(BondScrapper):
    """Bond Scrapper class."""

    name: str = "Bonk Bond Scrapper"

    def __init__(
        self, bot: Bot, chat_id: int, topic_id: Optional[int], full_stats: bool = False
    ) -> None:
        """Initialize Bonk Bond scrapper."""
        super().__init__(bot, chat_id, topic_id, full_stats)
        self.platform = "🔨 Bonk"
        self.migration_address = LAUNCHLAB_MIGRATION_ADDRESS
        self.bonk_configs = [BONK_CONFIG_1, BONK_CONFIG_2, BONK_CONFIG_3]

    def _compress_dev_link(self, dev: str) -> str:
        """Compress the dev wallet link."""
        compressed_string = escape_markdown_v2(dev[:4] + "..." + dev[-4:])
        profile_link = f"[{compressed_string}](https://solscan.io/account/{dev})"
        return profile_link

    def _is_migrate_tx_logs(self, logs: list[str]) -> bool:
        """Check if logs contain both 'Migrate'."""
        has_migrate = any("migratetocpswap" in log.lower() for log in logs)
        has_burn = any("burn" in log.lower() for log in logs)
        return has_migrate and has_burn

    def _is_migrate_tx(self, tx: EncodedConfirmedTransactionWithStatusMeta) -> bool:
        """Check if transaction is a migration."""
        if not tx.transaction.transaction:
            return False

        transaction_obj = tx.transaction.transaction
        if not hasattr(transaction_obj, "message"):
            return False

        return any(
            addr.pubkey in self.bonk_configs  # type: ignore
            for addr in transaction_obj.message.account_keys # type: ignore
        )

    async def _get_asset_info(self, mint: Pubkey) -> Optional[TokenAssetData]:
        if not self.task:
            return None

        asset = await fetch_launchlab_coin(str(mint))
        asset_stats = await fetch_token_stats(str(mint))
        if not asset:
            return None

        fill_time = calculate_fill_time(asset.created_at)
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
            img_url=asset.img_url,
            telegram=asset.telegram,
            website=asset.website,
            platform=f"https://letsbonk.fun/token/{mint}",
            dex=f"https://dexscreener.com/solana/{mint}",
            stats=asset_stats,
        )
