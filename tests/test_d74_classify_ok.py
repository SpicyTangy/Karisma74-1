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
        "supplier_verification": {"belongs_to_supplier": True, "confidence": 0.95},
        "classification": {"document_type": "fattura", "document_type_label": "Fattura", "confidence": 0.92},
        "extracted_fields": {"numero": {"value": "ABC123", "confidence": 0.99}},
    },
}

def test_classify_costruisce_record_da_200(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    session = MagicMock()
    session.post.return_value = _resp(200, SUCCESS)
    client = D74Client("https://x", "app", "pwd", "slug", session=session)
    client.token = "tok"  # salta il login

    rec = client.classify(str(pdf))

    assert rec["file"] == "doc.pdf"
    assert rec["status"] == "classificato"
    assert rec["fornitore_ok"] is True
    assert rec["tipo_documento"] == "fattura"
    assert rec["tipo_label"] == "Fattura"
    assert rec["confidenza_classif"] == 0.92
    assert rec["campi"] == {"numero": "ABC123"}
    assert rec["errore"] is None
