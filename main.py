from __future__ import annotations

import asyncio
import logging
import signal

from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from database import Database
from handlers.callbacks import list_toggle
from handlers.commands_admin import apagarlista, criarlista, status
from handlers.finance import (
    financeiro,
    fin_month_details,
    fin_receive_receipt,
    fin_review,
)
from handlers.join_requests import auto_approve_join_request
from handlers.onboarding import start
from handlers.relatorio import (
    relatorio,
    rel_menu,
    rel_user_detail,
    rel_mark_paid,
    rel_open_submission,
)
from scheduler import build_scheduler
from services.admin_service import AdminService
from services.telegram_service import TelegramService
from utils.config import load_config
from utils.logging import setup_logging


logger = logging.getLogger(__name__)


def _get_conn(application: Application):
    return application.bot_data["db_conn"]


def _get_cfg(application: Application):
    return application.bot_data["cfg"]


def _wrap(handler_fn):
    async def _inner(update, context):
        conn = _get_conn(context.application)
        cfg = _get_cfg(context.application)
        return await handler_fn(update, context, conn=conn, cfg=cfg)

    return _inner


def _wrap_conn(handler_fn):
    async def _inner(update, context):
        conn = _get_conn(context.application)
        return await handler_fn(update, context, conn=conn)

    return _inner


async def main() -> None:
    setup_logging()
    cfg = load_config()

    db = Database(cfg.db_path)
    db.init()
    conn = db.connect()
    AdminService(conn).bootstrap_admins(cfg.admin_ids)

    app = Application.builder().token(cfg.bot_token).build()
    app.bot_data["db_conn"] = conn
    app.bot_data["cfg"] = cfg

    app.add_handler(CommandHandler("start", _wrap(start)))
    app.add_handler(CommandHandler("apagarlista", _wrap(apagarlista)))
    app.add_handler(CommandHandler("criarlista", _wrap(criarlista)))
    app.add_handler(CommandHandler("status", _wrap_conn(status)))
    app.add_handler(CommandHandler("financeiro", _wrap(financeiro)))
    app.add_handler(CommandHandler("relatorio", _wrap(relatorio)))
    app.add_handler(CallbackQueryHandler(_wrap(list_toggle), pattern=r"^list:(vou|nao_vou)$"))

    app.add_handler(CallbackQueryHandler(_wrap(fin_month_details), pattern=r"^fin:month:\d+$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: fin_review(u, c, conn=_get_conn(c.application), cfg=_get_cfg(c.application), approved=True), pattern=r"^fin:approve:\d+$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: fin_review(u, c, conn=_get_conn(c.application), cfg=_get_cfg(c.application), approved=False), pattern=r"^fin:reject:\d+$"))

    app.add_handler(CallbackQueryHandler(_wrap(rel_menu), pattern=r"^rel:(pagos|inadimplentes|analise|stats|back)$"))
    app.add_handler(CallbackQueryHandler(_wrap(rel_user_detail), pattern=r"^rel:user:\d+$"))
    app.add_handler(CallbackQueryHandler(_wrap(rel_mark_paid), pattern=r"^rel:paid:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(_wrap(rel_open_submission), pattern=r"^rel:sub:\d+$"))

    # Receber comprovante em DM (foto/doc). Handler genérico, filtrado no próprio método.
    from telegram.ext import MessageHandler, filters
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, _wrap(fin_receive_receipt)))

    # Aprovação automática de “Solicitar entrada”
    from telegram.ext import ChatJoinRequestHandler
    app.add_handler(ChatJoinRequestHandler(_wrap(auto_approve_join_request)))

    telegram = TelegramService(app.bot)
    scheduler = build_scheduler(conn=conn, cfg=cfg, telegram=telegram)

    async with app:
        scheduler.start()
        await app.start()
        await app.updater.start_polling()
        logger.info("Bot iniciado.")

        stop_event = asyncio.Event()

        def _stop(*_):
            stop_event.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _stop)
            except NotImplementedError:
                # Windows
                signal.signal(sig, lambda *_: _stop())

        await stop_event.wait()

        logger.info("Encerrando...")
        scheduler.shutdown(wait=False)
        await app.updater.stop()
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())

