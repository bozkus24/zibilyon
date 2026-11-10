"""Ham veri kaynakları: Wikidata SPARQL, Wikimedia görüntülenme, wordfreq.

Her ağ yanıtı tarih + sorgu metniyle önbelleğe yazılır; önbellek varsa ağa
çıkılmaz (aynı önbellek -> aynı çıktı). Ağ hatasında veri UYDURULMAZ: hata
yükseltilir ve hangi hostun yanıt vermediği raporlanır.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import statistics
import time
import urllib.parse
from pathlib import Path

import requests

UA = "TrPuzzle-Zibilyon-veri/1.0 (info@trpuzzle.com)"
SPARQL = "https://query.wikidata.org/sparql"
PV = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/tr.wikipedia/all-access/user/{baslik}/monthly/{bas}/{bit}"


class AgHatasi(RuntimeError):
    pass


class Onbellek:
    def __init__(self, kok: Path, kaynak: str):
        self.dizin = kok / "ham" / kaynak
        self.dizin.mkdir(parents=True, exist_ok=True)

    def yol(self, anahtar: str) -> Path:
        return self.dizin / (hashlib.sha1(anahtar.encode()).hexdigest()[:20] + ".json")

    def oku(self, anahtar: str):
        p = self.yol(anahtar)
        if p.exists():
            return json.loads(p.read_text())["yanit"]
        return None

    def yaz(self, anahtar: str, yanit) -> None:
        kayit = {"tarih": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "sorgu": anahtar, "yanit": yanit}
        self.yol(anahtar).write_text(json.dumps(kayit, ensure_ascii=False))


_oturum = requests.Session()
_oturum.headers["User-Agent"] = UA
_son_istek = {"t": 0.0}


def _getir(url: str, params: dict | None = None, accept: str = "application/json", bekle: float = 1.0, deneme_sayisi: int = 6):
    """Kibar GET: istekler arası bekleme, 429/5xx'te Retry-After ile geri çekilme."""
    son = "?"
    for deneme in range(deneme_sayisi):
        fark = time.time() - _son_istek["t"]
        if fark < bekle:
            time.sleep(bekle - fark)
        _son_istek["t"] = time.time()
        try:
            r = _oturum.get(url, params=params, headers={"Accept": accept}, timeout=120)
        except requests.RequestException as e:
            if deneme == deneme_sayisi - 1:
                raise AgHatasi(f"{urllib.parse.urlparse(url).hostname}: {e}") from e
            time.sleep(2 ** deneme)
            continue
        if r.status_code == 404:
            return None
        if r.status_code in (429, 500, 502, 503, 504):
            son = str(r.status_code)
            time.sleep(min(60, float(r.headers.get("Retry-After") or 2 ** min(deneme + 1, 5))))
            continue
        if r.status_code != 200:
            raise AgHatasi(f"{urllib.parse.urlparse(url).hostname}: HTTP {r.status_code}")
        return r.json()
    raise AgHatasi(f"{urllib.parse.urlparse(url).hostname}: tekrarlanan HTTP {son} (429=hız sınırı, 5xx/504=sorgu zaman aşımı)")


def sparql(kok: Path, sorgu: str, tazele: bool = False) -> list[dict]:
    ob = Onbellek(kok, "wikidata")
    if not tazele and (y := ob.oku(sorgu)) is not None:
        return y
    j = _getir(SPARQL, {"query": sorgu, "format": "json"}, "application/sparql-results+json", bekle=1.5)
    if j is None:
        raise AgHatasi("query.wikidata.org: 404")
    satirlar = [{k: v["value"] for k, v in b.items()} for b in j["results"]["bindings"]]
    ob.yaz(sorgu, satirlar)
    return satirlar


def _qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


ALANLAR = """
  OPTIONAL { ?x rdfs:label ?etiket FILTER(lang(?etiket)="tr") }
  OPTIONAL { ?x skos:altLabel ?takma FILTER(lang(?takma)="tr") }
  OPTIONAL { ?makale schema:about ?x ; schema:isPartOf <https://tr.wikipedia.org/> ; schema:name ?baslik }
  OPTIONAL { ?x wikibase:sitelinks ?dil }
  OPTIONAL { ?x wdt:P31 ?tur }
"""


