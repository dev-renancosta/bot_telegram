from __future__ import annotations

import sqlite3

from database import utcnow_iso


class AdminService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def bootstrap_admins(self, admin_ids: tuple[int, ...]) -> None:
        if not admin_ids:
            return
        for telegram_id in admin_ids:
            self._conn.execute(
                "INSERT OR IGNORE INTO admins(telegram_id, created_at) VALUES (?, ?);",
                (telegram_id, utcnow_iso()),
            )

    def is_admin(self, telegram_id: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM admins WHERE telegram_id = ? LIMIT 1;",
            (telegram_id,),
        ).fetchone()
        return row is not None
