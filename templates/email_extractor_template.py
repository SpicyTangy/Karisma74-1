"""
Template estrazione email + allegati PDF da Gmail (IMAP + OAuth2).

File autoportante: non dipende da utils/ del progetto MSC, così puoi copiarlo
da solo. Riusa la connessione IMAP/OAuth2 (XOAUTH2) — la parte più rognosa —
e lascia personalizzabile SOLO la query di ricerca.

──────────────────────────────────────────────────────────────────────────
👉 PERSONALIZZA SOLO QUESTO: la costante SEARCH_QUERY qui sotto.
   Tutto il resto (auth, fetch, download, Excel) funziona già.
──────────────────────────────────────────────────────────────────────────

Setup (account già esistente — riusi gli stessi valori OAuth2):
  1. copia .env.example in .env e incolla GMAIL_USER / CLIENT_ID /
     CLIENT_SECRET / REFRESH_TOKEN
  2. pip install -r requirements.txt
  3. python email_extractor_template.py --from 2026-01-01 --to 2026-05-31
"""

from __future__ import annotations

import argparse
import email as email_lib
import imaplib
import logging
import os
import re
from datetime import date, timedelta
from email.message import Message
from email.utils import parsedate_to_datetime
from pathlib import Path

from dotenv import load_dotenv

# ───────────────────────────────────────────────────────────────────────────
# 👉 PERSONALIZZA QUI — sintassi ricerca Gmail (operatori from:/subject:/has:)
#    Esempio MSC: 'from:msc-booking.no-reply has:attachment'
#    Le date (after:/before:) vengono aggiunte in automatico dal codice.
# ───────────────────────────────────────────────────────────────────────────
SEARCH_QUERY = "from:bookingrdv has:attachment"

# Mesi in italiano per la gerarchia di cartelle (output/pdf/2026/05-Maggio/…)
_MESI_IT = {
    1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
    5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
    9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre",
}

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


def get_logger(name: str = "email_extractor") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


# ───────────────────────────────────────────────────────────────────────────
# OAuth2 → IMAP (XOAUTH2)
# ───────────────────────────────────────────────────────────────────────────

def _get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
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
    # imaplib.authenticate() fa da solo il base64 — restituire bytes grezzi.
    return f"user={user}\x01auth=Bearer {access_token}\x01\x01".encode()


def fetch_emails(
    user: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    from_date: date,
    to_date: date,
    logger: logging.Logger,
) -> list[Message]:
    """Ritorna le email che matchano SEARCH_QUERY nel range [from_date, to_date]."""
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
        # [Gmail]/Tutti i messaggi include anche le email archiviate fuori da INBOX.
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

        # X-GM-RAW: usa la sintassi di ricerca Gmail (filtra lato server, veloce).
        after = from_date.strftime("%Y/%m/%d")
        before = (to_date + timedelta(days=1)).strftime("%Y/%m/%d")
        gm_query = f"{SEARCH_QUERY} after:{after} before:{before}"
        try:
            _, data = imap.search(None, f'X-GM-RAW "{gm_query}"')
            logger.info("Ricerca Gmail: %s", gm_query)
        except imaplib.IMAP4.error:
            # Server non-Gmail → fallback IMAP standard (solo per data).
            since = from_date.strftime("%d-%b-%Y")
            bef = (to_date + timedelta(days=1)).strftime("%d-%b-%Y")
            _, data = imap.search(None, f"SINCE {since} BEFORE {bef}")
            logger.info("Ricerca IMAP standard (fallback solo data)")

        uids = data[0].split() if data and data[0] else []
        logger.info("Email trovate: %d", len(uids))
        if not uids:
            return []

        # Download completo in batch.
        BATCH = 50
        messages: list[Message] = []
        for i in range(0, len(uids), BATCH):
            batch = uids[i:i + BATCH]
            _, responses = imap.fetch(b",".join(batch), "(RFC822)")
            for item in responses:
                if not isinstance(item, tuple) or len(item) < 2:
                    continue
                try:
                    messages.append(email_lib.message_from_bytes(item[1]))
                except Exception as exc:
                    logger.warning("Mail non parsabile: %s — saltata", exc)
            logger.info("Download: %d/%d", min(i + BATCH, len(uids)), len(uids))
    finally:
        imap.logout()

    def _date_key(m: Message) -> float:
        try:
            return parsedate_to_datetime(m.get("Date", "")).timestamp()
        except Exception:
            return 0.0

    messages.sort(key=_date_key)
    return messages


# ───────────────────────────────────────────────────────────────────────────
# Download allegati PDF
# ───────────────────────────────────────────────────────────────────────────

MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB
_INVALID = re.compile(r'[<>:"/\\|?*]')


def download_pdfs(msg: Message, pdf_dir: Path, logger: logging.Logger) -> list[Path]:
    """Salva gli allegati PDF in pdf_dir/<anno>/<mese>/ e ritorna i path scritti."""
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

        safe = _INVALID.sub("_", Path(filename).name)
        pdf_path = dest_dir / f"{date_prefix}_{safe}"
        pdf_path.write_bytes(payload)
        saved.append(pdf_path)
        logger.info("PDF salvato: %s", pdf_path)
    return saved


# ───────────────────────────────────────────────────────────────────────────
# Excel
# ───────────────────────────────────────────────────────────────────────────

def write_excel(rows: list[dict], excel_path: Path) -> None:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Email"
    headers = ["data_email", "mittente", "oggetto", "pdf_file"]
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])
    excel_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(excel_path)


# ───────────────────────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    to_default = date.today()
    from_default = to_default - timedelta(days=30)
    p = argparse.ArgumentParser(description="Estrae email + allegati PDF da Gmail.")
    p.add_argument("--from", dest="from_date", default=from_default.isoformat(), metavar="YYYY-MM-DD")
    p.add_argument("--to", dest="to_date", default=to_default.isoformat(), metavar="YYYY-MM-DD")
    return p.parse_args()


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Variabile {name} mancante nel file .env")
    return value


def main() -> None:
    load_dotenv()
    args = parse_args()
    from_date = date.fromisoformat(args.from_date)
    to_date = date.fromisoformat(args.to_date)

    logger = get_logger()
    run_date = date.today().strftime("%Y%m%d")
    output_dir = Path("output")
    pdf_dir = output_dir / "pdf"
    excel_path = output_dir / f"email_{run_date}.xlsx"

    logger.info("Fetch email dal %s al %s…", from_date, to_date)
    messages = fetch_emails(
        _require_env("GMAIL_USER"),
        _require_env("GMAIL_CLIENT_ID"),
        _require_env("GMAIL_CLIENT_SECRET"),
        _require_env("GMAIL_REFRESH_TOKEN"),
        from_date, to_date, logger,
    )

    rows: list[dict] = []
    for msg in messages:
        try:
            mail_date = parsedate_to_datetime(msg.get("Date", "")).isoformat()
        except Exception:
            mail_date = ""
        for pdf_path in download_pdfs(msg, pdf_dir, logger):
            rows.append({
                "data_email": mail_date,
                "mittente": msg.get("From", ""),
                "oggetto": msg.get("Subject", ""),
                "pdf_file": pdf_path.name,
            })

    write_excel(rows, excel_path)
    logger.info("Excel scritto: %s (%d righe)", excel_path, len(rows))


if __name__ == "__main__":
    main()
