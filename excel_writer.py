from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

FIXED_COLUMNS = [
    "file", "data_email", "mittente", "oggetto", "status", "fornitore_ok",
    "tipo_documento", "tipo_label", "confidenza_classif", "errore",
]

# Ordine preferito delle colonne dei campi estratti. I campi qui elencati
# compaiono in quest'ordine (commissioni e provvigioni adiacenti); gli altri,
# non previsti, vengono aggiunti in fondo in ordine alfabetico.
PREFERRED_FIELD_ORDER = [
    "data_documento", "numero_documento", "totale", "commissioni", "provvigioni",
]


def collect_field_columns(records: list[dict]) -> list[str]:
    """Colonne dei campi estratti, ordinate secondo PREFERRED_FIELD_ORDER e poi
    per chiavi non previste in ordine alfabetico."""
    keys: set[str] = set()
    for rec in records:
        keys.update((rec.get("campi") or {}).keys())
    preferred = [k for k in PREFERRED_FIELD_ORDER if k in keys]
    others = sorted(k for k in keys if k not in PREFERRED_FIELD_ORDER)
    return preferred + others


def _timestamped_path(path: str) -> str:
    """Inserisce l'orario (HHMMSS) prima dell'estensione: ris.xlsx → ris_143700.xlsx."""
    p = Path(path)
    return str(p.with_name(f"{p.stem}_{datetime.now().strftime('%H%M%S')}{p.suffix}"))


def _save_workbook(wb, path: str) -> str:
    """Salva il workbook; se il file è bloccato (es. aperto in Excel) ripiega su
    un nome alternativo con l'orario. Ritorna il path effettivamente scritto."""
    try:
        wb.save(path)
        return path
    except PermissionError:
        alt = _timestamped_path(path)
        wb.save(alt)
        return alt


def _is_pertinente(rec: dict) -> bool:
    """True se il documento appartiene al fornitore (fornitore_ok == True).
    I non pertinenti (False) e gli errori (None) finiscono nel foglio 'Scartati'."""
    return rec.get("fornitore_ok") is True


def _fill_sheet(ws, title: str, records: list[dict]) -> None:
    ws.title = title
    field_cols = collect_field_columns(records)
    ws.append(FIXED_COLUMNS + field_cols)
    for rec in records:
        campi = rec.get("campi") or {}
        values = [rec.get(col) for col in FIXED_COLUMNS] + [campi.get(col) for col in field_cols]
        ws.append(["" if v is None else v for v in values])


def write_excel(records: list[dict], path: str) -> str:
    """Scrive l'Excel su due fogli — 'Karisma' (documenti del fornitore) e
    'Scartati' (non pertinenti o in errore) — e ritorna il path effettivamente
    scritto (può differire da `path` se l'originale era bloccato)."""
    karisma = [r for r in records if _is_pertinente(r)]
    scartati = [r for r in records if not _is_pertinente(r)]

    wb = Workbook()
    _fill_sheet(wb.active, "Karisma", karisma)
    _fill_sheet(wb.create_sheet("Scartati"), "Scartati", scartati)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return _save_workbook(wb, path)
