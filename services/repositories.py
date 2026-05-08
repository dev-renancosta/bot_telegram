from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from database import utcnow_iso


@dataclass(frozen=True)
class GameRow:
    id: int
    chat_id: int
    message_id: int | None
    created_at: str
    game_date: str
    status: str
    max_players: int


class GameRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_current(self, chat_id: int) -> GameRow | None:
        row = self._conn.execute(
            "SELECT * FROM games WHERE chat_id = ? AND status IN ('open','closed') ORDER BY id DESC LIMIT 1;",
            (chat_id,),
        ).fetchone()
        return GameRow(**dict(row)) if row else None

    def get_open(self, chat_id: int) -> GameRow | None:
        row = self._conn.execute(
            "SELECT * FROM games WHERE chat_id = ? AND status = 'open' ORDER BY id DESC LIMIT 1;",
            (chat_id,),
        ).fetchone()
        return GameRow(**dict(row)) if row else None

    def create(self, chat_id: int, game_date: date, max_players: int) -> int:
        cur = self._conn.execute(
            "INSERT INTO games(chat_id, message_id, created_at, game_date, status, max_players) VALUES (?, NULL, ?, ?, 'open', ?);",
            (chat_id, utcnow_iso(), game_date.isoformat(), max_players),
        )
        return int(cur.lastrowid)

    def set_message_id(self, game_id: int, message_id: int) -> None:
        self._conn.execute("UPDATE games SET message_id = ? WHERE id = ?;", (message_id, game_id))

    def set_status(self, game_id: int, status: str) -> None:
        self._conn.execute("UPDATE games SET status = ? WHERE id = ?;", (status, game_id))

    def delete(self, game_id: int) -> None:
        self._conn.execute("DELETE FROM games WHERE id = ?;", (game_id,))


@dataclass(frozen=True)
class PlayerRow:
    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    created_at: str


class PlayerRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert(self, telegram_id: int, username: str | None, first_name: str | None) -> int:
        self._conn.execute(
            "INSERT OR IGNORE INTO players(telegram_id, username, first_name, created_at) VALUES(?,?,?,?);",
            (telegram_id, username, first_name, utcnow_iso()),
        )
        self._conn.execute(
            "UPDATE players SET username = ?, first_name = ? WHERE telegram_id = ?;",
            (username, first_name, telegram_id),
        )
        row = self._conn.execute(
            "SELECT id FROM players WHERE telegram_id = ?;",
            (telegram_id,),
        ).fetchone()
        return int(row["id"])

    def get_display_name(self, player_id: int) -> str:
        row = self._conn.execute(
            "SELECT username, first_name FROM players WHERE id = ?;",
            (player_id,),
        ).fetchone()
        if not row:
            return "Jogador"
        if row["username"]:
            return f"@{row['username']}"
        return row["first_name"] or "Jogador"


@dataclass(frozen=True)
class MembershipRow:
    id: int
    player_id: int
    group_id: int
    status: str
    joined_at: str
    updated_at: str


class MembershipRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def activate(self, *, player_id: int, group_id: int) -> int:
        """
        Marca o usuário como membro rastreável do grupo.
        Idempotente via UNIQUE(player_id, group_id).
        """
        now = utcnow_iso()
        self._conn.execute(
            """
            INSERT INTO memberships(player_id, group_id, status, joined_at, updated_at)
            VALUES(?, ?, 'ACTIVE', ?, ?)
            ON CONFLICT(player_id, group_id) DO UPDATE
            SET status = 'ACTIVE', updated_at = excluded.updated_at;
            """,
            (player_id, group_id, now, now),
        )
        row = self._conn.execute(
            "SELECT id FROM memberships WHERE player_id = ? AND group_id = ?;",
            (player_id, group_id),
        ).fetchone()
        return int(row["id"])


class ConfirmationRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_status(self, game_id: int, player_id: int) -> str | None:
        row = self._conn.execute(
            "SELECT status FROM confirmations WHERE game_id = ? AND player_id = ?;",
            (game_id, player_id),
        ).fetchone()
        return str(row["status"]) if row else None

    def set_status(self, game_id: int, player_id: int, status: str) -> None:
        self._conn.execute(
            """
            INSERT INTO confirmations(game_id, player_id, status, created_at)
            VALUES(?,?,?,?)
            ON CONFLICT(game_id, player_id) DO UPDATE SET status = excluded.status;
            """,
            (game_id, player_id, status, utcnow_iso()),
        )

    def clear(self, game_id: int, player_id: int) -> None:
        self._conn.execute(
            "DELETE FROM confirmations WHERE game_id = ? AND player_id = ?;",
            (game_id, player_id),
        )

    def reset_game(self, game_id: int) -> None:
        self._conn.execute("DELETE FROM confirmations WHERE game_id = ?;", (game_id,))

    def list_by_status(self, game_id: int, status: str) -> list[int]:
        rows = self._conn.execute(
            "SELECT player_id FROM confirmations WHERE game_id = ? AND status = ? ORDER BY id ASC;",
            (game_id, status),
        ).fetchall()
        return [int(r["player_id"]) for r in rows]

    def count_by_status(self, game_id: int, status: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM confirmations WHERE game_id = ? AND status = ?;",
            (game_id, status),
        ).fetchone()
        return int(row["c"]) if row else 0

