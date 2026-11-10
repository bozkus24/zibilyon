"""ortak/normalize_vektorleri.json dosyasını üretir.

Beklenen sonuçlar ELLE yazılmıştır (aşağıdaki BEKLENEN); betik yalnız fikstür
tablolarını Python derleyicisiyle kurar ve beklenenle çelişki varsa durur.
Aynı dosyayı JS testi (tests/eslestir.test.mjs) ve pytest okur.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from zibilyon_veri.normalize import derle, eslestir, normalize, katla

KOK = Path(__file__).resolve().parents[2]
NORMALIZE = [
    ["  Elma  ", "elma"], ["İSTANBUL", "istanbul"], ["IĞDIR", "ığdır"], ["Iğdır", "ığdır"],
    ["Bursa'dan", "bursadan"], ["Bursa’dan", "bursadan"], ["ali-nazik", "ali nazik"],
    ["Hünkâr  Beğendi", "hünkar beğendi"], ["Kâğıt", "kağıt"], ["Gülkurusu!", "gülkurusu"],
    ["Ç,ş.ğ", "ç ş ğ"], ["é", "é"], ["Vişne\tçürüğü", "vişne çürüğü"], ["", ""], ["...", ""],
    ["Âşık", "aşık"], ["ÎMAN", "iman"], ["Ümraniyespor", "ümraniyespor"],
]
TABLOLAR = {
    "meyve": dict(cevaplar=[{"ad": "elma"}, {"ad": "çilek"}, {"ad": "trabzon hurması", "takma": ["cennet elması"]},
                            {"ad": "ağaç kavunu"}, {"ad": "kayısı", "takma": ["zerdali"]}, {"ad": "mandalina"},
                            {"ad": "nar"}, {"ad": "ali nazik"}, {"ad": "kitap"}, {"ad": "kaplan"}, {"ad": "kiraz"}, {"ad": "kira"}],
                  red=["domates", "patlıcan", "biber"], sozluk=["mantar", "elma", "kaptan", "kalem", "mandal"]),
    "kulup": dict(cevaplar=[{"ad": "Galatasaray", "takma": ["GS", "Cimbom"]}, {"ad": "Trabzonspor", "takma": ["TS"]},
                            {"ad": "Adana Demirspor"}, {"ad": "Adanaspor"}, {"ad": "Bursaspor"}], red=[], ek_kaldir=["spor"]),
    "renk": dict(cevaplar=[{"ad": "mavi"}, {"ad": "petrol mavisi"}, {"ad": "yeşil"}], red=["kara"], niteleyiciler=["açık", "koyu"]),
    "belirsiz": dict(cevaplar=[{"ad": "Kara deniz", "takma": ["ege"]}, {"ad": "Ege bölgesi", "takma": ["ege"]}, {"ad": "marmara"}], red=[]),
}
BEKLENEN = {
    "meyve": [["elmalar", "kabul", 0, "b"], ["Elmayı", "kabul", 0, "b"], ["cilek", "kabul", 1, "c"], ["ÇİLEK", "kabul", 1, "a"],
              ["trabzon hurmasi", "kabul", 2, "c"], ["cennet elması", "kabul", 2, "a"], ["Trabzon-Hurması", "kabul", 2, "a"],
              ["agac kavunu", "kabul", 3, "c"], ["ağaçkavunu", "kabul", 3, "a"], ["zerdali", "kabul", 4, "a"],
              ["mandalna", "kabul", 5, "d"], ["mandalinaa", "kabul", 5, "b"], ["mandalnaa", "kabul", 5, "d"], ["mandal", "liste_disi"], ["nur", "liste_disi"],
              ["nar", "kabul", 6, "a"], ["narlar", "kabul", 6, "b"], ["narı", "kabul", 6, "b"], ["domates", "kategori_disi"],
              ["domatesler", "kategori_disi"], ["DOMATES'i", "kategori_disi"], ["ali-nazik", "kabul", 7, "a"], ["alinazik", "kabul", 7, "a"],
              ["Ali Nâzik", "kabul", 7, "a"], ["kitabı", "kabul", 8, "b"], ["kitaplar", "kabul", 8, "b"],
              ["kaplann", "kabul", 9, "d"], ["kaptan", "liste_disi"], ["kirazlar", "kabul", 10, "b"], ["kiraa", "kabul", 11, "b"], ["kirz", "kabul", 10, "d"], ["krz", "liste_disi"],
              ["patlican", "kategori_disi"], ["biberr", "kategori_disi"], ["  elma  ", "kabul", 0, "a"], ["?", "bos"], ["", "bos"],
              ["elmaa", "kabul", 0, "b"], ["armut", "liste_disi"]],
    "kulup": [["gs", "kabul", 0, "a"], ["Cimbom", "kabul", 0, "a"], ["trabzon", "kabul", 1, "a"], ["adana", "kabul", 3, "a"],
              ["adana demir", "kabul", 2, "a"], ["bursa", "kabul", 4, "a"], ["Galatasaray'ı", "kabul", 0, "b"],
              ["galatasray", "kabul", 0, "d"], ["fenerbahçe", "liste_disi"]],
    "renk": [["açık mavi", "kabul", 0, "a"], ["koyu yeşil", "kabul", 2, "a"], ["petrol mavisi", "kabul", 1, "a"],
             ["açık petrol mavisi", "kabul", 1, "a"], ["kara", "kategori_disi"], ["koyu", "liste_disi"]],
    "belirsiz": [["ege", "liste_disi"], ["marmara", "kabul", 2, "a"], ["ege bölgesi", "kabul", 1, "a"]],
}
TEKRAR = [["meyve", ["elma", "Elma"], ["kabul", "tekrar"]], ["meyve", ["armut", "ARMUT"], ["liste_disi", "tekrar"]]]

def main():
    tablolar = {}
    for ad, t in TABLOLAR.items():
        tablolar[ad] = derle(t["cevaplar"], t["red"], t.get("niteleyiciler"), t.get("ek_kaldir"),
                             {katla(normalize(w)) for w in t.get("sozluk", [])})
    hata = []
    for g, b in NORMALIZE:
        if normalize(g) != b: hata.append(("normalize", g, normalize(g), b))
    eslesme = []
    for ad, satirlar in BEKLENEN.items():
        for s in satirlar:
            r = eslestir(s[0], tablolar[ad])
            beklenen = {"tur": s[1], **({"i": s[2], "adim": s[3]} if s[1] == "kabul" else {})}
            gercek = {k: r[k] for k in ("tur", "i", "adim") if k in r}
            if gercek != beklenen: hata.append((ad, s[0], gercek, beklenen))
            eslesme.append({"tablo": ad, "girdi": s[0], "beklenen": beklenen})
    for ad, girdiler, beklenen in TEKRAR:
        onceki, sonuc = [], []
        for g in girdiler:
            sonuc.append(eslestir(g, tablolar[ad], onceki)["tur"]); onceki.append(normalize(g))
        if sonuc != beklenen: hata.append(("tekrar", girdiler, sonuc, beklenen))
    if hata:
        for h in hata: print("UYUŞMAZLIK", h)
        raise SystemExit(1)
    out = {"aciklama": "Zibilyon ortak normalize/eşleştirme vektörleri. Üretici: tools/veri/vektor_uret.py",
           "normalize": NORMALIZE, "tablolar": tablolar, "eslesme": eslesme,
           "tekrar": [{"tablo": a, "girdiler": g, "beklenen": b} for a, g, b in TEKRAR]}
    (KOK / "ortak").mkdir(exist_ok=True)
    (KOK / "ortak/normalize_vektorleri.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print("Vektörler yazıldı:", len(NORMALIZE), "normalize,", len(eslesme), "eşleştirme")

if __name__ == "__main__":
    main()
