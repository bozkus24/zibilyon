"""Zibilyon cevap normalizasyonu ve eşleştirme (Python).

Bu dosya ile ``server/eslestir.mjs`` aynı kuralları uygular. İkisi de
``ortak/normalize_vektorleri.json`` dosyasındaki test vektörleriyle doğrulanır.
Kural değişirse İKİ dosya ve vektörler birlikte değişmelidir.
"""
from __future__ import annotations

import re
import unicodedata

# Kesme işaretleri silinir (Bursa'dan -> bursadan); diğer noktalama boşluğa döner.
KESME = "'’‘`´ʼ"
SAPKA = str.maketrans({"â": "a", "î": "i", "û": "u"})
KATLA = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u"})

# Uzundan kısaya: önce uzun ek denenir. Yalnız soyulmuş biçim tabloda varsa kabul.
EKLER = sorted({
    "lar", "ler",
    "ı", "i", "u", "ü", "yı", "yi", "yu", "yü", "sı", "si", "su", "sü",
    "a", "e", "ya", "ye",
    "da", "de", "ta", "te", "dan", "den", "tan", "ten",
    "ın", "in", "un", "ün", "nın", "nin", "nun", "nün",
}, key=lambda e: (-len(e), e))
# Ünsüz yumuşamasının tersi: ağac -> ağaç, kitab -> kitap, reng -> renk
YUMUSAMA = {"b": "p", "c": "ç", "d": "t", "ğ": "k", "g": "k"}
EN_KISA_KOK = 2


def kucuk_tr(s: str) -> str:
    """tr-TR küçük harf: İ->i, I->ı (JS toLocaleLowerCase('tr-TR') ile aynı)."""
    s = s.replace("İ", "i").replace("I", "ı")
    s = s.lower()
    return s.replace("i̇", "i")


def normalize(metin: str) -> str:
    s = unicodedata.normalize("NFC", str(metin))
    s = kucuk_tr(s)
    s = unicodedata.normalize("NFC", s).translate(SAPKA)
    out = []
    for ch in s:
        if ch in KESME:
            continue
        kat = unicodedata.category(ch)
        if kat[0] in ("L", "N") or ch == " ":
            out.append(ch)
        else:
            out.append(" ")
    return re.sub(r"\s+", " ", "".join(out)).strip()


def bosluksuz(s: str) -> str:
    return s.replace(" ", "")


def katla(s: str) -> str:
    return s.translate(KATLA)


def tolerans(uzunluk: int) -> int:
    if uzunluk <= 4:
        return 0
    if uzunluk <= 7:
        return 1
    return 2


def mesafe(a: str, b: str, sinir: int = 99) -> int:
    """Damerau-Levenshtein (optimal string alignment) mesafesi."""
    if abs(len(a) - len(b)) > sinir:
        return sinir + 1
    onceki2 = None
    onceki = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        simdi = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            maliyet = 0 if a[i - 1] == b[j - 1] else 1
            simdi[j] = min(onceki[j] + 1, simdi[j - 1] + 1, onceki[j - 1] + maliyet)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                simdi[j] = min(simdi[j], onceki2[j - 2] + 1)
        onceki2, onceki = onceki, simdi
    return onceki[len(b)]


def kokler(s: str) -> list[str]:
    """Ek soyma adayları (en çok iki ek), sıra deterministik."""
    sonuc: list[str] = []

    def ekle(k: str) -> None:
        if len(bosluksuz(k)) >= EN_KISA_KOK and k not in sonuc:
            sonuc.append(k)
            son = k[-1]
            if son in YUMUSAMA:
                y = k[:-1] + YUMUSAMA[son]
                if y not in sonuc:
                    sonuc.append(y)

    birinci = [s[: -len(e)] for e in EKLER if s.endswith(e) and len(s) > len(e)]
    for k in birinci:
        ekle(k)
    for k in birinci:
        for e in EKLER:
            if k.endswith(e) and len(k) > len(e):
                ekle(k[: -len(e)])
    return sonuc


