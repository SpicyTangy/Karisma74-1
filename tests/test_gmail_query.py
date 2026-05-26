from datetime import date
from gmail_fetch import build_gmail_query

def test_build_gmail_query_aggiunge_after_e_before_inclusivo():
    # before è esclusivo lato Gmail → il codice somma 1 giorno a to_date
    q = build_gmail_query("from:fornitore has:attachment", date(2026, 1, 1), date(2026, 5, 31))
    assert q == "from:fornitore has:attachment after:2026/01/01 before:2026/06/01"