def sinif_uyeleri(kok: Path, govde: str, tazele: bool = False) -> list[dict]:
    """``govde`` ?x değişkenini bağlayan SPARQL WHERE parçasıdır."""
    # Türkçe etiketi ya da trwiki makalesi olmayan öğeler (binlerce çeşit/alt tür)
    # baştan elenir; trwiki makalesi olup etiketi olmayanlar "etiketsiz" listesine düşer.
    sorgu = ("SELECT ?x ?etiket ?baslik ?dil (GROUP_CONCAT(DISTINCT ?takma; separator=\"|\") AS ?takmalar) "
             "(GROUP_CONCAT(DISTINCT ?tur; separator=\"|\") AS ?turler) WHERE {\n{ SELECT DISTINCT ?x WHERE {\n" + govde.strip() +
             "\nFILTER(EXISTS { ?x rdfs:label ?_e FILTER(lang(?_e)=\"tr\") } || EXISTS { ?_m schema:about ?x ; schema:isPartOf <https://tr.wikipedia.org/> })\n} }\n"
             + ALANLAR + "} GROUP BY ?x ?etiket ?baslik ?dil")
    return [_kayit(s) for s in sparql(kok, sorgu, tazele)]


def _kayit(s: dict) -> dict:
    return {
        "qid": _qid(s["x"]),
        "etiket": s.get("etiket"),
        "baslik": s.get("baslik"),
        "dil": int(s["dil"]) if s.get("dil") else 0,
        "takma": [t for t in (s.get("takmalar") or "").split("|") if t],
        "turler": [_qid(t) for t in (s.get("turler") or "").split("|") if t],
    }


def ada_gore_bul(kok: Path, adlar: list[str], dogrulama: str | None, tazele: bool = False) -> dict[str, list[dict]]:
    """Adları (tr etiket veya trwiki başlığı) Wikidata öğelerine çözer.

    ``dogrulama`` verilirse (ör. "?x wdt:P171* wd:Q729 .") yalnız onu sağlayan
    öğeler döner. Dönüş: ad -> aday öğeler (dil sayısına göre azalan).
    """
    sonuc: dict[str, list[dict]] = {a: [] for a in adlar}
    for i in range(0, len(adlar), 40):
        parca = adlar[i:i + 40]
        degerler = " ".join(json.dumps(a, ensure_ascii=False) + "@tr" for a in parca)
        govde = ("{ VALUES ?ad { " + degerler + " } { ?x rdfs:label ?ad } UNION "
                 "{ ?m schema:about ?x ; schema:isPartOf <https://tr.wikipedia.org/> ; schema:name ?ad } }\n" + (dogrulama or ""))
        sorgu = ("SELECT ?ad ?x ?etiket ?baslik ?dil (GROUP_CONCAT(DISTINCT ?takma; separator=\"|\") AS ?takmalar) "
                 "(GROUP_CONCAT(DISTINCT ?tur; separator=\"|\") AS ?turler) WHERE {\n" + govde + "\n" + ALANLAR +
                 "} GROUP BY ?ad ?x ?etiket ?baslik ?dil")
        for s in sparql(kok, sorgu, tazele):
            sonuc.setdefault(s["ad"], []).append(_kayit(s))
    for a in sonuc:
        sonuc[a].sort(key=lambda k: (-k["dil"], k["qid"]))
    return sonuc


def goruntulenme(kok: Path, baslik: str, bas: str, bit: str, tazele: bool = False) -> dict | None:
    """trwiki aylık görüntülenme (kullanıcı); ortalama ve medyan döner."""
    ob = Onbellek(kok, "pageviews")
    anahtar = f"{baslik}|{bas}|{bit}"
    y = None if tazele else ob.oku(anahtar)
    if y is None:
        url = PV.format(baslik=urllib.parse.quote(baslik.replace(" ", "_"), safe=""), bas=bas, bit=bit)
        # Wikimedia bu ortamın çıkış IP'sine sıkı hız sınırı uyguluyor (429, Retry-After: 20);
        # sınır neyse ona uyulur, istek sayısı artırılmaz.
        j = _getir(url, bekle=0.5, deneme_sayisi=40)
        y = {"aylar": {it["timestamp"][:6]: it["views"] for it in (j or {}).get("items", [])}}
        ob.yaz(anahtar, y)
    aylar = list(y["aylar"].values())
    if not aylar:
        return None
    # Eksik aylar 0 sayılır (makale yeni açılmış olabilir); 12 ay üzerinden.
    n = _ay_sayisi(bas, bit)
    tam = aylar + [0] * max(0, n - len(aylar))
    return {"ortalama": sum(tam) / n, "medyan": statistics.median(tam), "ay": len(aylar)}