def anahtarlar(ad: str, ek_kaldir: list[str] | None = None) -> list[str]:
    """Bir cevap/takma ad için tablo anahtarları: normal ve boşluksuz biçim."""
    n = normalize(ad)
    out = [n, bosluksuz(n)]
    for ek in ek_kaldir or []:
        e = normalize(ek)
        for k in list(out):
            if k.endswith(e) and len(k) > len(e) + 1:
                out += [k[: -len(e)].strip(), bosluksuz(k[: -len(e)])]
    sirali: list[str] = []
    for k in out:
        if k and k not in sirali:
            sirali.append(k)
    return sirali


def derle(cevaplar: list[dict], red: list[str], niteleyiciler: list[str] | None = None,
          ek_kaldir: list[str] | None = None, sozluk: set[str] | None = None) -> dict:
    """Sunucunun kullandığı eşleştirme tablosunu üretir.

    cevaplar: [{"ad": str, "takma": [str]}]. Dönen yapı katalogdaki ``eslesme``
    alanıdır; aynı anahtar iki farklı cevaba düşerse -1 (belirsiz) olur.
    """
    tam: dict[str, int] = {}
    kat: dict[str, int] = {}

    def koy(tablo: dict[str, int], k: str, i: int) -> None:
        if k in tablo and tablo[k] != i:
            tablo[k] = -1
        else:
            tablo.setdefault(k, i)

    # Önce asıl adlar, sonra takma adlar: bir takma ad başka bir cevabın asıl adını
    # ezemez (Wikidata altLabel'ları güvenilmez). İki takma ad çakışırsa -1 (belirsiz).
    asil_tam: set[str] = set()
    asil_kat: set[str] = set()
    for i, c in enumerate(cevaplar):
        for k in anahtarlar(c["ad"], ek_kaldir):
            koy(tam, k, i); koy(kat, katla(k), i)
            asil_tam.add(k); asil_kat.add(katla(k))
    for i, c in enumerate(cevaplar):
        for ad in [*c.get("takma", []), *c.get("wd_takma", [])]:
            for k in anahtarlar(ad, ek_kaldir):
                if k not in asil_tam:
                    koy(tam, k, i)
                if katla(k) not in asil_kat:
                    koy(kat, katla(k), i)
    redler: list[str] = []
    for r in red:
        for k in anahtarlar(r):
            if k not in tam and k not in redler:
                redler.append(k)
    engel: list[str] = []
    if sozluk:
        katli_anahtar = {k for k in kat}
        for k, i in kat.items():
            if i < 0 or " " in k:
                continue
            tol = tolerans(len(k))
            if not tol:
                continue
            for w in _komsular(k, tol, sozluk):
                if w not in katli_anahtar and w not in engel:
                    engel.append(w)
    return {
        "tam": tam,
        "kat": kat,
        "red": redler,
        "niteleyici": [normalize(n) for n in niteleyiciler or []],
        "engel": sorted(engel),
    }


def _silmeler(s: str, derinlik: int = 2) -> set[str]:
    out, kat = {s}, {s}
    for _ in range(derinlik):
        kat = {k[:i] + k[i + 1:] for k in kat for i in range(len(k))}
        out |= kat
    return out


_DIZIN: dict[int, dict[str, set[str]]] = {}


def _dizin(sozluk: set[str]) -> dict[str, set[str]]:
    """SymSpell benzeri silme dizini (en çok 2 silme). OSA<=2 olan her çift ortak bir
    silme biçimi paylaşır; adaylar sonra gerçek mesafeyle doğrulanır."""
    anahtar = id(sozluk)
    if anahtar not in _DIZIN:
        d: dict[str, set[str]] = {}
        for w in sozluk:
            if len(w) >= 3 and " " not in w:
                for v in _silmeler(w):
                    d.setdefault(v, set()).add(w)
        _DIZIN.clear()
        _DIZIN[anahtar] = d
    return _DIZIN[anahtar]


