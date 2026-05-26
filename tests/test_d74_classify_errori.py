from unittest.mock import MagicMock
from d74_client import D74Client

def _resp(status, json_data):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = json_data
    m.raise_for_status.return_value = None
    return m

SUCCESS = {
    "success": True,
    "data": {
        "supplier_verification": {"belongs_to_supplier": True},
        "classification": {"document_type": "fattura", "document_type_label": "Fattura", "confidence": 0.9},
        "extracted_fields": {},
    },
}

def _pdf(tmp_path):
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    return str(p)

def test_401_poi_relogin_poi_successo(tmp_path):
    session = MagicMock()
    # 1) classify→401, 2) login→token, 3) classify→200
    session.post.side_effect = [
        _resp(401, {"message": "Unauthenticated."}),
        _resp(200, {"token": "tok-nuovo"}),
        _resp(200, SUCCESS),
    ]
    client = D74Client("https://x", "app", "pwd", "slug", session=session)
    client.token = "tok-vecchio"

    rec = client.classify(_pdf(tmp_path))

    assert rec["status"] == "classificato"
    assert client.token == "tok-nuovo"

def test_401_due_volte_da_errore_auth(tmp_path):
    session = MagicMock()
    session.post.side_effect = [
        _resp(401, {"message": "Unauthenticated."}),
        _resp(200, {"token": "tok-nuovo"}),
        _resp(401, {"message": "Unauthenticated."}),
    ]
    client = D74Client("https://x", "app", "pwd", "slug", session=session)
    client.token = "tok"

    rec = client.classify(_pdf(tmp_path))

    assert rec["status"] == "errore"
    assert rec["errore"].startswith("AUTH")

def test_422_non_ritenta_e_logga_codice(tmp_path):
    session = MagicMock()
    session.post.return_value = _resp(422, {"success": False, "error": {"code": "FILE_TOO_LARGE", "message": "troppo grande"}})
    client = D74Client("https://x", "app", "pwd", "slug", session=session)
    client.token = "tok"

    rec = client.classify(_pdf(tmp_path))

    assert rec["status"] == "errore"
    assert rec["errore"] == "FILE_TOO_LARGE: troppo grande"
    assert session.post.call_count == 1  # nessun retry

def test_5xx_backoff_poi_successo(tmp_path):
    calls = []
    session = MagicMock()
    session.post.side_effect = [
        _resp(500, {"success": False, "error": {"code": "INTERNAL_ERROR", "message": "boom"}}),
        _resp(200, SUCCESS),
    ]
    client = D74Client("https://x", "app", "pwd", "slug", session=session,
                       sleep=lambda s: calls.append(s))
    client.token = "tok"

    rec = client.classify(_pdf(tmp_path))

    assert rec["status"] == "classificato"
    assert calls == [2]  # un solo backoff da 2s

def test_5xx_esaurisce_i_retry(tmp_path):
    session = MagicMock()
    session.post.side_effect = [
        _resp(500, {"success": False, "error": {"code": "INTERNAL_ERROR", "message": "boom"}})
        for _ in range(4)
    ]
    client = D74Client("https://x", "app", "pwd", "slug", session=session,
                       sleep=lambda s: None)
    client.token = "tok"

    rec = client.classify(_pdf(tmp_path))

    assert rec["status"] == "errore"
    assert rec["errore"].startswith("INTERNAL_ERROR")
    assert session.post.call_count == 4  # 1 + 3 retry
