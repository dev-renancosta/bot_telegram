from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


WEEKDAY_MAP_EN = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

WEEKDAY_LABEL_PT = {
    0: "Segunda-feira",
    1: "Terça-feira",
    2: "Quarta-feira",
    3: "Quinta-feira",
    4: "Sexta-feira",
    5: "Sábado",
    6: "Domingo",
}


def parse_hhmm(value: str) -> time:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Horário inválido (HH:MM): {value}")
    h, m = int(parts[0]), int(parts[1])
    return time(hour=h, minute=m)


def next_weekday(from_date: date, weekday: int) -> date:
    delta = (weekday - from_date.weekday()) % 7
    return from_date + timedelta(days=delta)


def compute_game_date(game_day: str, tz: ZoneInfo, now: datetime | None = None) -> date:
    if now is None:
        now = datetime.now(tz=tz)
    wd = WEEKDAY_MAP_EN.get(game_day.strip().lower())
    if wd is None:
        raise ValueError(f"GAME_DAY inválido: {game_day}")
    return next_weekday(now.date(), wd)


def weekday_label_pt(game_day: str) -> str:
    wd = WEEKDAY_MAP_EN.get(game_day.strip().lower())
    if wd is None:
        return game_day
    return WEEKDAY_LABEL_PT.get(wd, game_day)


def combine_date_time(d: date, hhmm: str, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, parse_hhmm(hhmm)).replace(tzinfo=tz)


def is_business_day(d: date) -> bool:
    return d.weekday() < 5


def nth_business_day(year: int, month: int, n: int) -> date:
    if n <= 0:
        raise ValueError("n deve ser >= 1")
    d = date(year, month, 1)
    count = 0
    while True:
        if is_business_day(d):
            count += 1
            if count == n:
                return d
        d += timedelta(days=1)
