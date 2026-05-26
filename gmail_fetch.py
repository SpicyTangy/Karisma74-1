from __future__ import annotations

from datetime import date, timedelta


def build_gmail_query(search_query: str, from_date: date, to_date: date) -> str:
    """Aggiunge gli operatori after:/before: alla query Gmail.

    before: è esclusivo lato Gmail, quindi sommiamo 1 giorno a to_date per
    rendere il range [from_date, to_date] inclusivo su entrambi gli estremi.
    """
    after = from_date.strftime("%Y/%m/%d")
    before = (to_date + timedelta(days=1)).strftime("%Y/%m/%d")
    return f"{search_query} after:{after} before:{before}"
