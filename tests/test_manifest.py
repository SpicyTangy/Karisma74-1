from manifest import append_manifest, load_manifest

def test_append_e_load_roundtrip(tmp_path):
    path = tmp_path / "manifest.jsonl"
    append_manifest(str(path), {"file": "a.pdf", "data_email": "2026-05-12", "mittente": "x@y.it", "oggetto": "Ciao"})
    append_manifest(str(path), {"file": "b.pdf", "data_email": "2026-05-13", "mittente": "z@y.it", "oggetto": "Altro"})

    loaded = load_manifest(str(path))

    assert set(loaded.keys()) == {"a.pdf", "b.pdf"}
    assert loaded["a.pdf"]["oggetto"] == "Ciao"

def test_load_manifest_inesistente_ritorna_vuoto(tmp_path):
    assert load_manifest(str(tmp_path / "manca.jsonl")) == {}
