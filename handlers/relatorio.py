from __future__ import annotations

import sqlite3
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from handlers.permissions import is_effective_admin
from services.finance_report_service import FinanceReportService
from services.telegram_service import TelegramService


def _main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💰 Pagos", callback_data="rel:pagos")],
            [InlineKeyboardButton("⚠️ Inadimplentes", callback_data="rel:inadimplentes")],
            [InlineKeyboardButton("🟡 Em análise", callback_data="rel:analise")],
            [InlineKeyboardButton("📈 Estatísticas", callback_data="rel:stats")],
        ]
    )


async def relatorio(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection, cfg) -> None:
    user = update.effective_user
    if not user:
        return

    # Admin financeiro sempre pode acessar o relatório
    if cfg.finance_admin_id and user.id == cfg.finance_admin_id:
        pass
    elif not await is_effective_admin(update, context, conn):
        if update.message:
            await update.message.reply_text("❌ Você não possui permissão.")
        return

    text = "📊 Relatório Financeiro"
    await context.bot.send_message(chat_id=user.id, text=text, reply_markup=_main_menu(), disable_web_page_preview=True)

    if update.message and update.effective_chat and update.effective_chat.type != "private":
        try:
            await update.message.delete()
        except Exception:
            pass


async def rel_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection, cfg) -> None:
    query = update.callback_query
    admin = update.effective_user
    if not query or not admin:
        return
    await query.answer()

    if cfg.finance_admin_id and admin.id != cfg.finance_admin_id:
        # também deixa admins do chat passarem
        if not await is_effective_admin(update, context, conn):
            await query.answer("Sem permissão.", show_alert=False)
            return

    svc = FinanceReportService(conn)

    if query.data == "rel:inadimplentes":
        rows = svc.list_inadimplentes()
        lines = ["⚠️ Usuários em atraso", ""]
        kb: list[list[InlineKeyboardButton]] = []
        for r in rows[:50]:
            lines.append(f"• {r.display_name} — {r.months_overdue} mês(es)")
            kb.append([InlineKeyboardButton(r.display_name, callback_data=f"rel:user:{r.player_id}")])
        if not rows:
            lines.append("• —")
        kb.append([InlineKeyboardButton("⬅️ Voltar", callback_data="rel:back")])
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
        return

    if query.data == "rel:analise":
        pend = svc.list_pending_submissions()
        lines = ["🟡 Comprovantes pendentes", ""]
        kb: list[list[InlineKeyboardButton]] = []
        for p in pend[:50]:
            lines.append(f"• {p.display_name} — {p.label}")
            kb.append([InlineKeyboardButton(f"{p.display_name} — {p.label}", callback_data=f"rel:sub:{p.submission_id}")])
        if not pend:
            lines.append("• —")
        kb.append([InlineKeyboardButton("⬅️ Voltar", callback_data="rel:back")])
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb))
        return

    if query.data == "rel:pagos":
        last = svc.list_last_approved(limit=20)
        lines = ["✅ Últimos pagamentos aprovados", ""]
        for a in last:
            when = a.reviewed_at or "—"
            lines.append(f"• {a.display_name} — {a.label} — {when}")
        if not last:
            lines.append("• —")
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="rel:back")]]))
        return

    if query.data == "rel:stats":
        s = svc.stats()
        total = f"R$ {s['total_received_cents']/100:.2f}".replace(".", ",")
        text = (
            "📈 Estatísticas\n\n"
            f"✅ Pagos: {s['PAGO']}\n"
            f"⚠️ Atrasados: {s['ATRASADO']}\n"
            f"🟡 Em análise: {s['AGUARDANDO_VALIDACAO']}\n\n"
            f"💵 Total recebido:\n{total}"
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="rel:back")]]))
        return

    if query.data == "rel:back":
        await query.edit_message_text("📊 Relatório Financeiro", reply_markup=_main_menu())
        return


