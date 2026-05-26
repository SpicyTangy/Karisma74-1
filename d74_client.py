from __future__ import annotations

LOW_CONFIDENCE_THRESHOLD = 0.7


def derive_status(data: dict) -> str:
    """Mappa il `data` di una risposta 200 in uno stato (MD §5.3).

    Ritorna: classificato | non_pertinente | tipo_sconosciuto | bassa_confidenza.
    """
    sv = data.get("supplier_verification") or {}
    if not sv.get("belongs_to_supplier"):
        return "non_pertinente"
    cls = data.get("classification") or {}
    dtype = cls.get("document_type")
    if dtype is None or dtype == "non_classificabile":
        return "tipo_sconosciuto"
    conf = cls.get("confidence")
    if conf is not None and conf < LOW_CONFIDENCE_THRESHOLD:
        return "bassa_confidenza"
    return "classificato"
