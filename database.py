from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime


logger = logging.getLogger(__name__)


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS games (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id INTEGER NOT NULL,
  message_id INTEGER,
  created_at TEXT NOT NULL,
  game_date TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('open','closed')),
  max_players INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_games_chat_status ON games(chat_id, status);

CREATE TABLE IF NOT EXISTS players (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  telegram_id INTEGER NOT NULL UNIQUE,
  username TEXT,
  first_name TEXT,
  created_at TEXT NOT NULL
);

-- Membros rastreáveis (vínculo do usuário com o grupo)
CREATE TABLE IF NOT EXISTS memberships (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id INTEGER NOT NULL,
  group_id INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('ACTIVE','LEFT')),
  joined_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(player_id, group_id),
  FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_memberships_group_status ON memberships(group_id, status);

CREATE TABLE IF NOT EXISTS confirmations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  game_id INTEGER NOT NULL,
  player_id INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('vou','nao_vou','espera')),
  created_at TEXT NOT NULL,
  UNIQUE(game_id, player_id),
  FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE,
  FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_confirmations_game_status ON confirmations(game_id, status);

CREATE TABLE IF NOT EXISTS admins (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  telegram_id INTEGER NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);

-- Mensalidades (financeiro)
CREATE TABLE IF NOT EXISTS monthly_fees (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_id INTEGER NOT NULL,
  year INTEGER NOT NULL,
  month INTEGER NOT NULL CHECK(month BETWEEN 1 AND 12),
  amount_cents INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('PENDENTE','ATRASADO','AGUARDANDO_VALIDACAO','PAGO','RECUSADO')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  approved_by_telegram_id INTEGER,
  approved_at TEXT,
  UNIQUE(player_id, year, month),
  FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_monthly_fees_player_status ON monthly_fees(player_id, status);

CREATE TABLE IF NOT EXISTS payment_submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  monthly_fee_id INTEGER NOT NULL,
  telegram_user_id INTEGER NOT NULL,
  file_id TEXT NOT NULL,
  file_unique_id TEXT,
  file_type TEXT NOT NULL CHECK(file_type IN ('photo','document')),
  original_file_name TEXT,
  mime_type TEXT,
  message_id INTEGER,
  chat_id INTEGER,
  status TEXT NOT NULL CHECK(status IN ('AGUARDANDO_VALIDACAO','APROVADO','RECUSADO')),
  created_at TEXT NOT NULL,
  reviewed_at TEXT,
  reviewed_by_telegram_id INTEGER,
  admin_note TEXT,
  FOREIGN KEY(monthly_fee_id) REFERENCES monthly_fees(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_payment_submissions_fee_status ON payment_submissions(monthly_fee_id, status);

-- Logs de cobrança (anti-spam/anti-duplicidade)
CREATE TABLE IF NOT EXISTS cobranca_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  telegram_user_id INTEGER NOT NULL,
  reference TEXT NOT NULL, -- ex: 2026-05
  kind TEXT NOT NULL CHECK(kind IN ('AUTO_AVAILABLE','AUTO_DUE','MANUAL')),
  created_at TEXT NOT NULL,
  UNIQUE(telegram_user_id, reference, kind)
);

CREATE INDEX IF NOT EXISTS idx_cobranca_logs_ref_kind ON cobranca_logs(reference, kind);
"""


@dataclass(frozen=True)
class Database:
    path: str

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)


@contextmanager
def transaction(conn: sqlite3.Connection):
    try:
        conn.execute("BEGIN;")
        yield
        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise


def utcnow_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

