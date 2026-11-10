"""Ortak vektörler: Python eşleştirici JS ile aynı sonuçları vermeli."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zibilyon_veri.normalize import eslestir, normalize, mesafe, kokler, tolerans

V = json.loads((Path(__file__).resolve().parents[3] / "ortak/normalize_vektorleri.json").read_text())

def test_normalize_vektorleri():
    for g, b in V["normalize"]:
        assert normalize(g) == b, g

def test_eslesme_vektorleri():
    for s in V["eslesme"]:
        r = eslestir(s["girdi"], V["tablolar"][s["tablo"]])
        assert {k: r[k] for k in ("tur", "i", "adim") if k in r} == s["beklenen"], (s["tablo"], s["girdi"])

def test_tekrar():
    for s in V["tekrar"]:
        onceki, sonuc = [], []
        for g in s["girdiler"]:
            sonuc.append(eslestir(g, V["tablolar"][s["tablo"]], onceki)["tur"]); onceki.append(normalize(g))
        assert sonuc == s["beklenen"]

def test_mesafe_ve_tolerans():
    assert mesafe("elma", "elam") == 1  # yer değiştirme tek hata
    assert mesafe("kiraz", "kirz") == 1
    assert [tolerans(n) for n in (3, 4, 5, 7, 8, 12)] == [0, 0, 1, 1, 2, 2]

def test_unsuz_yumusamasi():
    assert "ağaç" in kokler("ağacı") and "kitap" in kokler("kitabı") and "renk" in kokler("rengi")
