from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape
from urllib.parse import quote_plus

from utils.time import weekday_label_pt


@dataclass(frozen=True)
class RenderInput:
    game_name: str
    game_day: str
    game_time: str
    game_location: str
    game_address: str
    game_date: date
    status: str  # open|closed
    max_players: int
    confirmed: list[str]
    not_going: list[str]
    waiting: list[str]


def _bulleted(names: list[str]) -> str:
    return "\n".join([f"• {n}" for n in names])


def _weekday_short_pt(game_day: str) -> str:
    # Mantém curto e clean para a linha compacta.
    full = weekday_label_pt(game_day)
    return (
        full.replace("-feira", "")
        .replace("Sábado", "Sáb")
        .replace("Domingo", "Dom")
    )


def _vacancy_bar(confirmed: int, max_players: int, width: int = 15) -> str:
    if max_players <= 0:
        max_players = 1
    # Barra com largura fixa; aproxima para o efeito visual.
    filled = int(round((confirmed / max_players) * width))
    filled = max(0, min(width, filled))
    return ("█" * filled) + ("░" * (width - filled))


def render_game_message(data: RenderInput) -> str:
    date_str = data.game_date.strftime("%d/%m")
    location = escape(data.game_location or "")
    game_name = escape(data.game_name or "")
    q = quote_plus(data.game_address or data.game_location or data.game_name)
    maps_url = f"https://www.google.com/maps/search/?api=1&query={q}"

    confirmed_count = len(data.confirmed)
    bar = _vacancy_bar(confirmed_count, data.max_players, width=15)

    header = f"⚽ {game_name}\n\n"
    header += f"📅 {_weekday_short_pt(data.game_day)} ({date_str}) • {escape(data.game_time)}\n"
    header += f'📍 <a href="{maps_url}">{location}</a>\n\n'

    vacancies_block = "👥 Vagas:\n"
    vacancies_block += f"{bar} {confirmed_count}/{data.max_players}\n\n"

    confirmed_block = "✅ Confirmados\n"
    confirmed_block += ("• —" if confirmed_count == 0 else _bulleted(data.confirmed))

    if data.status == "closed":
        confirmed_block += "\n\n🔒 Lista encerrada."

    return header + vacancies_block + confirmed_block