def _ay_sayisi(bas: str, bit: str) -> int:
    return (int(bit[:4]) - int(bas[:4])) * 12 + int(bit[4:6]) - int(bas[4:6]) + 1


def frekans(ad: str) -> float:
    from wordfreq import zipf_frequency
    return zipf_frequency(ad, "tr")


def sozluk(n: int = 80000) -> list[str]:
    from wordfreq import top_n_list
    return top_n_list("tr", n)


API = "https://tr.wikipedia.org/w/api.php"


def goruntulenme_60g(kok: Path, basliklar: list[str], tazele: bool = False) -> dict[str, dict]:
    """trwiki Action API ile son 60 günün günlük görüntülenmesi (toplu istek, başlık bazında önbellek).

    REST API bu ortamda sıkı hız sınırına takıldığı için yedek kaynaktır. Dönüş:
    başlık -> {"ortalama": aylık eşdeğer ortalama, "medyan": aylık eşdeğer medyan, "gun": n}
    (günlük değer x 30). Verisi olmayan (görüntülenmesi 0 / makale yok) başlık için boş kayıt
    önbelleğe yazılır; böylece tekrar sorulmaz.
    """
    ob = Onbellek(kok, "pageviews60t")
    sonuc: dict[str, dict] = {}
    sirali = sorted(set(basliklar))
    eksik = [b for b in sirali if tazele or ob.oku(b) is None]
    for i in range(0, len(eksik), 50):
        parca = eksik[i:i + 50]
        bulunan, devam = {}, {}
        while True:  # API bir yanıtta yalnız bir kısım başlığın verisini verir; continue izlenir
            j = _getir(API, {"action": "query", "format": "json", "formatversion": "2", "prop": "pageviews",
                             "pvipdays": "60", "redirects": "1", "titles": "|".join(parca), **devam}, bekle=1.0, deneme_sayisi=40)
            q = (j or {}).get("query", {})
            ad = {n["to"]: n["from"] for n in q.get("normalized", [])}
            for r in q.get("redirects", []):
                ad[r["to"]] = ad.get(r["from"], r["from"])
            for p in q.get("pages", []):
                if p.get("pageviews"):
                    bulunan[ad.get(p["title"], p["title"])] = p["pageviews"]
            if not (j or {}).get("continue"):
                break
            devam = j["continue"]
            for b, v in bulunan.items():  # ara kayıt: kesilirse kaldığı yerden sürer
                ob.yaz(b, v)
        for b in parca:
            ob.yaz(b, bulunan.get(b, {}))
    for b in sirali:
        gunler = ob.oku(b) or {}
        v = [x or 0 for x in gunler.values()]
        if v:
            sonuc[b] = {"ortalama": 30 * sum(v) / len(v), "medyan": 30 * statistics.median(v), "gun": len(v)}
    return sonuc


def goruntulenme_onbellekte(kok: Path, baslik: str, bas: str, bit: str):
    """Yalnız önbellekten 12 aylık REST verisi (ağa çıkmaz)."""
    y = Onbellek(kok, "pageviews").oku(f"{baslik}|{bas}|{bit}")
    if y is None:
        return None
    aylar = list(y["aylar"].values())
    n = _ay_sayisi(bas, bit)
    tam = aylar + [0] * max(0, n - len(aylar))
    return {"ortalama": sum(tam) / n, "medyan": statistics.median(tam), "ay": len(aylar)} if aylar else {"ortalama": 0, "medyan": 0, "ay": 0}
