from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from database import utcnow_iso
from services.repositories import PlayerRepository


MONTHS_PT = [
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]


@dataclass(frozen=True)
class FinancePanel:
    text: str
    keyboard: InlineKeyboardMarkup | None


class FinanceService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._players = PlayerRepository(conn)

    def ensure_fee_row(
        self,
        *,
        player_id: int,
        year: int,
        month: int,
        amount_cents: int,
        status: str,
    ) -> int:
        now = utcnow_iso()
        self._conn.execute(
            """
            INSERT INTO monthly_fees(player_id, year, month, amount_cents, status, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(player_id, year, month) DO NOTHING;
            """,
            (player_id, year, month, amount_cents, status, now, now),
        )
        row = self._conn.execute(
            "SELECT id FROM monthly_fees WHERE player_id = ? AND year = ? AND month = ?;",
            (player_id, year, month),
        ).fetchone()
        return int(row["id"])

    def _get_fee(self, player_id: int, year: int, month: int):
        return self._conn.execute(
            "SELECT * FROM monthly_fees WHERE player_id = ? AND year = ? AND month = ?;",
            (player_id, year, month),
        ).fetchone()

    def _set_fee_status(self, fee_id: int, status: str, *, approved_by: int | None = None) -> None:
        now = utcnow_iso()
        self._conn.execute(
            """
            UPDATE monthly_fees
            SET status = ?, updated_at = ?, approved_by_telegram_id = COALESCE(?, approved_by_telegram_id),
                approved_at = CASE WHEN ? IS NOT NULL THEN ? ELSE approved_at END
            WHERE id = ?;
            """,
            (status, now, approved_by, approved_by, now, fee_id),
        )

    def build_panel_for_user(
        self,
        *,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        now: datetime,
        amount_cents: int,
        finance_start_year: int,
        finance_start_month: int,
    ) -> FinancePanel:
        player_id = self._players.upsert(telegram_id, username, first_name)

        rows: list[tuple[int, int, str, int]] = []  # (year, month, status, fee_id)

        y, m = finance_start_year, finance_start_month
        while (y, m) <= (now.year, now.month):
            is_past = (y, m) < (now.year, now.month)
            default_status = "ATRASADO" if is_past else "PENDENTE"
            fee_id = self.ensure_fee_row(
                player_id=player_id,
                year=y,
                month=m,
                amount_cents=amount_cents,
                status=default_status,
            )
            fee = self._get_fee(player_id, y, m)
            status = str(fee["status"]) if fee else default_status
            rows.append((y, m, status, fee_id))

            m += 1
            if m == 13:
                m = 1
                y += 1

        lines = ["💰 Painel Financeiro", ""]
        overdue_buttons: list[list[InlineKeyboardButton]] = []

        for year, month, status, fee_id in rows:
            label = MONTHS_PT[month - 1]
            if status == "PAGO":
                icon = "🟢"
            elif status == "AGUARDANDO_VALIDACAO":
                icon = "🟡"
            elif status == "RECUSADO":
                icon = "🟠"
            elif status == "ATRASADO":
                icon = "🔴"
            else:
                icon = "⚪"
            lines.append(f"{icon} {label}/{year} - {status.replace('_', ' ').title()}")

            if status == "ATRASADO":
                overdue_buttons.append(
                    [InlineKeyboardButton(f"🔴 Pagar {label}/{year}", callback_data=f"fin:month:{fee_id}")]
                )

        keyboard = InlineKeyboardMarkup(overdue_buttons) if overdue_buttons else None
        return FinancePanel(text="\n".join(lines), keyboard=keyboard)

    def build_month_payment_details(
        self,
        *,
        monthly_fee_id: int,
        pix_copy_paste: str,
        amount_cents: int,
    ) -> FinancePanel:
        fee = self._conn.execute("SELECT year, month, status FROM monthly_fees WHERE id = ?;", (monthly_fee_id,)).fetchone()
        if not fee:
            return FinancePanel(text="Mês não encontrado.", keyboard=None)

        year, month, status = int(fee["year"]), int(fee["month"]), str(fee["status"])
        label = f"{MONTHS_PT[month-1]}/{year}"
        amount = f"R$ {amount_cents/100:.2f}".replace(".", ",")

        text = (
            f"💰 Mensalidade {label}\n\n"
            f"Valor: {amount}\n"
            f"Status: {status}"
        )
        # Fluxo novo: sem botão de comprovante. Ao clicar no mês, o bot já pede o arquivo após um delay.
        return FinancePanel(text=text, keyboard=None)

    def register_submission(
        self,
        *,
        monthly_fee_id: int,
        telegram_user_id: int,
        file_id: str,
        file_unique_id: str | None,
        file_type: str,
        original_file_name: str | None,
        mime_type: str | None,
        message_id: int | None,
        chat_id: int | None,
    ) -> int:
        now = utcnow_iso()
        self._conn.execute(
            """
            INSERT INTO payment_submissions(
              monthly_fee_id, telegram_user_id, file_id, file_unique_id, file_type,
              original_file_name, mime_type, message_id, chat_id, status, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?);
            """,
            (
                monthly_fee_id,
                telegram_user_id,
                file_id,
                file_unique_id,
                file_type,
                original_file_name,
                mime_type,
                message_id,
                chat_id,
                "AGUARDANDO_VALIDACAO",
                now,
            ),
        )
        submission_id = int(self._conn.execute("SELECT last_insert_rowid() AS id;").fetchone()["id"])
        self._set_fee_status(monthly_fee_id, "AGUARDANDO_VALIDACAO")
        return submission_id

    def review_submission(
        self,
        *,
        submission_id: int,
        approved: bool,
        admin_telegram_id: int,
        admin_note: str | None = None,
    ) -> tuple[int, int, str]:
        row = self._conn.execute(
            "SELECT monthly_fee_id, telegram_user_id FROM payment_submissions WHERE id = ?;",
            (submission_id,),
        ).fetchone()
        if not row:
            raise RuntimeError("Comprovante não encontrado.")

        fee_id = int(row["monthly_fee_id"])
        user_id = int(row["telegram_user_id"])
        now = utcnow_iso()
        new_status = "APROVADO" if approved else "RECUSADO"

        self._conn.execute(
            """
            UPDATE payment_submissions
            SET status = ?, reviewed_at = ?, reviewed_by_telegram_id = ?, admin_note = ?
            WHERE id = ?;
            """,
            (new_status, now, admin_telegram_id, admin_note, submission_id),
        )

        if approved:
            self._set_fee_status(fee_id, "PAGO", approved_by=admin_telegram_id)
        else:
            self._set_fee_status(fee_id, "RECUSADO")

        fee = self._conn.execute("SELECT year, month FROM monthly_fees WHERE id = ?;", (fee_id,)).fetchone()
        label = f"{MONTHS_PT[int(fee['month'])-1]}/{int(fee['year'])}" if fee else "mensalidade"
        return fee_id, user_id, label