async def rel_user_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection, cfg) -> None:
    query = update.callback_query
    admin = update.effective_user
    if not query or not admin:
        return
    await query.answer()

    if not await is_effective_admin(update, context, conn):
        await query.answer("Sem permissão.", show_alert=False)
        return

    player_id = int(query.data.split(":")[-1])
    svc = FinanceReportService(conn)
    display, lines, total_cents = svc.user_overdue_details(player_id)
    total = f"R$ {total_cents/100:.2f}".replace(".", ",")

    # Ao clicar no usuário inadimplente, já envia cobrança automaticamente
    row = conn.execute("SELECT telegram_id FROM players WHERE id=?;", (player_id,)).fetchone()
    if row:
        tid = int(row["telegram_id"])
        amount = f"R$ {cfg.finance_amount_cents/100:.2f}".replace(".", ",")
        msg = (
            "Olá 👋\n\n"
            "Identificamos mensalidade(s) em atraso.\n\n"
            f"💵 Total em aberto:\n{total}\n"
            f"💵 Valor mensal:\n{amount}\n\n"
            "Use:\n/financeiro\n\n"
            "para regularizar."
        )
        await TelegramService(context.bot).safe_dm(tid, msg)

    text_lines = [f"👤 {display}", ""]
    kb: list[list[InlineKeyboardButton]] = []
    for fee_id, _m, label in lines:
        text_lines.append(f"📅 {label}")
        kb.append([InlineKeyboardButton(f"✅ Marcar pago ({label.split(' — ')[0]})", callback_data=f"rel:paid:{fee_id}:{player_id}")])

    text_lines += ["", "💵 Total:", total]
    kb.append([InlineKeyboardButton("⬅️ Voltar", callback_data="rel:inadimplentes")])
    await query.edit_message_text("\n".join(text_lines), reply_markup=InlineKeyboardMarkup(kb))


async def rel_mark_paid(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection, cfg) -> None:
    query = update.callback_query
    admin = update.effective_user
    if not query or not admin:
        return
    await query.answer()
    if not await is_effective_admin(update, context, conn):
        await query.answer("Sem permissão.", show_alert=False)
        return

    parts = query.data.split(":")
    fee_id = int(parts[2])
    player_id = int(parts[3])

    tid, label = FinanceReportService(conn).mark_month_paid(monthly_fee_id=fee_id, admin_telegram_id=admin.id)
    await TelegramService(context.bot).safe_dm(tid, f"✅ Mensalidade marcada como paga: {label}.")
    await query.answer("Marcado como pago.", show_alert=False)
    # Re-render do detalhe
    await context.bot.send_message(chat_id=admin.id, text="Atualizado. Volte para o usuário para ver o detalhe.")


async def rel_open_submission(update: Update, context: ContextTypes.DEFAULT_TYPE, *, conn: sqlite3.Connection, cfg) -> None:
    query = update.callback_query
    admin = update.effective_user
    if not query or not admin:
        return
    await query.answer()
    if not await is_effective_admin(update, context, conn):
        await query.answer("Sem permissão.", show_alert=False)
        return

    submission_id = int(query.data.split(":")[-1])
    row = conn.execute(
        """
        SELECT ps.telegram_user_id, ps.chat_id, ps.message_id, mf.year, mf.month,
               p.username, p.first_name
        FROM payment_submissions ps
        JOIN monthly_fees mf ON mf.id = ps.monthly_fee_id
        LEFT JOIN players p ON p.telegram_id = ps.telegram_user_id
        WHERE ps.id = ?;
        """,
        (submission_id,),
    ).fetchone()
    if not row:
        await query.answer("Comprovante não encontrado.", show_alert=False)
        return

    y, m = int(row["year"]), int(row["month"])
    label = f"{m:02d}/{y}"
    name = f"@{row['username']}" if row["username"] else (row["first_name"] or "Jogador")

    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ Aprovar", callback_data=f"fin:approve:{submission_id}"),
            InlineKeyboardButton("❌ Recusar", callback_data=f"fin:reject:{submission_id}"),
        ],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="rel:analise")]]
    )
    await query.edit_message_text(f"🧾 {name} — {label}\n\nUse os botões abaixo para aprovar/recusar.", reply_markup=kb)

