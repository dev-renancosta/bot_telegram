from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from services.finance_service import FinanceService
from services.telegram_service import TelegramService


async def financeiro(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection, cfg) -> None:
    user = update.effective_user
    if not user:
        return

    panel = FinanceService(conn).build_panel_for_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        now=datetime.now(tz=cfg.tz),
        amount_cents=cfg.finance_amount_cents,
        finance_start_year=cfg.finance_start_year,
        finance_start_month=cfg.finance_start_month,
    )

    # Responder sempre no privado
    await context.bot.send_message(chat_id=user.id, text=panel.text, reply_markup=panel.keyboard, disable_web_page_preview=True)

    # Se foi chamado no grupo, apagar para não poluir
    if update.message and update.effective_chat and update.effective_chat.type != "private":
        try:
            await update.message.delete()
        except Exception:
            pass


async def fin_month_details(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection, cfg) -> None:
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return
    await query.answer()

    fee_id = int(query.data.split(":")[-1])
    if not cfg.finance_pix_copy_paste:
        await query.answer("PIX não configurado.", show_alert=False)
        return

    panel = FinanceService(conn).build_month_payment_details(
        monthly_fee_id=fee_id,
        pix_copy_paste=cfg.finance_pix_copy_paste,
        amount_cents=cfg.finance_amount_cents,
    )
    # Ao clicar no mês, já entra em modo de receber comprovante (sem botão extra)
    context.user_data["awaiting_receipt_fee_id"] = fee_id

    # Botão de copiar PIX automaticamente (quando suportado pelo cliente/lib)
    kb: InlineKeyboardMarkup | None = None
    try:
        from telegram import CopyTextButton  # type: ignore

        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("PIX", copy_text=CopyTextButton(cfg.finance_pix_copy_paste))]]
        )
    except Exception:
        kb = None

    # Envia os detalhes + botão PIX (ou fallback sem botão)
    await context.bot.send_message(
        chat_id=user.id,
        text=panel.text,
        reply_markup=kb,
        disable_web_page_preview=True,
    )

    # Pequeno delay para UX (tempo de copiar o PIX) e depois pedir comprovante
    await asyncio.sleep(3)
    await context.bot.send_message(
        chat_id=user.id,
        text="📎 Agora envie o comprovante (foto, PDF ou documento).",
        disable_web_page_preview=True,
    )


async def fin_receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection, cfg) -> None:
    chat = update.effective_chat
    user = update.effective_user
    msg = update.message
    if not chat or not user or not msg:
        return

    if chat.type != "private":
        return

    fee_id = context.user_data.get("awaiting_receipt_fee_id")
    if not fee_id:
        return

    file_id = None
    file_unique_id = None
    file_type = None
    original_name = None
    mime_type = None

    if msg.photo:
        file_type = "photo"
        best = msg.photo[-1]
        file_id = best.file_id
        file_unique_id = best.file_unique_id
    elif msg.document:
        file_type = "document"
        file_id = msg.document.file_id
        file_unique_id = msg.document.file_unique_id
        original_name = msg.document.file_name
        mime_type = msg.document.mime_type

    if not file_id or not file_type:
        await msg.reply_text("Envie uma foto ou documento (PDF/arquivo) como comprovante.")
        return

    submission_id = FinanceService(conn).register_submission(
        monthly_fee_id=int(fee_id),
        telegram_user_id=user.id,
        file_id=file_id,
        file_unique_id=file_unique_id,
        file_type=file_type,
        original_file_name=original_name,
        mime_type=mime_type,
        message_id=msg.message_id,
        chat_id=chat.id,
    )

    context.user_data.pop("awaiting_receipt_fee_id", None)

    await msg.reply_text("🟡 Aguardando validação.")

    # Encaminhar para o admin financeiro
    if not cfg.finance_admin_id:
        return

    kb = (
        [[
            ("✅ Aprovar", f"fin:approve:{submission_id}"),
            ("❌ Recusar", f"fin:reject:{submission_id}"),
        ]]
    )
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    admin_keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(t, callback_data=cb) for t, cb in kb[0]]]
    )

    # Copiar o comprovante (sem baixar binário)
    await context.bot.copy_message(
        chat_id=cfg.finance_admin_id,
        from_chat_id=chat.id,
        message_id=msg.message_id,
    )
    await context.bot.send_message(
        chat_id=cfg.finance_admin_id,
        text=f"🧾 Novo comprovante\n\nUsuário: {user.full_name}\nTelegram ID: {user.id}\nSubmission ID: {submission_id}",
        reply_markup=admin_keyboard,
        disable_web_page_preview=True,
    )


async def fin_review(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection, cfg, approved: bool) -> None:
    query = update.callback_query
    admin = update.effective_user
    if not query or not admin:
        return
    await query.answer()

    # Segurança: apenas o admin financeiro
    if cfg.finance_admin_id and admin.id != cfg.finance_admin_id:
        await query.answer("Sem permissão.", show_alert=False)
        return

    submission_id = int(query.data.split(":")[-1])
    fee_id, user_id, label = FinanceService(conn).review_submission(
        submission_id=submission_id,
        approved=approved,
        admin_telegram_id=admin.id,
        admin_note=None,
    )

    if approved:
        await query.edit_message_text("✅ Aprovado.")
        await TelegramService(context.bot).safe_dm(user_id, f"✅ Pagamento aprovado: {label}. Obrigado!")
    else:
        await query.edit_message_text("❌ Recusado.")
        await TelegramService(context.bot).safe_dm(user_id, f"❌ Pagamento recusado: {label}. Envie um novo comprovante via /financeiro.")

