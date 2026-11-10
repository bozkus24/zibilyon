"""Zibilyon veri hattı: aday havuzu -> sinyaller -> harman -> katman -> rapor -> katalog.

Bütün düz metin veri git dışındaki ``.server-private/zibilyon/`` altındadır.
Hiçbir aşama eksik veriyi tahminle doldurmaz; eksik sinyal "yok" olarak kalır
ve ağırlıklar yeniden ölçeklenir.
"""
from __future__ import annotations

import csv
import json
import random
import re
from pathlib import Path

import yaml

from . import kaynaklar as K
from .istatistik import medyan, spearman, yuzdelik
from .normalize import bosluksuz, derle, katla, kucuk_tr, normalize

KATMANLAR = ["toprak", "komur", "demir", "altin", "elmas"]
KATMAN_AD = {"toprak": "Toprak", "komur": "Kömür", "demir": "Demir", "altin": "Altın", "elmas": "Elmas"}
PUAN = {"toprak": 10, "komur": 25, "demir": 50, "altin": 75, "elmas": 100}
AGIRLIK = {
    # 10 Kasım 2026 kararı: S_goruntu 60 günlük veride haber etkisine açık; ağırlığı düşürüldü.
    "cins": {"frek": 0.40, "goruntu": 0.05, "dil": 0.05, "llm": 0.50},
    "ozel": {"frek": 0.10, "goruntu": 0.25, "dil": 0.15, "llm": 0.50},
    "kapali": {"frek": 0.10, "goruntu": 0.25, "dil": 0.10, "llm": 0.55},
}
# 10 Kasım 2026 kararı: sabit sıra sınırları (büyük havuzlarda yüzdelik kota katmanları şişiriyordu).
SIRA_SINIR = [("toprak", 8), ("komur", 15), ("demir", 30), ("altin", 60)]  # kalanlar elmas
KUCUK_HAVUZ = 40  # bundan küçük havuzlarda (ör. 7 bölge) yüzdelik kota kullanılır
KOTA = [("toprak", 0.10), ("komur", 0.15), ("demir", 0.25), ("altin", 0.25), ("elmas", 0.25)]
ESIK_P = [("toprak", 0.08), ("komur", 0.03), ("demir", 0.01), ("altin", 0.003)]  # altı: elmas
PV_BAS, PV_BIT = "2025110100", "2026103100"  # son 12 tam ay (2025-11 .. 2026-10)
LLM_KOSU = 3


