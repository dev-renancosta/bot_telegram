from __future__ import annotations

import sqlite3

from services.repositories import ConfirmationRepository


class StatusService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._confirmations = ConfirmationRepository(conn)

    def get_stats(self, game_id: int) -> dict[str, int]:
        return {
            "vou": self._confirmations.count_by_status(game_id, "vou"),
            "espera": self._confirmations.count_by_status(game_id, "espera"),
            "nao_vou": self._confirmations.count_by_status(game_id, "nao_vou"),
        }