def _komsular(k: str, tol: int, sozluk: set[str]) -> list[str]:
    """Katlanmış sözlükte k'ye en çok tol mesafede olan (k'den farklı) kelimeler."""
    d = _dizin(sozluk)
    aday = set()
    for v in _silmeler(k):
        aday |= d.get(v, set())
    aday.discard(k)
    return sorted(w for w in aday if abs(len(w) - len(k)) <= tol and mesafe(w, k, tol) <= tol)


def eslestir(girdi: str, tablo: dict, onceki: list[str] | None = None, yazim: bool = True) -> dict:
    """Tek bir girdiyi sınıflandırır.

    Dönüş: {"tur": kabul|liste_disi|kategori_disi|tekrar|bos, "i": cevap sırası?, "adim": a..e}
    """
    n = normalize(girdi)
    if not bosluksuz(n):
        return {"tur": "bos"}
    if onceki and n in onceki:
        return {"tur": "tekrar"}
    tam, kat, red = tablo["tam"], tablo["kat"], set(tablo["red"])

    def bak(adaylar: list[str], harita: dict[str, int]) -> int | None:
        bulunan = {harita[k] for k in adaylar if k in harita}
        if not bulunan:
            return None
        if len(bulunan) > 1 or -1 in bulunan:
            return -1
        return bulunan.pop()

    def bicimler(s: str) -> list[str]:
        out = [s, bosluksuz(s)]
        for nit in tablo.get("niteleyici", []):
            if s.startswith(nit + " ") and len(s) > len(nit) + 1:
                kalan = s[len(nit) + 1:]
                out += [kalan, bosluksuz(kalan)]
        return out

    temel = bicimler(n)
    # a. tam eşleşme (ad / takma ad / niteleyicisiz)
    r = bak(temel, tam)
    if r is not None:
        return {"tur": "kabul", "i": r, "adim": "a"} if r >= 0 else {"tur": "liste_disi", "belirsiz": True}
    if any(k in red for k in temel):
        return {"tur": "kategori_disi"}
    # b. ek soyma (yalnız soyulmuş biçim tabloda varsa)
    soyulmus = [k for b in temel for k in kokler(b)]
    r = bak(soyulmus, tam)
    if r is not None:
        return {"tur": "kabul", "i": r, "adim": "b"} if r >= 0 else {"tur": "liste_disi", "belirsiz": True}
    if any(k in red for k in soyulmus):
        return {"tur": "kategori_disi"}
    # c. ASCII katlama (tek adaya düşüyorsa)
    katli = [katla(k) for k in temel + soyulmus]
    r = bak(katli, kat)
    if r is not None:
        return {"tur": "kabul", "i": r, "adim": "c"} if r >= 0 else {"tur": "liste_disi", "belirsiz": True}
    if any(k in {katla(x) for x in red} for k in katli):
        return {"tur": "kategori_disi"}
    if not yazim:  # yalnız hattın kopya birleştirmesi için (sunucuda hep açık)
        return {"tur": "liste_disi"}
    # d. yazım hatası toleransı (tek aday, girdi sözlükte başka bir kelime değil)
    g = katla(bosluksuz(n))
    if g in set(tablo.get("engel", [])):
        return {"tur": "liste_disi"}
    hedefler: set[int] = set()
    red_yakin = False
    for k, i in kat.items():
        kk = bosluksuz(k)
        tol = tolerans(len(kk))
        if tol and mesafe(g, kk, tol) <= tol:
            hedefler.add(i)
    for k in red:
        kk = katla(bosluksuz(k))
        tol = tolerans(len(kk))
        if tol and mesafe(g, kk, tol) <= tol:
            red_yakin = True
    if len(hedefler) == 1 and -1 not in hedefler and not red_yakin:
        return {"tur": "kabul", "i": hedefler.pop(), "adim": "d"}
    if not hedefler and red_yakin:
        return {"tur": "kategori_disi"}
    return {"tur": "liste_disi", **({"belirsiz": True} if hedefler else {})}
