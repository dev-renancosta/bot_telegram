from __future__ import annotations


def message_link(chat_id: int, message_id: int) -> str | None:
    """
    Para supergrupos/canais privados, links são do tipo:
    https://t.me/c/<internal_id>/<message_id>
    onde internal_id = chat_id sem o prefixo -100.
    """
    s = str(chat_id)
    if not s.startswith("-100"):
        return None
    internal = s[4:]
    return f"https://t.me/c/{internal}/{message_id}"

