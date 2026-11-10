"""LLM koşu yanıtlarını ham/llm/<id>.yanit.<k>.json olarak yazar.
Yanıt metinleri bu betiğin yanındaki .server-private kopyasından okunur; repo içine
cevap yazılmaz. Kullanım: python yaz.py <kosu_dosyasi.py>"""
import json, runpy, sys
from pathlib import Path
KOK = Path(__file__).resolve().parents[3] / ".server-private" / "zibilyon" / "ham" / "llm"
def yaz(sid, kosular):
    for k, metin in enumerate(kosular):
        c = {}
        for satir in metin.strip().split(";"):
            if not satir.strip():
                continue
            ad, v = satir.rsplit("=", 1)
            c[ad.strip()] = float(v)
        top = sum(c.values())
        olcek = 1.0
        if top > 100.0001:
            # Toplamı 100'ü aşan koşu orantılı küçültülür; ham toplam kayda geçer.
            olcek = 100 / top
            c = {a: v * olcek for a, v in c.items()}
            print(f"{sid} koşu {k}: ham toplam {top:.2f} > 100, x{olcek:.4f} ölçeklendi")
            top = 100.0
        (KOK / f"{sid}.yanit.{k}.json").write_text(json.dumps(
            {"kaynak": "llm", "kosu": k, "istem": f"{sid}.istem.{k}.txt", "cevaplar": c, "diger": round(100 - top, 2), "olcek": round(olcek, 6)},
            ensure_ascii=False, indent=1))
        print(sid, k, len(c), "aday, diğer", round(100 - top, 2))
if __name__ == "__main__":
    for f in sys.argv[1:]:
        for sid, kosular in runpy.run_path(f)["YANITLAR"].items():
            yaz(sid, kosular)
