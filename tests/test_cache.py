from cache import file_sha256, ResultCache

def test_file_sha256_deterministico(tmp_path):
    f = tmp_path / "x.pdf"
    f.write_bytes(b"contenuto")
    h1 = file_sha256(str(f))
    h2 = file_sha256(str(f))
    assert h1 == h2 and len(h1) == 64

def test_cache_put_get_save_reload(tmp_path):
    path = tmp_path / "cache.json"
    c = ResultCache(str(path))
    assert c.get("abc") is None
    c.put("abc", {"status": "classificato"})
    c.save()

    c2 = ResultCache(str(path))
    assert c2.get("abc") == {"status": "classificato"}
