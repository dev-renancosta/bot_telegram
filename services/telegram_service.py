from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telegram import InlineKeyboardMarkup, Message
from telegram.constants import ParseMode
from telegram.error import BadRequest, RetryAfter, TimedOut, NetworkError, TelegramError
from telegram.ext import ExtBot


logger = logging.getLogger(__name__)


class TelegramService:
    def __init__(self, bot: ExtBot) -> None:
        self._bot = bot

    async def _retry(self, fn, *, attempts: int = 5):
        delay = 0.8
        for i in range(attempts):
            try:
                return await fn()
            except RetryAfter as e:
                logger.warning("Telegram rate limit: aguardando %ss", e.retry_after)
                await asyncio.sleep(float(e.retry_after))
            except BadRequest:
                # Erro lógico (ex.: message_id não existe). Não adianta dar retry.
                raise
            except (TimedOut, NetworkError) as e:
                if i == attempts - 1:
                    raise
                logger.warning("Erro transitório Telegram (%s); retry em %.1fs", type(e).__name__, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 8)
            except TelegramError:
                raise

    async def send_list_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup],
    ) -> Message:
        return await self._retry(
            lambda: self._bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        )

    async def edit_list_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Optional[InlineKeyboardMarkup],
    ) -> None:
        await self._retry(
            lambda: self._bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        )

    async def pin_message(self, chat_id: int, message_id: int) -> None:
        await self._retry(lambda: self._bot.pin_chat_message(chat_id=chat_id, message_id=message_id, disable_notification=True))

    async def unpin_message(self, chat_id: int, message_id: int) -> None:
        await self._retry(lambda: self._bot.unpin_chat_message(chat_id=chat_id, message_id=message_id))

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        await self._retry(lambda: self._bot.delete_message(chat_id=chat_id, message_id=message_id))

    async def safe_dm(self, telegram_id: int, text: str) -> None:
        try:
            await self._retry(lambda: self._bot.send_message(chat_id=telegram_id, text=text, disable_web_page_preview=True))
        except TelegramError as e:
            logger.info("Falha ao enviar DM para %s (%s)", telegram_id, type(e).__name__)

    async def send_notice(self, chat_id: int, text: str) -> None:
        await self._retry(lambda: self._bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=True))

