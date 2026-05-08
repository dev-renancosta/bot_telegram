from __future__ import annotations

import sqlite3
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from services.finance_service import FinanceService
from services.repositories import MembershipRepository, PlayerRepository
from services.telegram_service import TelegramService


async def auto_approve_join_request(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    conn: sqlite3.Connection,
    cfg,
) -> None:
    req = update.chat_join_request
    if not req:
        return

    chat = req.chat
    user = req.from_user
    if not chat or not user:
        return

    # Segurança: só processa para o grupo configurado
    if int(chat.id) != int(cfg.group_id):
        return

    # Aprovação automática (profissional e zero fricção)
    try:
        await context.bot.approve_chat_join_request(chat_id=chat.id, user_id=user.id)
    except Exception:
        # Se falhar, não cria mensalidade/membership (evita marcar como membro sem estar no grupo)
        return

    # Garantir cadastro básico
    player_id = PlayerRepository(conn).upsert(user.id, user.username, user.first_name)

    # Ativar membro rastreável
    MembershipRepository(conn).activate(player_id=player_id, group_id=int(chat.id))

    # Criar mensalidade do mês atual (PENDENTE) de forma idempotente
    now = datetime.now(tz=cfg.tz)
    FinanceService(conn).ensure_fee_row(
        player_id=player_id,
        year=now.year,
        month=now.month,
        amount_cents=cfg.finance_amount_cents,
        status="PENDENTE",
    )

    # Confirmação em DM (não quebra se o usuário bloquear DM)
    await TelegramService(context.bot).safe_dm(
        user.id,
        "✅ Entrada aprovada!\n\n"
        "Você já é um membro rastreável no sistema e a mensalidade do mês atual foi criada como PENDENTE.\n\n"
        "Use /financeiro para ver o painel e enviar comprovante, se necessário.",
    )

