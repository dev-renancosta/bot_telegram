from __future__ import annotations

import sqlite3

from telegram import Update
from telegram.ext import ContextTypes

from services.repositories import GameRepository
from utils.telegram_links import message_link


async def lista(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection) -> None:
    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        return

    game = GameRepository(conn).get_current(chat.id)
    if not game or not game.message_id:
        if update.message:
            await update.message.reply_text("Ainda não existe lista ativa.")
        return

    link = message_link(chat.id, int(game.message_id))
    text = "📌 A lista está fixada no grupo."
    if link:
        text = f"📌 Lista atual: {link}"

    # tenta responder em privado para não poluir
    try:
        await context.bot.send_message(chat_id=user.id, text=text, disable_web_page_preview=True)
        if update.message:
            await update.message.delete()
    except Exception:
        if update.message:
            await update.message.reply_text(text, disable_web_page_preview=True)


async def financeiro(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection, cfg) -> None:
    # comando público e silencioso: responde no chat (ou em DM se preferir)
    text = cfg.finance_text or "💰 Financeiro ainda não configurado."
    if update.message:
        await update.message.reply_text(text, disable_web_page_preview=True)

