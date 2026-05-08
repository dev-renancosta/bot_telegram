from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from services.repositories import ConfirmationRepository, PlayerRepository


@dataclass(frozen=True)
class ConfirmationResult:
    toast: str
    promoted_telegram_id: int | None = None
    promoted_name: str | None = None


class ConfirmationService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._players = PlayerRepository(conn)
        self._confirmations = ConfirmationRepository(conn)

    def apply_toggle(
        self,
        *,
        game_id: int,
        max_players: int,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
        action: str,  # "vou" | "nao_vou"
    ) -> ConfirmationResult:
        player_id = self._players.upsert(telegram_id, username, first_name)
        current = self._confirmations.get_status(game_id, player_id)

        if action not in ("vou", "nao_vou"):
            return ConfirmationResult(toast="Ação inválida.")

        # Toggle: clicar no mesmo estado remove a resposta (limpo e silencioso)
        if current == action:
            self._confirmations.clear(game_id, player_id)
            return ConfirmationResult(toast="Resposta removida.")

        if action == "nao_vou":
            self._confirmations.set_status(game_id, player_id, "nao_vou")
            promoted = self._promote_from_waitlist_if_possible(game_id, max_players)
            if promoted:
                return ConfirmationResult(toast="❌ Marcado como não vou.", **promoted)
            return ConfirmationResult(toast="❌ Marcado como não vou.")

        # action == "vou"
        confirmed_count = self._confirmations.count_by_status(game_id, "vou")
        if confirmed_count < max_players:
            self._confirmations.set_status(game_id, player_id, "vou")
            return ConfirmationResult(toast="✅ Presença confirmada.")

        # sem vaga -> espera
        self._confirmations.set_status(game_id, player_id, "espera")
        return ConfirmationResult(toast="🕒 Você entrou na fila de espera.")

    def _promote_from_waitlist_if_possible(self, game_id: int, max_players: int) -> dict | None:
        confirmed = self._confirmations.count_by_status(game_id, "vou")
        if confirmed >= max_players:
            return None
        waiters = self._confirmations.list_by_status(game_id, "espera")
        if not waiters:
            return None

        promote_player_id = waiters[0]
        self._confirmations.set_status(game_id, promote_player_id, "vou")

        row = self._conn.execute(
            "SELECT telegram_id FROM players WHERE id = ?;",
            (promote_player_id,),
        ).fetchone()
        if not row:
            return None

        promoted_tid = int(row["telegram_id"])
        promoted_name = self._players.get_display_name(promote_player_id)
        return {"promoted_telegram_id": promoted_tid, "promoted_name": promoted_name}

