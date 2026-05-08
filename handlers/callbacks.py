from __future__ import annotations

import sqlite3
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

from services.confirmation_service import ConfirmationService
from services.game_service import GameService
from services.repositories import GameRepository
from services.telegram_service import TelegramService


async def list_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection, cfg) -> None:
    query = update.callback_query
    user = update.effective_user
    chat = update.effective_chat

    if not query or not user or not chat:
        return

    await query.answer()  # sempre, para UX e anti-spam

    game = GameRepository(conn).get_current(chat.id)
    if not game or not game.message_id:
        await query.answer("Nenhuma lista ativa.", show_alert=False)
        return

    # Segurança: só responde na mensagem atual do bot (evita cliques em listas antigas)
    if query.message and query.message.message_id != int(game.message_id):
        await query.answer("Essa lista não é a atual.", show_alert=False)
        return

    if game.status != "open":
        await query.answer("🔒 Lista encerrada.", show_alert=False)
        return

    action = "vou" if query.data == "list:vou" else "nao_vou"
    result = ConfirmationService(conn).apply_toggle(
        game_id=game.id,
        max_players=game.max_players,
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        action=action,
    )

    # Refresh mensagem única
    await GameService(conn, TelegramService(context.bot)).refresh_message(
        chat_id=chat.id,
        message_id=int(game.message_id),
        game_id=game.id,
        game_status=game.status,
        max_players=game.max_players,
        game_name=cfg.game_name,
        game_day=cfg.game_day,
        game_time=cfg.game_time,
        game_location=cfg.game_location,
        game_address=cfg.game_address,
        game_date=date.fromisoformat(game.game_date),
    )

    await query.answer(result.toast, show_alert=False)

    if result.promoted_telegram_id:
        await TelegramService(context.bot).safe_dm(
            result.promoted_telegram_id,
            "🎉 Você entrou na lista principal.",
        )

