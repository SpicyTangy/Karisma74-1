from __future__ import annotations

import email as email_lib
import imaplib
import logging
import os
import re
from datetime import date, timedelta
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB
_INVALID = re.compile(r'[<>:"/\\|?*]')

_MESI_IT = {
    1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
    5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
    9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre",
}

# Query Gmail del fornitore. Override con env GMAIL_SEARCH_QUERY se presente.
DEFAULT_SEARCH_QUERY = "has:attachment"


def get_search_query() -> str:
    return os.getenv("GMAIL_SEARCH_QUERY", DEFAULT_SEARCH_QUERY)


def _get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://mail.google.com/"],
    )
    creds.refresh(Request())
    return creds.token


def _build_xoauth2_string(user: str, access_token: str) -> bytes:
    return f"user={user}\x01auth=Bearer {access_token}\x01\x01".encode()


def build_gmail_query(search_query: str, from_date: date, to_date: date) -> str:
    """Aggiunge gli operatori after:/before: alla query Gmail.

    before: è esclusivo lato Gmail, quindi sommiamo 1 giorno a to_date per
    rendere il range [from_date, to_date] inclusivo su entrambi gli estremi.
    """
    after = from_date.strftime("%Y/%m/%d")
    before = (to_date + timedelta(days=1)).strftime("%Y/%m/%d")
    return f"{search_query} after:{after} before:{before}"


def fetch_emails(user, client_id, client_secret, refresh_token,
                 from_date, to_date, search_query, logger) -> list[Message]:
    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    except OSError as exc:
        logger.error("Connessione IMAP fallita: %s", exc)
        raise SystemExit(1)

    try:
        access_token = _get_access_token(client_id, client_secret, refresh_token)
        xoauth2 = _build_xoauth2_string(user, access_token)
        imap.authenticate("XOAUTH2", lambda _: xoauth2)
    except imaplib.IMAP4.error as exc:
        logger.error("Autenticazione IMAP fallita: %s", exc)
        raise SystemExit(1)
    except Exception as exc:
        logger.error("Errore credenziali OAuth2: %s", exc)
        raise SystemExit(1)

    try:
        for folder in ('"[Gmail]/Tutti i messaggi"', "INBOX"):
            try:
                status, _ = imap.select(folder, readonly=True)
            except imaplib.IMAP4.error:
                status = "NO"
            if status == "OK":
                logger.info("Cartella selezionata: %s", folder)
                break
        else:
            logger.error("Impossibile selezionare una cartella IMAP valida")
            raise SystemExit(1)

        gm_query = build_gmail_query(search_query, from_date, to_date)
        try:
            _, data = imap.search(None, f'X-GM-RAW "{gm_query}"')
            logger.info("Ricerca Gmail: %s", gm_query)
        except imaplib.IMAP4.error:
            since = from_date.strftime("%d-%b-%Y")
            bef = (to_date + timedelta(days=1)).strftime("%d-%b-%Y")
            _, data = imap.search(None, f"SINCE {since} BEFORE {bef}")
            logger.info("Ricerca IMAP standard (fallback solo data)")

        uids = data[0].split() if data and data[0] else []
        logger.info("Email trovate: %d", len(uids))
        if not uids:
            return []

        batch_size = 50
        messages: list[Message] = []
        for i in range(0, len(uids), batch_size):
            batch = uids[i:i + batch_size]
            _, responses = imap.fetch(b",".join(batch), "(RFC822)")
            for item in responses:
                if not isinstance(item, tuple) or len(item) < 2:
                    continue
                try:
                    messages.append(email_lib.message_from_bytes(item[1]))
                except Exception as exc:
                    logger.warning("Mail non parsabile: %s — saltata", exc)
            logger.info("Download: %d/%d", min(i + batch_size, len(uids)), len(uids))
    finally:
        imap.logout()

    def _date_key(m: Message) -> float:
        try:
            return parsedate_to_datetime(m.get("Date", "")).timestamp()
        except Exception:
            return 0.0

    messages.sort(key=_date_key)
    return messages


def _safe_filename(filename: str) -> str:
    """Rende un nome file sicuro per il filesystem.

    Sostituisce i caratteri di controllo (inclusi i ritorni a capo che a volte
    finiscono nel nome per via degli header MIME ripiegati su più righe),
    collassa gli spazi, scarta eventuali componenti di percorso e rimpiazza i
    caratteri non ammessi da Windows. Ritorna 'allegato.pdf' se resta vuoto.
    """
    name = re.sub(r"[\x00-\x1f]+", " ", filename)  # \r \n \t … → spazio
    name = re.sub(r"\s+", " ", name).strip()        # collassa spazi multipli
    name = Path(name).name                           # scarta parti di percorso
    name = _INVALID.sub("_", name)
    name = name.strip(" .")                          # niente spazi/punti ai bordi
    return name or "allegato.pdf"


def download_pdfs(msg: Message, pdf_dir: Path, logger) -> list[Path]:
    try:
        dt = parsedate_to_datetime(msg.get("Date", ""))
        year, month = str(dt.year), f"{dt.month:02d}-{_MESI_IT[dt.month]}"
        date_prefix = dt.strftime("%Y-%m-%d")
    except Exception:
        year, month, date_prefix = "sconosciuto", "00-Sconosciuto", "0000-00-00"

    dest_dir = pdf_dir / year / month
    dest_dir.mkdir(parents=True, exist_ok=True)

    saved: list[Path] = []
    for part in msg.walk():
        ct = part.get_content_type()
        filename = part.get_filename() or ""
        is_pdf = ct == "application/pdf" or (
            ct == "application/octet-stream" and filename.lower().endswith(".pdf")
        )
        if not is_pdf or not filename:
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        if len(payload) > MAX_PDF_BYTES:
            logger.warning("PDF oversize (%d MB): %s — saltato", len(payload) // (1024 * 1024), filename)
            continue

        safe = _safe_filename(filename)
        pdf_path = dest_dir / f"{date_prefix}_{safe}"
        pdf_path.write_bytes(payload)
        saved.append(pdf_path)
        logger.info("PDF salvato: %s", pdf_path)
    return saved