class Hat:
    def __init__(self, kok: Path):
        self.kok = kok
        for d in ["sorular", "ham/llm", "ham/anket", "editor", "cikti"]:
            (kok / d).mkdir(parents=True, exist_ok=True)

    # ── yardımcılar ──
    def sorular(self) -> list[dict]:
        out = []
        for p in sorted((self.kok / "sorular").glob("*.yaml")):
            s = yaml.safe_load(p.read_text())
            s.setdefault("takma", {})
            out.append(s)
        return out

    def soru(self, sid: str) -> dict:
        for s in self.sorular():
            if s["id"] == sid:
                return s
        raise SystemExit(f"Soru yok: {sid}")

    def _json(self, ad: str, varsayilan=None):
        p = self.kok / ad
        return json.loads(p.read_text()) if p.exists() else varsayilan

    def _yaz(self, ad: str, veri) -> Path:
        p = self.kok / ad
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(veri, ensure_ascii=False, indent=1) + "\n")
        return p

    @staticmethod
    def _temizle(metin: str | None, desenler: list[str]) -> str | None:
        if metin is None:
            return None
        for d in desenler:
            metin = re.sub(d, "", metin, flags=re.I)
        return metin.strip()

    # ── 1. aday havuzu ──
    def topla(self, s: dict, tazele: bool = False) -> dict:
        sid = s["id"]
        haric_p31 = set(s.get("haric_p31", []))
        desenler = [re.compile(d) for d in s.get("haric_desen", [])]
        red = {normalize(r) for r in s.get("red_listesi", [])}
        etiket_sil = s.get("etiket_sil", [])
        havuz: dict[str, dict] = {}
        elenen: list[dict] = []
        etiketsiz: list[dict] = []

        def ele(ad, neden, **ek):
            elenen.append({"ad": ad, "neden": neden, **ek})

        # Wikidata sınıf üyeleri
        satirlar: dict[str, dict] = {}
        for govde in s.get("wikidata", []):
            for k in K.sinif_uyeleri(self.kok, govde, tazele):
                satirlar.setdefault(k["qid"], k)
        if s.get("wikidata_dogrula") and satirlar:
            gecen = self._dogrula(list(satirlar), s["wikidata_dogrula"], tazele)
            for q in list(satirlar):
                if q not in gecen:
                    ele(satirlar[q]["etiket"] or q, "dogrulama_disi", qid=q)
                    del satirlar[q]
        for q in sorted(satirlar):
            k = satirlar[q]
            if not k["etiket"]:
                etiketsiz.append({"qid": q, "baslik": k["baslik"]})
                continue
            ad = self._temizle(k["etiket"], etiket_sil)
            # "Şo (enstrüman)" -> "Şo": parantezli açıklama görünen ada girmez, takma ad olarak kalır
            ad_temiz = re.sub(r"\s*\([^)]*\)\s*$", "", ad).strip() or ad
            if ad_temiz != ad:
                k = {**k, "takma": [*k["takma"], ad]}
                ad = ad_temiz
            n = normalize(ad)
            if haric_p31 & set(k["turler"]):
                ele(ad, "haric_p31", qid=q); continue
            if any(d.search(n) or (k["baslik"] and d.search(normalize(k["baslik"]))) for d in desenler):
                ele(ad, "haric_desen", qid=q); continue
            if s.get("trwiki_zorunlu") and not k["baslik"]:
                ele(ad, "trwiki_yok", qid=q); continue
            if len(n.split()) > 4 or not bosluksuz(n):
                ele(ad, "uzun_ad", qid=q); continue
            self._ekle(havuz, n, ad, "wikidata", k)

        # LLM ve editör adayları
        ek_a = self._json(f"ham/llm/{sid}.ek_a.json", {}) or {}
        beyin = self._json(f"ham/llm/{sid}.beyin.json", {}) or {}
        llm_adlar = [a for t in KATMANLAR for a in ek_a.get("katmanlar", {}).get(t, [])] + beyin.get("adaylar", [])
        editor = []
        p = self.kok / "editor" / "ekle.csv"
        if p.exists():
            for r in csv.DictReader(p.open()):
                if r.get("id") == sid:
                    editor.append(r)
        cozulecek = []
        for kaynak, adlar in [("llm", llm_adlar), ("editor", [r["ad"] for r in editor])]:
            for ad in adlar:
                n = normalize(ad)
                if not n:
                    continue
                if n in havuz:
                    havuz[n]["kaynak"] = sorted(set(havuz[n]["kaynak"]) | {kaynak})
                else:
                    cozulecek.append((kaynak, ad, n))
        # Wikidata'da ada göre çöz (eksik QID / makale / sitelink için)
        adlar = sorted({ad for _, ad, _ in cozulecek} | {ad[:1].upper() + ad[1:] for _, ad, _ in cozulecek})
        bulunan = K.ada_gore_bul(self.kok, adlar, s.get("dogrulama"), tazele) if adlar else {}
        qid_n = {v["qid"]: n for n, v in havuz.items() if v.get("qid")}
        for kaynak, ad, n in cozulecek:
            if n in havuz:
                havuz[n]["kaynak"] = sorted(set(havuz[n]["kaynak"]) | {kaynak}); continue
            adaylar = bulunan.get(ad, []) + bulunan.get(ad[:1].upper() + ad[1:], [])
            adaylar = [a for a in adaylar if a["baslik"]] or adaylar
            adaylar.sort(key=lambda k: (-k["dil"], k["qid"]))
            k = adaylar[0] if adaylar else None
            if k and k["qid"] in qid_n:
                # Aynı öğe: bu ad bir takma addır. Gündelik ad daha kısaysa kanonik ad o olur
                # (ör. Wikidata "Kuyruksuz kurbağalar" -> "kurbağa").
                eski = qid_n[k["qid"]]
                hedef = havuz[eski]
                hedef["kaynak"] = sorted(set(hedef["kaynak"]) | {kaynak})
                baslik_n = normalize(re.sub(r" \(.*\)$", "", hedef.get("baslik") or ""))
                if (len(n.split()) < len(eski.split()) or (n == baslik_n and eski != baslik_n)) and n not in havuz:
                    hedef["takma"] = sorted((set(hedef["takma"]) | {hedef["ad"]}) - {ad})
                    hedef["ad"], hedef["n"] = ad, n
                    havuz[n] = havuz.pop(eski); qid_n[k["qid"]] = n
                else:
                    hedef["takma"] = sorted(set(hedef["takma"]) | {ad})
                continue
            self._ekle(havuz, n, ad, kaynak, k, dogrulandi=bool(k and s.get("dogrulama")))
            if k:
                qid_n[k["qid"]] = n

        # LLM uygunluk değerlendirmesi (llm etiketli; editör override ile geri alınabilir)
        uy = self._json(f"ham/llm/{sid}.uygunluk.json", {}) or {}
        geri_al = self._editor_geri_al(sid)
        ad_haritasi = {}
        for n0, a0 in havuz.items():
            for x in [a0["ad"], *a0.get("takma", []), *a0.get("wd_takma", [])]:
                ad_haritasi.setdefault(normalize(x), n0)
        for x in uy.get("hayir", []):
            n = ad_haritasi.get(normalize(x))
            if n and n in havuz and n not in geri_al:
                ele(havuz[n]["ad"], "llm_uygunsuz", qid=havuz[n].get("qid")); del havuz[n]
        supheli = {normalize(x) for x in uy.get("supheli", [])}
        takma_cfg = {normalize(k): v or [] for k, v in s.get("takma", {}).items()}
        for n, a in havuz.items():
            # editör takma adı anahtarı adayın adı, Wikidata takma adı ya da trwiki başlığı olabilir
            bas = normalize(re.sub(r"\s*\([^)]*\)\s*$", "", a.get("baslik") or ""))
            for anahtar in {n, bas, *(normalize(t) for t in a.get("wd_takma", []))}:
                if anahtar in takma_cfg:
                    a["takma"] = sorted(set(a["takma"]) | set(takma_cfg[anahtar]) | ({anahtar} if anahtar != n else set()))
        # Kopya birleştirme: ortak eşleştiricinin a-c adımlarıyla aynı yere düşen adlar tek cevaptır
        birlesen = self._birlestir(havuz)
        # Kırmızı liste, çeşit gürültüsü, işaretler
        adlar_n = set(havuz)
        for n in sorted(havuz):
            a = havuz[n]
            if n in red:
                ele(a["ad"], "red_listesi"); del havuz[n]; continue
            if s.get("cesit_filtre", True) and a["kaynak"] == ["wikidata"] and " " in n:
                kelimeler = n.split()
                if any(self._cesit_mi(w, adlar_n - {n}) for w in kelimeler):
                    ele(a["ad"], "cesit_gurultusu", qid=a.get("qid")); del havuz[n]; continue
        es = {normalize(x) for x in s.get("es_sesli", [])}
        cel = {normalize(x) for x in s.get("celiskili", [])}
        for n, a in havuz.items():
            a["es_sesli"] = n in es
            a["celiskili"] = n in cel
            a["cok_kelimeli"] = " " in n
            a["llm_supheli"] = n in supheli or any(normalize(t) in supheli for t in a["takma"])
        if s.get("beklenen_sayi") and len(havuz) != s["beklenen_sayi"]:
            print(f"UYARI {sid}: beklenen {s['beklenen_sayi']} aday, bulunan {len(havuz)}")
        sonuc = {"id": sid, "adaylar": [havuz[n] for n in sorted(havuz)], "elenen": elenen, "etiketsiz": etiketsiz,
                 "birlesen": birlesen}
        self._yaz(f"cikti/{sid}.adaylar.json", sonuc)
        return sonuc

    def _editor_geri_al(self, sid) -> set[str]:
        p = self.kok / "editor" / "override.csv"
        if not p.exists():
            return set()
        return {normalize(r["cevap"]) for r in csv.DictReader(p.open()) if r.get("id") == sid and r["katman"].strip() != "sil"}

    @staticmethod
    def _birlestir(havuz: dict) -> list[dict]:
        from .normalize import anahtarlar, eslestir
        def oncelik(n):
            a = havuz[n]
            return (-len(a["kaynak"]), a.get("qid") is None, -(a.get("dil") or 0), len(n), n)
        tablo = {"tam": {}, "kat": {}, "red": [], "niteleyici": [], "engel": []}
        tutulan, birlesen = [], []
        for n in sorted(havuz, key=oncelik):
            a = havuz[n]
            hedef = None
            for ad in [a["ad"]] + a["takma"]:
                r = eslestir(ad, tablo, yazim=False)
                if r["tur"] == "kabul":
                    hedef = tutulan[r["i"]]; break
            if hedef is not None:
                h = havuz[hedef]
                if bosluksuz(a["n"]) == bosluksuz(h["n"]) and " " in a["n"] and " " not in h["n"]:
                    a["ad"], h["ad"] = h["ad"], a["ad"]  # okunaklı (boşluklu) yazım kanonik olsun
                h["takma"] = sorted((set(h["takma"]) | {a["ad"]} | set(a["takma"])) - {h["ad"]})
                h["wd_takma"] = sorted(set(h.get("wd_takma", [])) | set(a.get("wd_takma", [])))
                h["kaynak"] = sorted(set(h["kaynak"]) | set(a["kaynak"]))
                birlesen.append({"ad": a["ad"], "hedef": h["ad"]})
                del havuz[n]; continue
            i = len(tutulan); tutulan.append(n)
            for ad in [a["ad"]] + a["takma"]:
                for k in anahtarlar(ad):
                    tablo["tam"].setdefault(k, i); tablo["kat"].setdefault(katla(k), i)
        return birlesen

    @staticmethod
    def _cesit_mi(kelime: str, adlar: set[str]) -> bool:
        for ek in ["", "ı", "i", "u", "ü", "sı", "si", "su", "sü", "leri", "ları", "ler", "lar"]:
            if ek and kelime.endswith(ek) and kelime[: -len(ek)] in adlar:
                return True
            if not ek and kelime in adlar:
                return True
        return False

    def _dogrula(self, qidler: list[str], kosul: str, tazele: bool) -> set[str]:
        gecen = set()
        for i in range(0, len(qidler), 60):
            v = " ".join("wd:" + q for q in qidler[i:i + 60])
            for r in K.sparql(self.kok, "SELECT DISTINCT ?x WHERE { VALUES ?x { " + v + " } " + kosul + " }", tazele):
                gecen.add(r["x"].rsplit("/", 1)[-1])
        return gecen

    def _ekle(self, havuz, n, ad, kaynak, k=None, dogrulandi=None):
        takma = []
        if k:
            for t in k.get("takma", []):
                tn = normalize(t)
                if tn and tn != n and len(tn.split()) <= 4 and not re.search(r"\d", tn) and len(bosluksuz(tn)) >= 2:
                    takma.append(t)
        havuz[n] = {
            "ad": ad, "n": n, "kaynak": [kaynak],
            "qid": k["qid"] if k else None, "baslik": k["baslik"] if k else None,
            "dil": k["dil"] if k else None, "takma": [], "wd_takma": sorted(set(takma)),
            "qid_kontrol": None if not k else ("dogrulandi" if (dogrulandi or kaynak == "wikidata") else "ada_gore_eslesti"),
        }

    # ── 2. LLM istemleri ──
    IFADE = [
        "100 rastgele Türk yetişkine şu soru soruluyor ve her biri 30 saniye içinde TEK cevap veriyor: «{soru}». "
        "Aşağıdaki her adayı kaç kişi verir? Toplam 100 olsun; listede olmayan cevaplar 'diğer' satırına. Ondalık serbest (ör. 0.2).",
        "Bir sokak röportajında yüz yetişkine «{soru}» diye soruluyor; düşünmeye vakit yok, ilk akla gelen söyleniyor. "
        "Listedeki her cevabın yüz kişiden kaçında çıkacağını tahmin et (toplam 100, kalanı 'diğer'; ondalık olabilir).",
        "Türkiye'yi temsil eden 100 kişilik bir örneklem «{soru}» sorusuna yarım dakikada tek cevap yazıyor. "
        "Her aday için beklenen kişi sayısını ver; toplam 100 olacak, listede olmayanlar 'diğer'. Çok nadir cevaplara 0 ile 1 arası değer verebilirsin.",
    ]

    def llm_istem(self, s: dict) -> list[Path]:
        havuz = self._json(f"cikti/{s['id']}.adaylar.json")
        adlar = [a["ad"] for a in havuz["adaylar"]]
        yollar = []
        for k in range(LLM_KOSU):
            r = random.Random(f"{s['id']}:{k}")
            liste = adlar[:]
            r.shuffle(liste)
            metin = self.IFADE[k].format(soru=s["metin"]) + "\n\nAdaylar:\n" + "\n".join(liste) + \
                f"\n\nYanıt biçimi: ham/llm/{s['id']}.yanit.{k}.json -> {{\"cevaplar\": {{ad: sayı}}, \"diger\": sayı}}\n"
            p = self.kok / f"ham/llm/{s['id']}.istem.{k}.txt"
            p.write_text(metin)
            yollar.append(p)
        return yollar

    # ── 3. sinyaller ──
    def sinyal(self, s: dict, tazele: bool = False) -> dict:
        sid = s["id"]
        havuz = self._json(f"cikti/{sid}.adaylar.json")
        # LLM yanıtındaki adlar adayın adı veya takma adlarıyla eşlenir.
        esle = {}
        for a in havuz["adaylar"]:
            bas = re.sub(r"\s*\([^)]*\)\s*$", "", a.get("baslik") or "")
            for x in [a["ad"], *a.get("takma", []), *([bas] if bas else [])]:
                esle.setdefault(normalize(x), a["n"])
                esle.setdefault(bosluksuz(normalize(x)), a["n"])
        kosular = []
        for k in range(LLM_KOSU):
            y = self._json(f"ham/llm/{sid}.yanit.{k}.json")
            if y:
                ks: dict[str, float] = {}
                for ad, v in y["cevaplar"].items():
                    n = normalize(ad)
                    hedef = esle.get(n) or esle.get(bosluksuz(n)) or n
                    ks[hedef] = ks.get(hedef, 0.0) + float(v)
                kosular.append(ks)
        anket = self._json(f"cikti/{sid}.anket.json")
        uyari_llm = []
        if kosular:
            bilinen = {a["n"] for a in havuz["adaylar"]}
            for i, ks in enumerate(kosular):
                fazla = sorted(set(ks) - bilinen)
                if fazla:
                    uyari_llm.append(f"koşu {i}: listede olmayan {len(fazla)} ad yok sayıldı: {', '.join(fazla[:5])}")
        # S_goruntu kaynağı soru içinde TEK olmalı: tüm makalelerin 12 aylık REST verisi
        # önbellekte varsa o; yoksa hepsi için 60 günlük Action API verisi.
        basliklar = [a["baslik"] for a in havuz["adaylar"] if a.get("baslik")]
        on12 = {b: K.goruntulenme_onbellekte(self.kok, b, PV_BAS, PV_BIT) for b in basliklar}
        if basliklar and all(v is not None for v in on12.values()):
            pv_kaynak, havuz["goruntu_kaynagi"] = on12, f"REST 12 ay ({PV_BAS[:6]}-{PV_BIT[:6]})"
        else:
            pv_kaynak = K.goruntulenme_60g(self.kok, basliklar, tazele)
            eksik = sum(1 for v in on12.values() if v is None)
            havuz["goruntu_kaynagi"] = f"Action API son 60 gün (12 aylık REST verisi {eksik}/{len(basliklar)} makalede eksik)"
        import math
        for a in havuz["adaylar"]:
            sig = {}
            # S_frek: ad ve editör takma adlarının en yükseği; eş seslide kullanılmaz
            if not a["es_sesli"]:
                takma = {normalize(k): v or [] for k, v in s.get("takma", {}).items()}
                adlar = [a["ad"]] + takma.get(a["n"], [])
                sig["frek"] = max(K.frekans(normalize(x)) for x in adlar)
            a["frek_guven"] = "dusuk" if a["cok_kelimeli"] else "normal"
            a["frek_yok"] = (not a["es_sesli"]) and sig.get("frek", 0) == 0
            if a.get("baslik"):
                pv = pv_kaynak.get(a["baslik"])
                if pv:
                    a["pv"] = pv
                    sig["goruntu"] = math.log10(1 + min(pv["ortalama"], pv["medyan"]))
            if a.get("dil"):
                sig["dil"] = float(a["dil"])
            if len(kosular) == LLM_KOSU:
                v = [ks.get(a["n"], 0.0) for ks in kosular]
                sig["llm"] = medyan(v)
                a["llm_kosular"] = v
                a["kararsiz"] = (max(v) - min(v) >= 10) or (min(v) == 0 and max(v) >= 5)
            if anket and a["n"] in anket["p"]:
                sig["anket"] = anket["p"][a["n"]]
            for kod in s.get("sinyal_haric", []):  # soru tanımında güvenilmez ilan edilen sinyaller
                sig.pop(kod, None)
            a["sinyal"] = sig
        havuz["llm_uyari"] = uyari_llm
        havuz["sinyal_haric"] = s.get("sinyal_haric", [])
        havuz["llm_kosu"] = len(kosular)
        self._yaz(f"cikti/{sid}.sinyal.json", havuz)
        return havuz

    # ── 4. harman + katman ──
    def harmanla(self, s: dict, agirlik: dict | None = None) -> dict:
        sid = s["id"]
        veri = self._json(f"cikti/{sid}.sinyal.json")
        ad = veri["adaylar"]
        w = (agirlik or AGIRLIK)[s["tip"]]
        yz = {}
        for kod in ["frek", "goruntu", "dil", "llm", "anket"]:
            yz[kod] = yuzdelik({a["n"]: a["sinyal"][kod] for a in ad if kod in a["sinyal"]})
        for a in ad:
            a["yuzdelik"] = {k: round(yz[k][a["n"]], 4) for k in yz if a["n"] in yz[k]}
            mevcut = {k: w[k] for k in w if k in a["yuzdelik"]}
            top = sum(mevcut.values())
            a["bilesik"] = round(sum(v / top * a["yuzdelik"][k] for k, v in mevcut.items()), 4) if top else None
            a["veri_bilesik"] = self._veri_bilesik(a, w)
            if "anket" in a["yuzdelik"] and a["bilesik"] is not None:
                a["nihai"] = round(0.7 * a["yuzdelik"]["anket"] + 0.3 * a["bilesik"], 4)
            else:
                a["nihai"] = a["bilesik"]
            sira = [a["yuzdelik"][k] for k in ("frek", "goruntu", "dil", "llm") if k in a["yuzdelik"]]
            a["sira_farki"] = round(max(sira) - min(sira), 3) if len(sira) > 1 else 0
        self._katmanla(s, ad, veri)
        self._override(s, ad)
        veri["agirlik"] = w
        llm, digr = [], []
        for a in ad:
            if "llm" in a["yuzdelik"] and a["veri_bilesik"] is not None:
                llm.append(a["yuzdelik"]["llm"]); digr.append(a["veri_bilesik"])
        veri["spearman_llm_veri"] = spearman(llm, digr)
        veri["spearman_n"] = len(llm)
        self._yaz(f"cikti/{sid}.json", veri)
        return veri

    @staticmethod
    def _veri_bilesik(a, w):
        mevcut = {k: w[k] for k in ("frek", "goruntu", "dil") if k in a["yuzdelik"]}
        top = sum(mevcut.values())
        return round(sum(v / top * a["yuzdelik"][k] for k, v in mevcut.items()), 4) if top else None

    def _katmanla(self, s, ad, veri):
        puanli = [a for a in ad if a["nihai"] is not None]
        anketli = all("anket" in a["sinyal"] for a in puanli) and puanli
        sirali = sorted(puanli, key=lambda a: (-a["nihai"], a["n"]))
        n = len(sirali)
        if anketli:
            for a in sirali:
                p = a["sinyal"]["anket"]
                a["katman_oneri"] = next((t for t, e in ESIK_P if p >= e), "elmas")
            veri["katman_yontemi"] = "anket_esik"
        else:
            sinirlar, birikim = [], 0.0
            if n >= KUCUK_HAVUZ:
                for t, adet in SIRA_SINIR:
                    birikim += adet
                    sinirlar.append((t, int(birikim)))
                sinirlar.append(("elmas", n))
                veri["katman_yontemi"] = "sabit_sira"
            else:
                for t, oran in KOTA:
                    birikim += oran
                    sinirlar.append((t, round(birikim * n)))
                veri["katman_yontemi"] = "kota"
            sayac = {t: 0 for t in KATMANLAR}
            atama = []
            for i, a in enumerate(sirali):
                t = next((t for t, sinir in sinirlar if i < sinir), "elmas")
                atama.append(t)
            # kısıtlar: Toprak <= 8; her katmanda en az 2 (yeterli aday varsa)
            while atama.count("toprak") > 8:
                i = max(j for j, t in enumerate(atama) if t == "toprak"); atama[i] = "komur"
            if n >= 10:
                for ti, t in enumerate(KATMANLAR):
                    while atama.count(t) < 2:
                        # komşu katmandan sınırdaki adayı çek
                        if ti + 1 < len(KATMANLAR) and atama.count(KATMANLAR[ti + 1]) > 2:
                            j = atama.index(KATMANLAR[ti + 1]); atama[j] = t
                        elif ti > 0 and atama.count(KATMANLAR[ti - 1]) > 2:
                            j = max(k for k, x in enumerate(atama) if x == KATMANLAR[ti - 1]); atama[j] = t
                        else:
                            break
            for a, t in zip(sirali, atama):
                a["katman_oneri"] = t
                sayac[t] += 1
        for i, a in enumerate(sirali):
            a["sira"] = i + 1
        for a in ad:
            if a["nihai"] is None:
                a["katman_oneri"] = None
                a["sira"] = None
            a["katman"] = a["katman_oneri"]
            a["uyarilar"] = self._uyarilar(a)

    @staticmethod
    def _uyarilar(a) -> list[str]:
        u = []
        if a.get("sira_farki", 0) > 0.4: u.append("sinyal_sira_farki>0.4")
        if a.get("kararsiz"): u.append("llm_kararsiz")
        if a.get("llm_supheli"): u.append("llm_kategori_supheli")
        if a.get("es_sesli"): u.append("es_sesli")
        if a.get("celiskili"): u.append("celiskili")
        if a.get("cok_kelimeli"): u.append("cok_kelimeli(frek_guven_dusuk)")
        if a.get("frek_yok"): u.append("frek_yok")
        if a.get("qid_kontrol") == "ada_gore_eslesti": u.append("qid_ada_gore(eslesme_kontrol_et)")
        if not a.get("qid"): u.append("wikidata_yok")
        if a["kaynak"] == ["llm"]: u.append("yalniz_llm_kaynakli")
        if a.get("katman") == "elmas": u.append("elmas_editor_onayi_gerekli")
        return u

    def _override(self, s, ad):
        p = self.kok / "editor" / "override.csv"
        if not p.exists():
            return
        harita = {a["n"]: a for a in ad}
        for r in csv.DictReader(p.open()):
            if r.get("id") != s["id"]:
                continue
            a = harita.get(normalize(r["cevap"]))
            if not a:
                print(f"UYARI override: {s['id']} '{r['cevap']}' havuzda yok"); continue
            k = r["katman"].strip()
            a.setdefault("override", []).append({"katman": k, "gerekce": r.get("gerekce", "")})
            if k in KATMANLAR:
                a["katman"] = k; a["editor_onay"] = True
            elif k == "onay":
                a["editor_onay"] = True
            elif k == "sil":
                a["katman"] = None; a["silindi"] = True
            elif k.startswith("birlestir:"):
                hedef = harita.get(normalize(k.split(":", 1)[1]))
                if not hedef:
                    print(f"UYARI override: {s['id']} birleştirme hedefi yok: {k}"); continue
                hedef["takma"] = sorted(set(hedef.get("takma", [])) | {a["ad"], *a.get("takma", [])})
                a["katman"] = None; a["silindi"] = True; a["birlesti"] = hedef["ad"]

    # ── 5. katalog (sunucu) ──
    def katalog(self, sorular: list[dict]) -> dict:
        sozluk = {katla(normalize(w)) for w in K.sozluk()}
        kat = {"surum": 1, "sorular": {}, "rapor": {}}
        for s in sorular:
            veri = self._json(f"cikti/{s['id']}.json")
            if not veri:
                continue
            kabul, tavan = [], []
            for a in sorted(veri["adaylar"], key=lambda a: (a["sira"] or 10 ** 6, a["n"])):
                t = a.get("katman")
                if not t or a.get("silindi"):
                    continue
                # Elmas yalnız editör onayıyla; frek verisi olmayan sözlük kelimesi onaysız Altın'da tavanlanır.
                if t == "elmas" and not a.get("editor_onay"):
                    t = "altin"; tavan.append(a["ad"])
                # Görünen ad: cins isimlerde gündelik küçük yazım (özel adlarda olduğu gibi)
                gorunen = kucuk_tr(a["ad"]) if s["tip"] == "cins" else a["ad"]
                kabul.append({"ad": gorunen, "takma": a.get("takma", []), "wd_takma": a.get("wd_takma", []), "katman": t})
            tablo = derle(kabul, s.get("red_listesi", []), s.get("niteleyiciler"), s.get("ek_kaldir"), sozluk)
            cevher = s.get("cevher")
            cevher_kaynagi = "editor" if cevher else None
            if not cevher:
                cevher = (self._json(f"ham/llm/{s['id']}.ek_a.json", {}) or {}).get("cevher_oneri")
                cevher_kaynagi = "ek_a_onerisi(editör onayı bekliyor)" if cevher else None
            ci = next((i for i, c in enumerate(kabul) if cevher and normalize(c["ad"]) == normalize(cevher)), None)
            ornek = {t: [c["ad"] for c in kabul if c["katman"] == t][:3] for t in KATMANLAR}
            kat["sorular"][s["id"]] = {
                "metin": s["metin"], "tip": s["tip"], "kategori": s.get("kategori"),
                "kategori_disi_mesaj": s.get("kategori_disi_mesaj") or self._red_mesaj(s),
                "cevaplar": [{"ad": c["ad"], "katman": c["katman"]} for c in kabul],
                "eslesme": tablo, "cevher": ci, "ornekler": ornek,
            }
            belirsiz = sorted(k for k, v in tablo["tam"].items() if v == -1)
            kat["rapor"][s["id"]] = {"cevap": len(kabul), "elmas_tavan": tavan, "belirsiz_anahtar": belirsiz,
                                     "engel": len(tablo["engel"]), "cevher": cevher if ci is not None else None,
                                     "cevher_kaynagi": cevher_kaynagi if ci is not None else ("bulunamadi" if cevher else None)}
        self._yaz("cikti/katalog.json", kat)
        return kat

    @staticmethod
    def _red_mesaj(s):
        m = re.match(r"Bir (.+?) söyle", s["metin"])
        return f"Bu bir {m.group(1)} değil." if m else "Bu cevap kategoriye uymuyor."
