from __future__ import annotations

import sqlite3

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.repositories import PlayerRepository


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection, cfg) -> None:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return

    # Preferir DM para onboarding (sem poluir o grupo)
    PlayerRepository(conn).upsert(user.id, user.username, user.first_name)

    lines = [
        "⚽ Bem-vindo ao FUTPBR!",
        "",
        "Grupo oficial da comunidade.",
        "",
        "📅 Jogos",
        "💰 Mensalidades",
        "✅ Confirmações",
        "",
        "Use os comandos do bot para acessar as funções e acompanhar tudo:",
        "",
        "/start",
        "/status",
        "/financeiro",
        "",
        "Bom jogo 👊",
    ]

    kb: InlineKeyboardMarkup | None = None
    if cfg.group_invite_link:
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ Solicitar entrada no grupo", url=cfg.group_invite_link)]]
        )
        lines += [
            "",
            "Clique no botão abaixo para solicitar a entrada.",
        ]
    else:
        lines += [
            "",
            "⚠️ Link do grupo não configurado. Peça para o admin definir `GROUP_INVITE_LINK` no `.env`.",
        ]

    # Se o /start veio do grupo, tenta apagar e manda no privado
    try:
        await context.bot.send_message(
            chat_id=user.id,
            text="\n".join(lines),
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        if update.message and chat.type != "private":
            try:
                await update.message.delete()
            except Exception:
                pass
    except Exception:
        # fallback: responde onde foi chamado (caso DM esteja bloqueada)
        if update.message:
            await update.message.reply_text(
                "\n".join(lines),
                reply_markup=kb,
                disable_web_page_preview=True,
            )

