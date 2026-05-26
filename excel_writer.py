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


def write_excel(records: list[dict], path: str) -> str:
    """Scrive l'Excel e ritorna il path effettivamente scritto (può differire
    da `path` se l'originale era bloccato)."""
    field_cols = collect_field_columns(records)
    headers = FIXED_COLUMNS + field_cols

    wb = Workbook()
    ws = wb.active
    ws.title = "Risultati"
    ws.append(headers)

    for rec in records:
        campi = rec.get("campi") or {}
        values = [rec.get(col) for col in FIXED_COLUMNS] + [campi.get(col) for col in field_cols]
        ws.append(["" if v is None else v for v in values])

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return _save_workbook(wb, path)
