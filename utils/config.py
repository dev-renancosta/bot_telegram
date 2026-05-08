from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime

from dotenv import dotenv_values, load_dotenv


@dataclass(frozen=True)
class Config:
    bot_token: str
    group_id: int
    group_invite_link: str | None
    db_path: str
    tz: ZoneInfo
    max_players: int
    game_name: str
    game_day: str
    game_time: str
    game_location: str
    game_address: str
    admin_ids: tuple[int, ...]
    finance_text: str
    finance_admin_id: int | None
    finance_amount_cents: int
    finance_pix_copy_paste: str
    finance_start_year: int
    finance_start_month: int


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name}")
    return value.strip()


def _parse_int(name: str, default: int | None = None) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        if default is None:
            raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name}")
        return default
    try:
        return int(raw.strip())
    except ValueError as e:
        raise RuntimeError(f"Variável {name} inválida (esperado inteiro): {raw}") from e


def _parse_admin_ids(raw: str | None) -> tuple[int, ...]:
    if raw is None or raw.strip() == "":
        return tuple()
    ids: list[int] = []
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        try:
            ids.append(int(p))
        except ValueError as e:
            raise RuntimeError(f"ADMIN_IDS inválido (esperado números separados por vírgula): {raw}") from e
    return tuple(dict.fromkeys(ids))


def load_config() -> Config:
    # No Windows, rely menos no "auto-discovery" e aponte para o .env do projeto.
    project_root = Path(__file__).resolve().parents[1]
    env_path = project_root / ".env"

    # Tentativa 1: loader padrão (rápido)
    load_dotenv(dotenv_path=env_path, override=False)

    # Tentativa 2 (fallback): parse manual (lida melhor com alguns encodings/edições do Windows)
    if os.getenv("BOT_TOKEN") is None and env_path.exists():
        values = dotenv_values(env_path)
        for k, v in values.items():
            if v is None:
                continue
            os.environ.setdefault(k, v)

    tz_name = os.getenv("TZ", "America/Sao_Paulo").strip() or "America/Sao_Paulo"

    return Config(
        bot_token=_require_env("BOT_TOKEN"),
        group_id=_parse_int("GROUP_ID"),
        group_invite_link=(os.getenv("GROUP_INVITE_LINK", "").strip() or None),
        db_path=os.getenv("DB_PATH", "bot.db").strip() or "bot.db",
        tz=ZoneInfo(tz_name),
        max_players=_parse_int("MAX_PLAYERS", default=15),
        game_name=os.getenv("GAME_NAME", "ARENA DWD").strip() or "ARENA DWD",
        game_day=os.getenv("GAME_DAY", "Friday").strip() or "Friday",
        game_time=os.getenv("GAME_TIME", "18:00").strip() or "18:00",
        game_location=os.getenv("GAME_LOCATION", "Arena").strip() or "Arena",
        game_address=os.getenv("GAME_ADDRESS", "").strip(),
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS")),
        finance_text=os.getenv("FINANCE_TEXT", "").strip(),
        finance_admin_id=_parse_int("FINANCE_ADMIN_ID", default=0) or None,
        finance_amount_cents=_parse_int("FINANCE_AMOUNT_CENTS", default=5000),
        finance_pix_copy_paste=os.getenv("FINANCE_PIX_COPY_PASTE", "").strip(),
        finance_start_year=_parse_int("FINANCE_START_YEAR", default=datetime.now(tz=ZoneInfo(tz_name)).year),
        finance_start_month=_parse_int("FINANCE_START_MONTH", default=1),
    )
