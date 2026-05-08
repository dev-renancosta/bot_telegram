from __future__ import annotations

import sqlite3

from telegram import Update
from telegram.ext import ContextTypes

from services.admin_service import AdminService


async def is_effective_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, conn: sqlite3.Connection) -> bool:
    user = update.effective_user
    chat = update.effective_chat
    if not user or not chat:
        return False

    # Preferência: admins reais do chat também podem operar (útil quando DB ainda vazio)
    try:
        member = await context.bot.get_chat_member(chat_id=chat.id, user_id=user.id)
        if member.status in ("administrator", "creator"):
            return True
    except Exception:
        pass

    return AdminService(conn).is_admin(user.id)

