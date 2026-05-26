"""CLI estrattore email + classificatore documenti (Karisma).

Comandi:
  download  scarica i PDF dalle email del fornitore (+ manifest metadati)
  classify  invia i PDF all'API d74-service e scrive l'Excel
  all       download seguito da classify
"""
from __future__ import annotations

import argparse
import logging
import os
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

import gmail_fetch
from cache import ResultCache, file_sha256
from d74_client import D74Client
from excel_writer import write_excel
from manifest import append_manifest, load_manifest

OUTPUT_DIR = Path("output")
PDF_DIR = OUTPUT_DIR / "pdf"
MANIFEST_PATH = OUTPUT_DIR / "manifest.jsonl"
CACHE_PATH = OUTPUT_DIR / "cache.json"
MAX_PDF_BYTES = 20 * 1024 * 1024
DEFAULT_BASE_URL = "https://services.d74.cloud"


def get_logger() -> logging.Logger:
    logger = logging.getLogger("karisma")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Variabile {name} mancante nel file .env")
    return value


def cmd_download(args, logger) -> None:
    from email.utils import parsedate_to_datetime

    from_date = date.fromisoformat(args.from_date)
    to_date = date.fromisoformat(args.to_date)
    logger.info("Download email dal %s al %s…", from_date, to_date)

    messages = gmail_fetch.fetch_emails(
        _require_env("GMAIL_USER"),
        _require_env("GMAIL_CLIENT_ID"),
        _require_env("GMAIL_CLIENT_SECRET"),
        _require_env("GMAIL_REFRESH_TOKEN"),
        from_date, to_date, gmail_fetch.get_search_query(), logger,
    )

    total = 0
    for msg in messages:
        try:
            mail_date = parsedate_to_datetime(msg.get("Date", "")).isoformat()
        except Exception:
            mail_date = ""
        for pdf_path in gmail_fetch.download_pdfs(msg, PDF_DIR, logger):
            append_manifest(str(MANIFEST_PATH), {
                "file": pdf_path.name,
                "data_email": mail_date,
                "mittente": msg.get("From", ""),
                "oggetto": msg.get("Subject", ""),
            })
            total += 1
    logger.info("PDF scaricati: %d (manifest: %s)", total, MANIFEST_PATH)


def cmd_classify(args, logger) -> None:
    base_url = os.getenv("D74_BASE_URL", DEFAULT_BASE_URL)
    client = D74Client(
        base_url,
        _require_env("APP_NAME"),
        _require_env("APP_PASSWORD"),
        _require_env("SUPPLIER_SLUG"),
    )
    manifest = load_manifest(str(MANIFEST_PATH))
    cache = ResultCache(str(CACHE_PATH))

    records: list[dict] = []
    pdfs = sorted(PDF_DIR.rglob("*.pdf"))
    logger.info("PDF da classificare: %d", len(pdfs))

    for pdf in pdfs:
        if pdf.stat().st_size > MAX_PDF_BYTES:
            logger.warning("PDF oversize, saltato: %s", pdf.name)
            continue
        file_hash = file_sha256(str(pdf))
        record = cache.get(file_hash)
        if record is None:
            logger.info("Classifico: %s", pdf.name)
            record = client.classify(str(pdf))
            record["file_hash"] = file_hash
            cache.put(file_hash, record)
            cache.save()
        else:
            logger.info("Da cache: %s", pdf.name)

        meta = manifest.get(pdf.name, {})
        records.append({
            **record,
            "data_email": meta.get("data_email", ""),
            "mittente": meta.get("mittente", ""),
            "oggetto": meta.get("oggetto", ""),
        })

    run_date = date.today().strftime("%Y%m%d")
    excel_path = OUTPUT_DIR / f"risultati_{run_date}.xlsx"
    write_excel(records, str(excel_path))
    logger.info("Excel scritto: %s (%d righe)", excel_path, len(records))


def cmd_all(args, logger) -> None:
    cmd_download(args, logger)
    cmd_classify(args, logger)


def parse_args() -> argparse.Namespace:
    to_default = date.today()
    from_default = to_default - timedelta(days=30)
    parser = argparse.ArgumentParser(description="Estrattore email + classificatore documenti.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("download", "classify", "all"):
        sp = sub.add_parser(name)
        sp.add_argument("--from", dest="from_date", default=from_default.isoformat(), metavar="YYYY-MM-DD")
        sp.add_argument("--to", dest="to_date", default=to_default.isoformat(), metavar="YYYY-MM-DD")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    logger = get_logger()
    args = parse_args()
    {"download": cmd_download, "classify": cmd_classify, "all": cmd_all}[args.command](args, logger)


if __name__ == "__main__":
    main()
