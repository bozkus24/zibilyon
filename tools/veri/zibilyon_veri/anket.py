"""Site dışı anket içe aktarımı ve ağırlık kalibrasyonu.

CSV biçimi (ham/anket/<soru-id>.csv, UTF-8, başlıklı):
    katilimci,cevap1,cevap2,cevap3
    k001,elma,muz,kiraz
Ağırlık: 1. cevap 1.0, 2. cevap 0.6, 3. cevap 0.4. p = cevabın ağırlık toplamı / tüm ağırlıklar.
Cevaplar sunucuyla aynı eşleştiriciden geçer (ek, katlama, yazım hatası). Eşleşmeyenler
"yeni_aday" olarak raporlanır; otomatik eklenmez.
"""
from __future__ import annotations

import csv
import itertools
import json

from .hat import AGIRLIK
from .istatistik import spearman
from .normalize import derle, eslestir, normalize

SIRA_AGIRLIK = [1.0, 0.6, 0.4]
EN_AZ_SORU = 30


def ice_aktar(h, s: dict) -> str:
    p = h.kok / "ham" / "anket" / f"{s['id']}.csv"
    if not p.exists():
        return f"{s['id']}: anket dosyası yok ({p.name})"
    veri = json.loads((h.kok / f"cikti/{s['id']}.adaylar.json").read_text())
    ad = veri["adaylar"]
    tablo = derle([{"ad": a["ad"], "takma": a.get("takma", []), "wd_takma": a.get("wd_takma", [])} for a in ad],
                  s.get("red_listesi", []), s.get("niteleyiciler"), s.get("ek_kaldir"))
    toplam, w, yeni, kisi = 0.0, {}, {}, 0
    for r in csv.DictReader(p.open(encoding="utf-8")):
        kisi += 1
        verilen = set()
        for i, alan in enumerate(["cevap1", "cevap2", "cevap3"]):
            x = (r.get(alan) or "").strip()
            if not x:
                continue
            toplam += SIRA_AGIRLIK[i]
            m = eslestir(x, tablo)
            if m["tur"] == "kabul" and m["i"] not in verilen:
                verilen.add(m["i"])
                n = ad[m["i"]]["n"]
                w[n] = w.get(n, 0.0) + SIRA_AGIRLIK[i]
            elif m["tur"] != "kabul":
                k = normalize(x)
                yeni[k] = yeni.get(k, 0) + 1
    p_ = {n: v / toplam for n, v in w.items()} if toplam else {}
    for a in ad:
        p_.setdefault(a["n"], 0.0)
    h._yaz(f"cikti/{s['id']}.anket.json", {"katilimci": kisi, "p": p_, "yeni_aday": dict(sorted(yeni.items(), key=lambda x: -x[1]))})
    return f"{s['id']}: {kisi} katılımcı, {len(w)} eşleşen cevap, {len(yeni)} listede olmayan"


def kalibre(h, sorular: list[dict]) -> str:
    """Anketli >= 30 soruda, anketle Spearman korelasyonunu en üst düzeye çıkaran ağırlıklar."""
    veri = []
    for s in sorular:
        if not (h.kok / f"cikti/{s['id']}.anket.json").exists():
            continue
        v = json.loads((h.kok / f"cikti/{s['id']}.json").read_text())
        veri.append((s, v))
    if len(veri) < EN_AZ_SORU:
        return f"Kalibrasyon yapılmadı: anketli soru {len(veri)}/{EN_AZ_SORU}. Varsayılan ağırlıklar korunur."
    izgara = [x / 20 for x in range(21)]
    sonuc = {}
    for tip in AGIRLIK:
        grup = [(s, v) for s, v in veri if s["tip"] == tip]
        if not grup:
            continue
        en_iyi = (None, -2.0)
        for f, g, d in itertools.product(izgara, repeat=3):
            l = round(1 - f - g - d, 4)
            if l < 0:
                continue
            w = {"frek": f, "goruntu": g, "dil": d, "llm": l}
            rho = []
            for s, v in grup:
                x, y = [], []
                for a in v["adaylar"]:
                    yz = a["yuzdelik"]
                    if "anket" not in a["sinyal"]:
                        continue
                    m = {k: w[k] for k in w if k in yz}
                    t = sum(m.values())
                    if t:
                        x.append(sum(m[k] / t * yz[k] for k in m)); y.append(a["sinyal"]["anket"])
                r = spearman(x, y)
                if r is not None:
                    rho.append(r)
            ort = sum(rho) / len(rho) if rho else -2
            if ort > en_iyi[1]:
                en_iyi = (w, ort)
        sonuc[tip] = {"agirlik": en_iyi[0], "ortalama_spearman": round(en_iyi[1], 4), "soru": len(grup)}
    h._yaz("cikti/kalibrasyon.json", sonuc)
    return json.dumps(sonuc, ensure_ascii=False, indent=1)
