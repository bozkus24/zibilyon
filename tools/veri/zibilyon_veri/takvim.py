"""Günlük 7'li soru setleri ve kural denetimi (cikti/takvim.json).

Kurallar: günde 7 soru; >= 2 cins, >= 2 özel, <= 1 kapalı; <= 1 bilgi ağırlıklı;
aynı kategori >= 45 gün arayla; bölgesel soru (ör. İstanbul) haftada <= 1;
zorluk dengesi: günün bileşik medyanları ortalaması hedef banda yakın.
Deterministik: aynı soru havuzu -> aynı takvim. İhlaller raporlanır, gizlenmez.
"""
from __future__ import annotations

import datetime as dt
import json
import random

from .istatistik import medyan

GUNLUK = 7
KATEGORI_ARA = 45


def zorluk(h, sid: str) -> float | None:
    p = h.kok / f"cikti/{sid}.json"
    if not p.exists():
        return None
    v = json.loads(p.read_text())
    b = [a["bilesik"] for a in v["adaylar"] if a.get("bilesik") is not None]
    return medyan(b) if b else None


def takvim(h, sorular: list[dict], baslangic: str = "2026-12-01", gun_sayisi: int = 90) -> str:
    havuz = sorted(sorular, key=lambda s: s["id"])
    r = random.Random("zibilyon-takvim-v1")
    kullanilan: set[str] = set()
    son_kategori: dict[str, int] = {}
    son_bolgesel: dict[str, int] = {}
    gunler, ihlal = [], []
    bas = dt.date.fromisoformat(baslangic)
    for g in range(gun_sayisi):
        kalan = [s for s in havuz if s["id"] not in kullanilan]
        if len(kalan) < GUNLUK:
            ihlal.append(f"{g + 1}. gün ve sonrası: soru havuzu yetersiz ({len(kalan)} kaldı, {GUNLUK} gerekli)")
            break
        r.shuffle(kalan)
        secim: list[dict] = []

        def uygun(s):
            k = s.get("kategori")
            if k and g - son_kategori.get(k, -10 ** 6) < KATEGORI_ARA:
                return False
            if any(x.get("kategori") == k for x in secim):
                return False
            b = s.get("bolgesel")
            if b and g - son_bolgesel.get(b, -10 ** 6) < 7:
                return False
            if s["tip"] == "kapali" and sum(x["tip"] == "kapali" for x in secim) >= 1:
                return False
            if s.get("bilgi_agirlikli") and sum(bool(x.get("bilgi_agirlikli")) for x in secim) >= 1:
                return False
            return True

        for gerek in ["cins", "cins", "ozel", "ozel"]:
            for s in kalan:
                if s not in secim and s["tip"] == gerek and uygun(s):
                    secim.append(s); break
        for s in kalan:
            if len(secim) >= GUNLUK:
                break
            if s not in secim and uygun(s):
                secim.append(s)
        if len(secim) < GUNLUK:
            # Kurala uyan yeterli soru yok: ihlali kaydedip kalanla doldur
            eksik = [s for s in kalan if s not in secim][: GUNLUK - len(secim)]
            ihlal.append(f"{g + 1}. gün: kurallara uyan soru yetersiz; {len(eksik)} soru kural dışı eklendi "
                         f"({', '.join(s['id'] for s in eksik)})")
            secim += eksik
        tipler = [s["tip"] for s in secim]
        if tipler.count("cins") < 2 or tipler.count("ozel") < 2 or tipler.count("kapali") > 1:
            ihlal.append(f"{g + 1}. gün: tip karışımı ihlali {tipler}")
        z = [zorluk(h, s["id"]) for s in secim]
        for s in secim:
            kullanilan.add(s["id"])
            if s.get("kategori"):
                son_kategori[s["kategori"]] = g
            if s.get("bolgesel"):
                son_bolgesel[s["bolgesel"]] = g
        gunler.append({"tarih": (bas + dt.timedelta(days=g)).isoformat(), "sorular": [s["id"] for s in secim],
                       "zorluk_ortalama": round(sum(x for x in z if x is not None) / max(1, sum(x is not None for x in z)), 3)})
    h._yaz("cikti/takvim.json", {"baslangic": baslangic, "gunler": gunler, "ihlaller": ihlal})
    return json.dumps({"gun": len(gunler), "ihlal": ihlal[:20]}, ensure_ascii=False, indent=1)
