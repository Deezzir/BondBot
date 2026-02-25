"""Base class for scrappers."""

import asyncio
import logging
from abc import ABC
from typing import Any, List, Optional

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, URLInputFile
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Commitment
from solana.rpc.websocket_api import connect as ws_connect
from solders.pubkey import Pubkey
from solders.rpc.config import RpcTransactionLogsFilterMentions
from solders.rpc.responses import GetTransactionResp
from solders.signature import Signature
from solders.transaction_status import (
    EncodedConfirmedTransactionWithStatusMeta,
    UiPartiallyDecodedInstruction,
    UiTransaction,
)

from constants import MAX_FETCH_RETRIES, RPC, SOL_MINT_ADDRESS
from scrapper import Scrapper
from utils import (
    Holder,
    HoldersInfo,
    TokenAssetData,
    escape_markdown_v2,
    format_currency,
    get_token_wallet,
    send_photo,
)

LOGGER: logging.Logger = logging.getLogger(__name__)


class BondScrapper(Scrapper, ABC):
    """Base class for scrappers."""

    platform: str
    migration_address: Pubkey
    full_stats: bool = False

    def __init__(
        self, bot: Bot, chat_id: int, topic_id: Optional[int], full_stats: bool = False
    ) -> None:
        """Initialize New Bond scrapper."""
        super().__init__(bot, chat_id, topic_id)
        self.rpc = RPC
        self.full_stats = full_stats
        self._post_new_bond = (
            self._post_new_bond_full if full_stats else self._post_new_bond_short
        )

    def _compress_dev_link(self, dev: str) -> str:
        """Compress the dev wallet link."""
        raise NotImplementedError("This method should be implemented by subclasses.")

    def _is_migrate_tx_logs(self, logs: list[str]) -> bool:
        """Check if logs contain both 'Migrate' and 'Burn' entries."""
        raise NotImplementedError("This method should be implemented by subclasses.")

    def _is_migrate_tx(self, tx: EncodedConfirmedTransactionWithStatusMeta) -> bool:
        """Check if the transaction is a migration transaction."""
        raise NotImplementedError("This method should be implemented by subclasses.")

    async def _get_asset_info(self, mint: Pubkey) -> Optional[TokenAssetData]:
        """Fetch asset information for the given mint."""
        raise NotImplementedError("This method should be implemented by subclasses.")

    async def _process_log(self, raw_tx: Any) -> Optional[Pubkey]:
        """Process the log and return the mint address if found."""
        if not self.task:
            return None

        LOGGER.info("Processing log: %s", raw_tx.signature)
        if raw_tx.err or not self._is_migrate_tx_logs(raw_tx.logs):
            LOGGER.info("Skipping log due to error or missing migration logs.")
            return None
        tx = await self._get_tx_details(raw_tx.signature)
        if not tx or not self._is_migrate_tx(tx):
            LOGGER.info("Transaction is not a migration transaction.")
            return None

        LOGGER.info("Found the initilize new pool tx: %s", raw_tx.signature)

        token_balances = tx.transaction.meta.post_token_balances  # type: ignore
        if not token_balances:
            LOGGER.warning("No token balances found in transaction.")
            return None
        mint_balance = next(
            (
                token_balance
                for token_balance in token_balances
                if (
                    token_balance.ui_token_amount.ui_amount is None
                    or token_balance.ui_token_amount.ui_amount == 0
                )
                and token_balance.mint != SOL_MINT_ADDRESS
            ),
            None,
        )
        if not mint_balance:
            LOGGER.warning("No mint balance found in transaction.")
            return None
        return mint_balance.mint

    async def _task(self) -> None:
        """Subscribe to bond logs and process them."""
        if not self.task:
            return

        sub_id: Optional[int] = None
        done = False

        while not done:
            async with ws_connect(
                f"wss://{self.rpc}", ping_interval=60, ping_timeout=120
            ) as websocket:
                try:
                    await websocket.logs_subscribe(
                        RpcTransactionLogsFilterMentions(self.migration_address),
                        Commitment("confirmed"),
                    )
                    LOGGER.info("Subscribed to logs. Waiting for messages...")
                    first_resp = await websocket.recv()
                    sub_id = first_resp[0].result  # type: ignore

                    async for log in websocket:
                        try:
                            mint = await self._process_log(log[0].result.value)  # type: ignore
                            if mint:
                                LOGGER.info("Found new bond: %s", str(mint))
                                asset_info = await self._get_asset_info(mint)
                                if asset_info:
                                    await self._post_new_bond(asset_info)
                        except Exception as e:  # pylint: disable=broad-except
                            LOGGER.error("Error processing a log: %s", e)
                except asyncio.CancelledError:
                    LOGGER.info("The task was canceled. Cleaning up...")
                    done = True
                    break
                except Exception as e:  # pylint: disable=broad-except
                    LOGGER.error("Error with the WebSocket connection: %s", e)
                finally:
                    if websocket.open and sub_id is not None:
                        await websocket.logs_unsubscribe(sub_id)

    def _find_instruction_by_program_id(
        self, transaction: UiTransaction, target_program_id: Pubkey
    ) -> Optional[UiPartiallyDecodedInstruction]:
        """Find instruction by program id."""
        if not self.task:
            return None
        if not transaction.message or not transaction.message.instructions:
            return None

        for instruction in transaction.message.instructions:
            if not isinstance(instruction, UiPartiallyDecodedInstruction):
                continue
            if instruction.program_id == target_program_id:
                return instruction
        return None

    async def _post_new_bond_short(self, asset: TokenAssetData) -> None:
        """Post a new bond to the chat with short info."""
        if not self.task or not self.bot or not self.chat_id:
            return

        token_info = escape_markdown_v2(f"{asset.name} (${asset.symbol})")
        payload = f"📛 *{token_info}*\n" f"📄 *CA:* `{asset.ca}`"

        keyboard_buttons: List[List[InlineKeyboardButton]] = []
        social_buttons: List[InlineKeyboardButton] = []

        if asset.twitter:
            social_buttons.append(
                InlineKeyboardButton(
                    text="🐤 Twitter",
                    url=asset.twitter,
                )
            )
        if asset.telegram:
            social_buttons.append(
                InlineKeyboardButton(
                    text="📞 Telegram",
                    url=asset.telegram,
                )
            )
        if asset.website:
            social_buttons.append(
                InlineKeyboardButton(
                    text="🌐 Website",
                    url=asset.website,
                )
            )

        if social_buttons:
            keyboard_buttons.append(social_buttons)

        keyboard_buttons.append(
            [
                InlineKeyboardButton(
                    text="🦅 DEX Screener",
                    url=asset.dex,
                )
            ]
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        image = URLInputFile(asset.img_url)
        _ = await send_photo(
            self.bot,
            self.chat_id,
            image,
            payload,
            keyboard,
            parse_mode=ParseMode.MARKDOWN_V2,
            topic_id=self.topic_id,
        )

    async def _post_new_bond_full(self, asset: TokenAssetData) -> None:
        """Post a new bond to the chat."""
        if not self.task or not self.bot or not self.chat_id:
            return

        keyboard_buttons: List[List[InlineKeyboardButton]] = []
        top_buttons = []
        bottom_buttons = []

        title = escape_markdown_v2("- NEW BOND -")
        token_info = escape_markdown_v2(f"{asset.name} (${asset.symbol})")

        payload = (
            f"*{title}*\n\n"
            f"📛 *{token_info}*\n"
            f"📄 *CA:* `{asset.ca}`\n\n"
            f"👨‍💻 *Dev:* {self._compress_dev_link(asset.dev_wallet)}\n"
            f"🏛 *Dev Hodls:* {asset.dev_alloc if asset.dev_alloc > 1 else '<1'}%\n\n"
            f"🐳 *Top Hodlers:* "
        )
        allocation_strings = [
            f"{holder.allocation}%" for holder in asset.top_holders[:5]
        ]
        result = escape_markdown_v2(" | ".join(allocation_strings))
        payload += result
        payload += (
            f"\n*🏦 Top 20 Hodlers allocation:* {asset.top_holders_allocation}%\n"
        )

        stats = ""
        if asset.stats and asset.stats.stats_24h:
            buy_volume = escape_markdown_v2(
                format_currency(asset.stats.stats_24h.buy_volume)
            )
            sell_volume = escape_markdown_v2(
                format_currency(asset.stats.stats_24h.sell_volume)
            )

            stats = (
                f"\n*👥 Total Hodlers:* {asset.stats.holder_count}\n"
                f"*🌱 Organic Score:* {asset.stats.organic_score_label.capitalize()}\n"
                f"*📈 Stats:*\n"
                f"        • Buy Volume: {buy_volume}$\n"
                f"        • Sell Volume: {sell_volume}$\n"
                f"        • Buys: {asset.stats.stats_24h.num_buys}\n"
                f"        • Sells: {asset.stats.stats_24h.num_sells}\n"
                f"        • Traders: {asset.stats.stats_24h.num_traders}\n"
            )

        payload += stats
        payload += f"\n*⏰ Fill time: *{asset.fill_time}"

        if asset.twitter:
            top_buttons.append(
                InlineKeyboardButton(
                    text="🐤 Twitter",
                    url=asset.twitter,
                )
            )
        if asset.telegram:
            top_buttons.append(
                InlineKeyboardButton(
                    text="📞 Telegram",
                    url=asset.telegram,
                )
            )
        if asset.website:
            top_buttons.append(
                InlineKeyboardButton(
                    text="🌐 Website",
                    url=asset.website,
                )
            )

        bottom_buttons.append(
            InlineKeyboardButton(
                text=self.platform,
                url=asset.platform,
            )
        )
        bottom_buttons.append(
            InlineKeyboardButton(
                text="🦅 DEX Screener",
                url=asset.dex,
            )
        )
        keyboard_buttons.append(top_buttons)
        keyboard_buttons.append(bottom_buttons)
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        image = URLInputFile(asset.img_url)
        _ = await send_photo(
            self.bot,
            self.chat_id,
            image,
            payload,
            keyboard,
            parse_mode=ParseMode.MARKDOWN_V2,
            topic_id=self.topic_id,
        )

    async def _get_tx_details(
        self, sig: Signature
    ) -> Optional[EncodedConfirmedTransactionWithStatusMeta]:
        """Get transaction details by signature."""
        if not self.task:
            return None

        tx_raw = GetTransactionResp(None)
        attempt = 0

        async with AsyncClient(f"https://{self.rpc}") as client:
            try:
                while attempt < MAX_FETCH_RETRIES:
                    tx_raw = await client.get_transaction(
                        sig,
                        "jsonParsed",
                        Commitment("confirmed"),
                        max_supported_transaction_version=0,
                    )
                    if tx_raw != GetTransactionResp(None):
                        break

                    LOGGER.warning("Failed to get transaction %s, retrying...", sig)
                    attempt += 1
                    await asyncio.sleep(0.5)
                if (
                    tx_raw.value
                    and tx_raw.value.transaction
                    and tx_raw.value.transaction.meta
                ):
                    return tx_raw.value
            except Exception as e:  # pylint: disable=broad-except
                LOGGER.error("Error in _get_tx_details: %s", e)
            return None

    def _sort_holders(self, top_holders: List[Holder]) -> List[Holder]:
        return sorted(top_holders, key=lambda x: x.allocation, reverse=True)

    async def _get_allocation_info(
        self,
        mint: Pubkey,
        dev: Optional[Pubkey],
    ) -> Optional[HoldersInfo]:
        """Get allocation info for the given mint."""
        if not self.task:
            return None

        attempt = 0

        async with AsyncClient(f"https://{self.rpc}") as client:
            while attempt < MAX_FETCH_RETRIES:
                try:
                    info = HoldersInfo(
                        top_holders=[], dev_allocation=0, top_holders_allocation=0
                    )
                    total_supply = await client.get_token_supply(
                        mint, Commitment("confirmed")
                    )
                    holders_raw = await client.get_token_largest_accounts(
                        mint, Commitment("confirmed")
                    )
                    for holder_raw in holders_raw.value:
                        info.top_holders.append(
                            Holder(
                                address=str(holder_raw.address),
                                allocation=int(
                                    round(
                                        int(holder_raw.amount.amount)
                                        / int(total_supply.value.amount)
                                        * 100
                                    )
                                ),
                            )
                        )
                    if dev:
                        dev_token = get_token_wallet(dev, mint)
                        for holder in info.top_holders:
                            if holder.address == str(dev_token):
                                info.dev_allocation = holder.allocation
                                break
                    info.top_holders = info.top_holders[1:]
                    info.top_holders_allocation = int(
                        sum(holder.allocation for holder in info.top_holders)
                    )
                    return info
                except Exception as e:  # pylint: disable=broad-except
                    LOGGER.error("Error in get_allocation_info: %s, retrying...", e)
                    attempt += 1
            return None
