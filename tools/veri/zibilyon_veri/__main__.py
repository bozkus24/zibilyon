"""Kullanım: python -m zibilyon_veri <komut> [soru-id ...]

Komutlar:
  topla     Aday havuzu (Wikidata + LLM + editör), önbellekli
  istem     3 LLM istem dosyası üretir (ham/llm/<id>.istem.<k>.txt)
  sinyal    S_frek, S_goruntu, S_dil, S_llm, S_anket
  harman    Bileşik puan, katman, override
  rapor     editor/<id>.html + editor/rapor.html
  katalog   cikti/katalog.json (sunucu için; ŞİFRELENMEDEN commit edilmez)
  anket     ham/anket/*.csv içe aktarımı
  kalibre   Anketle ağırlık kalibrasyonu (>= 30 soru)
  takvim    Günlük 7'li setler ve kural ihlalleri
  hepsi     topla+sinyal+harman+rapor+katalog
"""
import argparse, os, sys
from pathlib import Path
from .hat import Hat

def kok() -> Path:
    v = os.environ.get("ZIBILYON_VERI")
    return Path(v) if v else Path(__file__).resolve().parents[3] / ".server-private" / "zibilyon"

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("komut")
    ap.add_argument("idler", nargs="*")
    ap.add_argument("--tazele", action="store_true", help="önbelleği yok say, yeniden indir")
    a = ap.parse_args(argv)
    h = Hat(kok())
    sorular = [s for s in h.sorular() if not a.idler or s["id"] in a.idler]
    k = a.komut
    if k in ("topla", "hepsi"):
        for s in sorular:
            r = h.topla(s, a.tazele); print(f"{s['id']}: {len(r['adaylar'])} aday, {len(r['elenen'])} elenen, {len(r['etiketsiz'])} etiketsiz")
    if k == "istem":
        for s in sorular:
            print(*h.llm_istem(s), sep="\n")
    if k in ("sinyal", "hepsi"):
        for s in sorular:
            r = h.sinyal(s, a.tazele); print(f"{s['id']}: sinyal tamam, LLM koşu {r['llm_kosu']}/3", *r["llm_uyari"])
    if k in ("harman", "hepsi"):
        for s in sorular:
            h.harmanla(s)
    if k in ("rapor", "hepsi"):
        from .rapor import rapor
        print(rapor(h, sorular))
    if k in ("katalog", "hepsi"):
        r = h.katalog(sorular)["rapor"]
        for i, v in r.items(): print(i, v)
    if k == "anket":
        from .anket import ice_aktar
        for s in sorular: print(ice_aktar(h, s))
    if k == "kalibre":
        from .anket import kalibre
        print(kalibre(h, sorular))
    if k == "pv60":
        # 60 günlük toplu görüntülenmeyi önbelleğe alır; verilen sırayla (öncelik) çalışır
        from . import kaynaklar as K
        import json
        sira = a.idler or [s["id"] for s in sorular]
        for sid in sira:
            d = json.loads((h.kok / f"cikti/{sid}.adaylar.json").read_text())
            b = [x["baslik"] for x in d["adaylar"] if x.get("baslik")]
            r = K.goruntulenme_60g(h.kok, b)
            print(sid, f"{len(r)}/{len(b)} makale", flush=True)
    if k == "pv12":
        # 12 aylık REST görüntülenmesini yavaşça önbelleğe alır (hız sınırına uyar)
        from . import kaynaklar as K
        from .hat import PV_BAS, PV_BIT
        import json
        for s in sorular:
            d = json.loads((h.kok / f"cikti/{s['id']}.adaylar.json").read_text())
            for a in d["adaylar"]:
                if a.get("baslik"):
                    K.goruntulenme(h.kok, a["baslik"], PV_BAS, PV_BIT)
            print(s["id"], "12 ay tamam", flush=True)
    if k == "takvim":
        from .takvim import takvim
        print(takvim(h, sorular))

if __name__ == "__main__":
    main()
