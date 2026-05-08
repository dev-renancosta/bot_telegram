from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, time

from telegram import Update
from telegram.ext import ContextTypes

from handlers.permissions import is_effective_admin
from services.game_service import GameService
from services.status_service import StatusService
from services.telegram_service import TelegramService
from utils.time import compute_game_date


logger = logging.getLogger(__name__)


async def criarlista(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection, cfg) -> None:
    if not await is_effective_admin(update, context, conn):
        return
    chat = update.effective_chat
    if not chat:
        return

    # Regra: o bot cria automaticamente toda quarta 12:00.
    # O comando serve para adiantar (antes de quarta) ou recuperar se o bot estava offline.
    now = datetime.now(tz=cfg.tz)
    is_wed = now.weekday() == 2
    after_wed_noon = is_wed and now.time() >= time(hour=12, minute=0)

    game_date = compute_game_date(cfg.game_day, cfg.tz)
    svc = GameService(conn, TelegramService(context.bot))
    open_game = svc.get_open_game(chat.id)

    if after_wed_noon and open_game is not None:
        # já existe lista aberta e já passou do horário automático -> não precisa recriar
        if update.message:
            await update.message.delete()
        return

    await svc.create_or_refresh_list(
        chat_id=chat.id,
        game_date=game_date,
        max_players=cfg.max_players,
        game_name=cfg.game_name,
        game_day=cfg.game_day,
        game_time=cfg.game_time,
        game_location=cfg.game_location,
        game_address=cfg.game_address,
    )

    if update.message:
        await update.message.delete()


async def fecharlista(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection, cfg) -> None:
    if not await is_effective_admin(update, context, conn):
        return
    chat = update.effective_chat
    if not chat:
        return

    svc = GameService(conn, TelegramService(context.bot))
    await svc.close_list(
        chat_id=chat.id,
        game_name=cfg.game_name,
        game_day=cfg.game_day,
        game_time=cfg.game_time,
        game_location=cfg.game_location,
        game_address=cfg.game_address,
    )

    if update.message:
        await update.message.delete()


async def resetlista(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection, cfg) -> None:
    if not await is_effective_admin(update, context, conn):
        return
    chat = update.effective_chat
    if not chat:
        return

    svc = GameService(conn, TelegramService(context.bot))
    await svc.reset_list(
        chat_id=chat.id,
        game_name=cfg.game_name,
        game_day=cfg.game_day,
        game_time=cfg.game_time,
        game_location=cfg.game_location,
        game_address=cfg.game_address,
    )

    if update.message:
        await update.message.delete()


async def apagarlista(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection, cfg) -> None:
    if not await is_effective_admin(update, context, conn):
        return
    chat = update.effective_chat
    if not chat:
        return

    ok = await GameService(conn, TelegramService(context.bot)).delete_current_list(chat_id=chat.id)

    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass

    if ok:
        # Confirmação silenciosa (DM se possível)
        user = update.effective_user
        if user:
            await TelegramService(context.bot).safe_dm(user.id, "🗑️ Lista/jogo atual apagado. Agora você pode usar /criarlista para recriar do zero.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection) -> None:
    chat = update.effective_chat
    if not chat:
        return

    from services.repositories import GameRepository

    game = GameRepository(conn).get_current(chat.id)
    if not game:
        if update.message:
            await update.message.reply_text("Nenhuma lista encontrada.")
        return

    stats = StatusService(conn).get_stats(game.id)
    text = (
        "📊 Status da lista\n\n"
        f"✅ Confirmados: {stats['vou']}\n"
        f"🕒 Espera: {stats['espera']}\n"
        f"❌ Não vão: {stats['nao_vou']}\n"
    )
    if update.message:
        await update.message.reply_text(text)
