"""Module for Bond Scrapper."""

import asyncio
import logging
from typing import Any, List, Optional

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, URLInputFile
from solana.rpc.async_api import AsyncClient
from solana.rpc.types import Commitment, MemcmpOpts
from solana.rpc.websocket_api import connect as ws_connect
from solders.pubkey import Pubkey
from solders.rpc.config import RpcTransactionLogsFilterMentions
from solders.rpc.responses import GetProgramAccountsResp, GetTransactionResp
from solders.signature import Signature
from solders.transaction_status import (
    UiPartiallyDecodedInstruction,
    UiTransaction,
    UiTransactionTokenBalance,
)

from constants import PUMP_AMM_ADDRESS, PUMP_MIGRATION_ADDRESS, RPC
from utils import (
    AssetData,
    Holder,
    HoldersInfo,
    calculate_fill_time,
    fetch_pump_coin,
    get_token_wallet,
    send_photo,
)

LOGGER: logging.Logger = logging.getLogger(__name__)


class BondScrapper:
    """Bond Scrapper class."""

    def __init__(self, bot: Bot, chat_id: int) -> None:
        """Initialize New Bond scrapper."""
        self.rpc = RPC
        self.task: Optional[asyncio.Task[Any]] = None
        self.bot = bot
        self.chat_id = chat_id

    async def start(self, chat_id: int) -> None:
        """Start the Bond Scrapper."""
        if self.task:
            await self.bot.send_message(chat_id, "Bond Scrapper already running.")
            return

        await self.bot.send_message(chat_id, "Starting Bond Scrapper...")
        task = asyncio.create_task(self._subscribe_bonds())
        self.task = task
        await task

    async def stop(self, chat_id: int) -> None:
        """Stop the Bond Scrapper."""
        if self.task:
            await self.bot.send_message(chat_id, "Stopping Bond Scrapper...")
            self.task.cancel()

            try:
                await self.task
            except asyncio.CancelledError:
                pass
            finally:
                LOGGER.info("Bond Task was successfully cancelled.")
                self.task = None
        else:
            if not self.chat_id:
                return
            await self.bot.send_message(chat_id, "Bond Scrapper is not running.")

    def _compress_dev_link(self, dev: str) -> str:
        """Compress the dev wallet link."""
        compressed_string = dev[:4] + "\.\.\." + dev[-4:]
        profile_link = f"[{compressed_string}](https://pump.fun/profile/{dev})"
        return profile_link

    async def _post_new_bond(self, asset: AssetData) -> None:
        """Post a new bond to the chat."""
        if not self.task or not self.bot or not self.chat_id:
            LOGGER.error("Task not initialized")
            return

        keyboard_buttons: List[List[InlineKeyboardButton]] = []
        top_buttons = []
        bottom_buttons = []

        payload = (
            f"*\- NEW BOND \-*\n\n"
            f"📛 *{asset.name} \(${asset.symbol}\)*\n"
            f"📄 *CA:* `{asset.ca}`\n\n"
            f"👨‍💻 *Dev:* {self._compress_dev_link(asset.dev_wallet)}\n"
            f"🏛 *Dev Hodls:* {asset.dev_alloc if asset.dev_alloc > 1 else '<1%'}%\n\n"
            f"🐳 *Top Hodlers:* "
        )
        allocation_strings = [
            f"{holder.allocation}%" for holder in asset.top_holders[:5]
        ]
        result = " \| ".join(allocation_strings)
        payload += result
        payload += (
            f"\n*🏦 Top 20 Hodlers allocation:* {asset.top_holders_allocation}%\n"
        )
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
                text="💊 Pump Fun",
                url=asset.pump,
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
        )

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

    async def _get_tx_details(
        self, sig: Signature
    ) -> Optional[List[UiTransactionTokenBalance]]:
        if not self.task:
            return None
        tx_raw = GetTransactionResp(None)
        attempt = 0

        async with AsyncClient(f"https://{self.rpc}") as client:
            try:
                while attempt < 10:
                    tx_raw = await client.get_transaction(
                        sig, "jsonParsed", Commitment("confirmed"), max_supported_transaction_version=0
                    )
                    if tx_raw != GetTransactionResp(None):
                        break
                    else:
                        LOGGER.warning(f"Failed to get transaction {sig}, retrying...")
                        attempt += 1
                        await asyncio.sleep(0.5)
                if (
                    tx_raw.value
                    and tx_raw.value.transaction
                    and tx_raw.value.transaction.meta
                ):
                    return tx_raw.value.transaction.meta.post_token_balances
            except Exception as e:
                LOGGER.error(f"Error in _get_tx_details: {e}")
            return None

    async def _get_pump_amm(
        self, mint: str
    ) -> Optional[List[UiTransactionTokenBalance]]:
        """Get the AMM pool of a pump coin."""
        if not self.task:
            return None
        accounts = GetProgramAccountsResp([])
        attempt = 0

        async with AsyncClient(f"https://{self.rpc}") as client:
            try:
                while attempt < 10:
                    accounts = await client.get_program_accounts(
                        PUMP_AMM_ADDRESS,
                        filters=[
                            MemcmpOpts(
                                offset=32 + 2 + 8 + 1,
                                bytes=mint,
                            )
                        ],
                        encoding="jsonParsed",
                    )
                    if accounts != GetProgramAccountsResp([]):
                        break
                    else:
                        LOGGER.warning(f"Failed to get AMM for '{mint}', retrying...")
                        attempt += 1
                        await asyncio.sleep(0.5)
                if accounts.value:
                    return accounts.value
            except Exception as e:
                LOGGER.error(f"Error in _get_tx_details: {e}")
            return None

    async def _process_log(self, raw_tx: Any) -> Optional[Pubkey]:
        if not self.task:
            return None
        if any(log for log in raw_tx.logs if "Migrate" in log and "Burn" in log) and not raw_tx.err:
            token_balances = await self._get_tx_details(raw_tx.signature)
            if not token_balances:
                return None
            LOGGER.info(f"Found the initilize new pool tx: {raw_tx.signature}")
            mint_balance = next(
                (
                    token_balance
                    for token_balance in token_balances
                    if token_balance.ui_token_amount.ui_amount is None
                ),
                None,
            )
            return mint_balance.mint if mint_balance else None
        return None

    async def _subscribe_bonds(self) -> None:
        if not self.task:
            return

        sub_id: int
        done = False

        while not done:
            async with ws_connect(
                f"wss://{self.rpc}", ping_interval=60, ping_timeout=120
            ) as websocket:
                try:
                    await websocket.logs_subscribe(
                        RpcTransactionLogsFilterMentions(PUMP_MIGRATION_ADDRESS),
                        Commitment("confirmed"),
                    )
                    LOGGER.info("Subscribed to logs. Waiting for messages...")
                    first_resp = await websocket.recv()
                    sub_id = first_resp[0].result  # type: ignore

                    async for log in websocket:
                        try:
                            mint = await self._process_log(log[0].result.value)  # type: ignore
                            if mint:
                                LOGGER.info(f"Found new bond: {str(mint)}")
                                asset_info = await self._get_asset_info(mint)
                                if asset_info:
                                    await self._post_new_bond(asset_info)
                        except Exception as e:
                            LOGGER.error(f"Error processing a log: {e}")
                except asyncio.CancelledError:
                    LOGGER.info("The task was canceled. Cleaning up...")
                    done = True
                    break
                except Exception as e:
                    LOGGER.error(f"Error with the WebSocket connection: {e}")
                finally:
                    if websocket.open and sub_id:
                        await websocket.logs_unsubscribe(sub_id)

    def _sort_holders(self, top_holders: List[Holder]) -> List[Holder]:
        return sorted(top_holders, key=lambda x: x.allocation, reverse=True)

    async def _get_allocation_info(
        self,
        mint: Pubkey,
        dev: Optional[Pubkey],
        bonding_curve: Optional[Pubkey],
    ) -> Optional[HoldersInfo]:
        if not self.task:
            return None

        async with AsyncClient(f"https://{self.rpc}") as client:
            try:
                info = HoldersInfo(
                    top_holders=[], dev_allocation=0, top_holders_allocation=0
                )
                total_supply = await client.get_token_supply(mint)
                holders_raw = await client.get_token_largest_accounts(mint)
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
                if bonding_curve:
                    bonding_curve_token = get_token_wallet(bonding_curve, mint)
                    info.top_holders = [
                        holder
                        for holder in info.top_holders
                        if holder.address != str(bonding_curve_token)
                    ]
                info.top_holders_allocation = int(
                    sum(holder.allocation for holder in info.top_holders)
                )
                return info
            except Exception as e:
                LOGGER.error(f"Error in get_allocation_info: {e}")
                return None

    async def _get_asset_info(self, mint: Pubkey) -> Optional[AssetData]:
        if not self.task:
            return None

        asset = await fetch_pump_coin(str(mint))
        if not asset:
            return None

        fill_time = calculate_fill_time(asset.created_timestamp)
        alloc_info = await self._get_allocation_info(
            mint,
            Pubkey.from_string(asset.creator),
            Pubkey.from_string(asset.bonding_curve),
        )

        return AssetData(
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
            pump=f"https://pump.fun/{mint}",
            dex=f"https://dexscreener.com/solana/{mint}",
        )
