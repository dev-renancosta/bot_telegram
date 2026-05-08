from __future__ import annotations

import logging
import sqlite3
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from services.game_service import GameService
from services.finance_report_service import FinanceReportService
from services.telegram_service import TelegramService
from utils.time import compute_game_date, nth_business_day


logger = logging.getLogger(__name__)


def build_scheduler(*, conn: sqlite3.Connection, cfg, telegram: TelegramService) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=cfg.tz)

    async def job_create_list():
        try:
            game_date = compute_game_date(cfg.game_day, cfg.tz)
            await GameService(conn, telegram).create_or_refresh_list(
                chat_id=cfg.group_id,
                game_date=game_date,
                max_players=cfg.max_players,
                game_name=cfg.game_name,
                game_day=cfg.game_day,
                game_time=cfg.game_time,
                game_location=cfg.game_location,
                game_address=cfg.game_address,
            )
        except Exception:
            logger.exception("Falha no job de criar lista")

    async def job_reminder():
        try:
            await telegram.send_notice(cfg.group_id, "⚠️ Não esqueçam de responder a lista do futebol.")
        except Exception:
            logger.exception("Falha no job de lembrete")

    async def job_today():
        try:
            await telegram.send_notice(cfg.group_id, f"⚽ Hoje tem jogo às {cfg.game_time}.")
        except Exception:
            logger.exception("Falha no job de aviso do jogo")

    async def job_close():
        try:
            await GameService(conn, telegram).close_list(
                chat_id=cfg.group_id,
                game_name=cfg.game_name,
                game_day=cfg.game_day,
                game_time=cfg.game_time,
                game_location=cfg.game_location,
                game_address=cfg.game_address,
            )
        except Exception:
            logger.exception("Falha no job de fechar lista")

    async def job_auto_charge():
        """
        Rodamos diariamente e só envia no 5º dia útil do mês.
        Anti-spam: cobranca_logs UNIQUE(user_id, reference, kind).
        """
        try:
            now = datetime.now(tz=cfg.tz)
            target = nth_business_day(now.year, now.month, 5)
            if now.date() != target:
                return

            reference = f"{now.year:04d}-{now.month:02d}"
            # Cobra quem não está PAGO no mês atual
            rows = conn.execute(
                """
                SELECT p.telegram_id
                FROM monthly_fees mf
                JOIN players p ON p.id = mf.player_id
                WHERE mf.year = ? AND mf.month = ? AND mf.status != 'PAGO';
                """,
                (now.year, now.month),
            ).fetchall()

            amount = f"R$ {cfg.finance_amount_cents/100:.2f}".replace(".", ",")
            msg = (
                "🔔 Mensalidade disponível\n\n"
                "Olá 👋\n\n"
                "Sua mensalidade do mês atual está disponível.\n\n"
                f"💵 Valor:\n{amount}\n\n"
                "Utilize:\n/financeiro\n\n"
                "para visualizar e enviar comprovante."
            )

            svc = FinanceReportService(conn)
            for r in rows:
                tid = int(r["telegram_id"])
                if not svc.log_charge(telegram_user_id=tid, reference=reference, kind="AUTO_AVAILABLE"):
                    continue
                await telegram.safe_dm(tid, msg)
        except Exception:
            logger.exception("Falha no job de cobrança automática")

    scheduler.add_job(job_create_list, CronTrigger(day_of_week="wed", hour=12, minute=0), id="create_list", replace_existing=True)
    scheduler.add_job(job_reminder, CronTrigger(day_of_week="thu", hour=12, minute=0), id="reminder", replace_existing=True)
    scheduler.add_job(job_today, CronTrigger(day_of_week="fri", hour=12, minute=0), id="today", replace_existing=True)
    scheduler.add_job(job_close, CronTrigger(day_of_week="fri", hour=17, minute=0), id="close", replace_existing=True)
    scheduler.add_job(job_auto_charge, CronTrigger(hour=9, minute=0), id="auto_charge", replace_existing=True)

    return scheduler

