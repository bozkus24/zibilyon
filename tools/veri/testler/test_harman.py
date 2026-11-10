"""Harmanlama ve katmanlama birim testleri (ağ gerektirmez)."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zibilyon_veri.hat import Hat
from zibilyon_veri.istatistik import spearman, yuzdelik

def test_yuzdelik_esitlik_ve_tek():
    assert yuzdelik({"a": 1, "b": 1, "c": 3}) == {"a": 0.25, "b": 0.25, "c": 1.0}
    assert yuzdelik({"x": 5}) == {"x": 0.5}

def test_spearman():
    assert round(spearman([1, 2, 3, 4], [10, 20, 30, 40]), 6) == 1.0
    assert round(spearman([1, 2, 3, 4], [4, 3, 2, 1]), 6) == -1.0
    assert spearman([1, 2], [1, 2]) is None

def _hat(tmp_path, adaylar, tip="cins"):
    h = Hat(tmp_path)
    s = {"id": "t-01", "metin": "Bir şey söyle", "tip": tip}
    h._yaz("cikti/t-01.sinyal.json", {"id": "t-01", "adaylar": adaylar, "llm_kosu": 3, "llm_uyari": []})
    return h, s

def _aday(n, **sig):
    return {"ad": n, "n": n, "kaynak": ["wikidata"], "qid": "Q1", "sinyal": sig, "takma": [], "es_sesli": False,
            "celiskili": False, "cok_kelimeli": False}

def test_eksik_sinyal_agirliklari_yeniden_olceklenir(tmp_path):
    ad = [_aday("a", frek=5, llm=10), _aday("b", llm=1), _aday("c", frek=1, llm=5)]
    h, s = _hat(tmp_path, ad)
    v = {a["n"]: a for a in h.harmanla(s)["adaylar"]}
    # b'nin yalnız llm'i var: bileşik = llm yüzdeliği
    assert v["b"]["bilesik"] == v["b"]["yuzdelik"]["llm"] == 0.0
    # a: frek 1.0 ve llm 1.0 -> 1.0
    assert v["a"]["bilesik"] == 1.0

def test_kota_ve_kisitlar(tmp_path):
    ad = [_aday(f"x{i:03d}", frek=i, llm=i) for i in range(100)]
    h, s = _hat(tmp_path, ad)
    v = h.harmanla(s)["adaylar"]
    say = {}
    for a in v: say[a["katman"]] = say.get(a["katman"], 0) + 1
    assert say["toprak"] <= 8 and all(say[t] >= 2 for t in ["toprak", "komur", "demir", "altin", "elmas"])
    en_iyi = max(v, key=lambda a: a["nihai"]); assert en_iyi["katman"] == "toprak"
    en_kotu = min(v, key=lambda a: a["nihai"]); assert en_kotu["katman"] == "elmas"
    assert "elmas_editor_onayi_gerekli" in en_kotu["uyarilar"]

def test_anket_varsa_esik_kullanilir(tmp_path):
    ps = [0.2, 0.05, 0.02, 0.005, 0.001]
    ad = [_aday(f"y{i}", frek=5 - i, llm=5 - i, anket=p) for i, p in enumerate(ps)]
    h, s = _hat(tmp_path, ad)
    v = {a["n"]: a["katman"] for a in h.harmanla(s)["adaylar"]}
    assert v == {"y0": "toprak", "y1": "komur", "y2": "demir", "y3": "altin", "y4": "elmas"}

def test_sabit_sira_siniri(tmp_path):
    ad = [_aday(f"z{i:03d}", frek=i, llm=i) for i in range(200)]
    h, s = _hat(tmp_path, ad)
    v = h.harmanla(s)
    say = {}
    for a in v["adaylar"]: say[a["katman"]] = say.get(a["katman"], 0) + 1
    assert v["katman_yontemi"] == "sabit_sira"
    assert say == {"toprak": 8, "komur": 15, "demir": 30, "altin": 60, "elmas": 87}

def test_kucuk_havuz_yuzdelik(tmp_path):
    ad = [_aday(f"k{i:02d}", frek=i, llm=i) for i in range(20)]
    h, s = _hat(tmp_path, ad)
    assert h.harmanla(s)["katman_yontemi"] == "kota"
