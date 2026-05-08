from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from database import utcnow_iso
from services.finance_service import MONTHS_PT
from services.repositories import PlayerRepository


@dataclass(frozen=True)
class InadimplenteRow:
    player_id: int
    telegram_id: int
    display_name: str
    months_overdue: int


@dataclass(frozen=True)
class PendingSubmissionRow:
    submission_id: int
    telegram_user_id: int
    display_name: str
    label: str  # Maio/2026


@dataclass(frozen=True)
class ApprovedPaymentRow:
    submission_id: int
    telegram_user_id: int
    display_name: str
    label: str
    reviewed_at: str | None
    approved_by_telegram_id: int | None


class FinanceReportService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._players = PlayerRepository(conn)

    def list_inadimplentes(self) -> list[InadimplenteRow]:
        rows = self._conn.execute(
            """
            SELECT
              p.id AS player_id,
              p.telegram_id AS telegram_id,
              p.username AS username,
              p.first_name AS first_name,
              SUM(CASE WHEN mf.status = 'ATRASADO' THEN 1 ELSE 0 END) AS months_overdue
            FROM monthly_fees mf
            JOIN players p ON p.id = mf.player_id
            WHERE mf.status = 'ATRASADO'
            GROUP BY p.id
            ORDER BY months_overdue DESC, p.id ASC;
            """
        ).fetchall()

        result: list[InadimplenteRow] = []
        for r in rows:
            name = f"@{r['username']}" if r["username"] else (r["first_name"] or "Jogador")
            result.append(
                InadimplenteRow(
                    player_id=int(r["player_id"]),
                    telegram_id=int(r["telegram_id"]),
                    display_name=name,
                    months_overdue=int(r["months_overdue"] or 0),
                )
            )
        return result

    def user_overdue_details(self, player_id: int) -> tuple[str, list[tuple[int, int, str]], int]:
        p = self._conn.execute(
            "SELECT telegram_id, username, first_name FROM players WHERE id = ?;",
            (player_id,),
        ).fetchone()
        if not p:
            raise RuntimeError("Usuário não encontrado.")

        display = f"@{p['username']}" if p["username"] else (p["first_name"] or "Jogador")
        fees = self._conn.execute(
            """
            SELECT id, year, month, status, amount_cents
            FROM monthly_fees
            WHERE player_id = ? AND status IN ('ATRASADO','RECUSADO','PENDENTE')
            ORDER BY year ASC, month ASC;
            """,
            (player_id,),
        ).fetchall()

        lines: list[tuple[int, int, str]] = []
        total_cents = 0
        for f in fees:
            y, m = int(f["year"]), int(f["month"])
            label = f"{MONTHS_PT[m-1]}/{y} — {str(f['status'])}"
            lines.append((int(f["id"]), m, label))
            if str(f["status"]) in ("ATRASADO", "RECUSADO", "PENDENTE"):
                total_cents += int(f["amount_cents"])

        return display, lines, total_cents

    def list_pending_submissions(self) -> list[PendingSubmissionRow]:
        rows = self._conn.execute(
            """
            SELECT ps.id AS submission_id, ps.telegram_user_id, mf.year, mf.month,
                   p.username, p.first_name
            FROM payment_submissions ps
            JOIN monthly_fees mf ON mf.id = ps.monthly_fee_id
            LEFT JOIN players p ON p.telegram_id = ps.telegram_user_id
            WHERE ps.status = 'AGUARDANDO_VALIDACAO'
            ORDER BY ps.id DESC;
            """
        ).fetchall()

        out: list[PendingSubmissionRow] = []
        for r in rows:
            y, m = int(r["year"]), int(r["month"])
            label = f"{MONTHS_PT[m-1]}/{y}"
            name = f"@{r['username']}" if r["username"] else (r["first_name"] or "Jogador")
            out.append(
                PendingSubmissionRow(
                    submission_id=int(r["submission_id"]),
                    telegram_user_id=int(r["telegram_user_id"]),
                    display_name=name,
                    label=label,
                )
            )
        return out

    def list_last_approved(self, limit: int = 20) -> list[ApprovedPaymentRow]:
        rows = self._conn.execute(
            """
            SELECT ps.id AS submission_id, ps.telegram_user_id, ps.reviewed_at, ps.reviewed_by_telegram_id,
                   mf.year, mf.month,
                   p.username, p.first_name
            FROM payment_submissions ps
            JOIN monthly_fees mf ON mf.id = ps.monthly_fee_id
            LEFT JOIN players p ON p.telegram_id = ps.telegram_user_id
            WHERE ps.status = 'APROVADO'
            ORDER BY ps.reviewed_at DESC, ps.id DESC
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()

        out: list[ApprovedPaymentRow] = []
        for r in rows:
            y, m = int(r["year"]), int(r["month"])
            label = f"{MONTHS_PT[m-1]}/{y}"
            name = f"@{r['username']}" if r["username"] else (r["first_name"] or "Jogador")
            out.append(
                ApprovedPaymentRow(
                    submission_id=int(r["submission_id"]),
                    telegram_user_id=int(r["telegram_user_id"]),
                    display_name=name,
                    label=label,
                    reviewed_at=r["reviewed_at"],
                    approved_by_telegram_id=r["reviewed_by_telegram_id"],
                )
            )
        return out

    def stats(self) -> dict[str, int]:
        def c(status: str) -> int:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM monthly_fees WHERE status = ?;", (status,)).fetchone()
            return int(row["c"]) if row else 0

        total_received_row = self._conn.execute(
            """
            SELECT COALESCE(SUM(amount_cents),0) AS s
            FROM monthly_fees
            WHERE status = 'PAGO';
            """
        ).fetchone()
        total_received_cents = int(total_received_row["s"]) if total_received_row else 0

        return {
            "PAGO": c("PAGO"),
            "ATRASADO": c("ATRASADO"),
            "AGUARDANDO_VALIDACAO": c("AGUARDANDO_VALIDACAO"),
            "RECUSADO": c("RECUSADO"),
            "total_received_cents": total_received_cents,
        }

    def log_charge(self, *, telegram_user_id: int, reference: str, kind: str) -> bool:
        try:
            self._conn.execute(
                "INSERT INTO cobranca_logs(telegram_user_id, reference, kind, created_at) VALUES(?,?,?,?);",
                (telegram_user_id, reference, kind, utcnow_iso()),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def mark_month_paid(self, *, monthly_fee_id: int, admin_telegram_id: int) -> tuple[int, str]:
        row = self._conn.execute(
            "SELECT player_id, year, month FROM monthly_fees WHERE id = ?;",
            (monthly_fee_id,),
        ).fetchone()
        if not row:
            raise RuntimeError("Mensalidade não encontrada.")

        self._conn.execute(
            """
            UPDATE monthly_fees
            SET status='PAGO', updated_at=?, approved_by_telegram_id=?, approved_at=?
            WHERE id=?;
            """,
            (utcnow_iso(), admin_telegram_id, utcnow_iso(), monthly_fee_id),
        )

        player = self._conn.execute("SELECT telegram_id FROM players WHERE id=?;", (int(row["player_id"]),)).fetchone()
        tid = int(player["telegram_id"]) if player else 0
        label = f"{MONTHS_PT[int(row['month'])-1]}/{int(row['year'])}"
        return tid, label

