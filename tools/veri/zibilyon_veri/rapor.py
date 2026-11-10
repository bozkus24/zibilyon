"""Editör inceleme aracı: editor/<id>.html (yerel, statik) + editor/<id>.csv + editor/rapor.html.

Sayfalar yalnız yerelde açılır; dış kaynak yüklemez. İçerik düz cevap içerdiğinden
.server-private altında kalır ve hiçbir zaman commit edilmez.
"""
from __future__ import annotations

import csv
import html
import json
from collections import Counter

from .hat import KATMAN_AD, KATMANLAR

STIL = """body{font:14px/1.45 system-ui,sans-serif;margin:24px;color:#1d1f24;background:#faf8f4}
table{border-collapse:collapse;width:100%;font-size:12.5px}th,td{border-bottom:1px solid #ddd;padding:4px 6px;text-align:left;vertical-align:top}
th{background:#efe9df;position:sticky;top:0}tr.elmas{background:#eef6ff}tr.altin{background:#fff8e1}.u{color:#a34;font-size:11.5px}
.h{display:flex;gap:6px;align-items:flex-end;height:90px;margin:8px 0 16px}.h div{background:#8a6d3b;width:46px;color:#fff;font-size:11px;text-align:center}
.k{display:inline-block;padding:1px 6px;border-radius:4px;background:#ddd}code{background:#eee;padding:0 3px}"""


def _e(x) -> str:
    return html.escape("" if x is None else str(x))


def soru_sayfasi(h, s: dict) -> tuple[str, dict]:
    veri = json.loads((h.kok / f"cikti/{s['id']}.json").read_text())
    havuz = json.loads((h.kok / f"cikti/{s['id']}.adaylar.json").read_text())
    ad = sorted(veri["adaylar"], key=lambda a: (a["sira"] or 10 ** 6, a["n"]))
    say = Counter(a["katman"] for a in ad if a["katman"])
    uyari = Counter(u for a in ad for u in a["uyarilar"])
    en = max(say.values() or [1])
    hist = "".join(f'<div style="height:{20 + 70 * say.get(t, 0) / en:.0f}px">{KATMAN_AD[t]}<br>{say.get(t, 0)}</div>' for t in KATMANLAR)
    satir = []
    for a in ad:
        sg, yz = a["sinyal"], a["yuzdelik"]
        f = lambda k, d=2: (f"{sg[k]:.{d}f}" if k in sg else "—") + (f" <small>({yz[k]:.2f})</small>" if k in yz else "")
        pv = a.get("pv") or {}
        satir.append(
            f'<tr class="{_e(a["katman"])}"><td>{_e(a["sira"])}</td><td><b>{_e(a["ad"])}</b><br><small>{_e(", ".join(a.get("takma", [])))}</small></td>'
            f'<td>{_e("+".join(a["kaynak"]))}<br><small>{_e(a.get("qid"))} {_e(a.get("baslik"))}</small></td>'
            f'<td>{f("frek")}</td><td>{f("goruntu")}<br><small>ort {pv.get("ortalama", 0):.0f} / med {pv.get("medyan", 0):.0f}</small></td>'
            f'<td>{f("dil", 0)}</td><td>{f("llm")}<br><small>{_e(a.get("llm_kosular"))}</small></td>'
            f'<td>{_e(a["bilesik"])}</td><td><span class="k">{_e(KATMAN_AD.get(a["katman"], "—"))}</span></td>'
            f'<td class="u">{_e(", ".join(a["uyarilar"]))}</td></tr>')
    elenen = Counter(e["neden"] for e in havuz["elenen"])
    sayfa = f"""<!doctype html><meta charset="utf-8"><title>{_e(s['id'])} editör</title><style>{STIL}</style>
<h1>{_e(s['metin'])} <small>({_e(s['id'])}, {_e(s['tip'])})</small></h1>
<p>{_e(s.get('kapsam_notu'))}</p>
<p>Aday: <b>{len(ad)}</b> · Katman yöntemi: <code>{_e(veri.get('katman_yontemi'))}</code> · Ağırlıklar: <code>{_e(veri['agirlik'])}</code>
 · Görüntülenme kaynağı: <code>{_e(veri.get('goruntu_kaynagi'))}</code> · LLM koşu: {veri.get('llm_kosu')}/3
 · Spearman(S_llm, veri sinyalleri) = <b>{'—' if veri['spearman_llm_veri'] is None else f"{veri['spearman_llm_veri']:.3f}"}</b> (n={veri['spearman_n']})</p>
<div class="h">{hist}</div>
<p>Uyarılar: {_e(dict(uyari))}</p>
<p>Elenen: {_e(dict(elenen))} · Birleşen kopya: {len(havuz['birlesen'])} · Etiketsiz: {len(havuz['etiketsiz'])}</p>
<p>Override: <code>editor/override.csv</code> → <code>id,cevap,katman,gerekce</code>; katman = toprak|komur|demir|altin|elmas|onay|sil|birlestir:&lt;hedef cevap&gt;.
Elmas yalnız editör onayıyla yayına girer (onaysızlar Altın'da tavanlanır).</p>
<table><tr><th>#</th><th>Cevap / takma</th><th>Kaynak</th><th>S_frek (yzd)</th><th>S_goruntu</th><th>S_dil</th><th>S_llm [koşular]</th><th>Bileşik</th><th>Katman</th><th>Uyarı</th></tr>
{''.join(satir)}</table>
<h2>Elenenler</h2><table><tr><th>Ad</th><th>Neden</th><th>QID</th></tr>
{''.join(f"<tr><td>{_e(e['ad'])}</td><td>{_e(e['neden'])}</td><td>{_e(e.get('qid'))}</td></tr>" for e in havuz['elenen'])}</table>
<h2>Birleşen kopyalar</h2><p>{_e('; '.join(f"{b['ad']} → {b['hedef']}" for b in havuz['birlesen']))}</p>
<h2>Etiketsiz (Türkçe etiketi yok)</h2><p>{_e(', '.join(f"{e['qid']} {e.get('baslik') or ''}" for e in havuz['etiketsiz']))}</p>"""
    (h.kok / "editor" / f"{s['id']}.html").write_text(sayfa)
    with (h.kok / "editor" / f"{s['id']}.csv").open("w", newline="") as fp:
        w = csv.writer(fp)
        w.writerow(["sira", "cevap", "takma", "kaynak", "qid", "frek", "goruntu", "dil", "llm", "bilesik", "katman", "uyarilar"])
        for a in ad:
            sg = a["sinyal"]
            w.writerow([a["sira"], a["ad"], "|".join(a.get("takma", [])), "+".join(a["kaynak"]), a.get("qid"),
                        sg.get("frek"), sg.get("goruntu"), sg.get("dil"), sg.get("llm"), a["bilesik"], a["katman"], "|".join(a["uyarilar"])])
    ozet = {"id": s["id"], "metin": s["metin"], "tip": s["tip"], "aday": len(ad), "katman": {t: say.get(t, 0) for t in KATMANLAR},
            "spearman": veri["spearman_llm_veri"], "spearman_n": veri["spearman_n"], "uyari": dict(uyari),
            "elenen": dict(elenen), "birlesen": len(havuz["birlesen"]), "goruntu_kaynagi": veri.get("goruntu_kaynagi"),
            "ilk": [a["ad"] for a in ad[:8]],
            "elmas_ornek": [a["ad"] for a in ad if a["katman"] == "elmas"][:10],
            "ek_a_cevher": (h._json(f"ham/llm/{s['id']}.ek_a.json", {}) or {}).get("cevher_oneri")}
    return sayfa, ozet


def rapor(h, sorular: list[dict]) -> str:
    ozetler = [soru_sayfasi(h, s)[1] for s in sorular]
    satir = "".join(
        f"<tr><td><a href='{_e(o['id'])}.html'>{_e(o['id'])}</a></td><td>{_e(o['metin'])}</td><td>{_e(o['tip'])}</td><td>{o['aday']}</td>"
        + "".join(f"<td>{o['katman'][t]}</td>" for t in KATMANLAR)
        + f"<td>{'—' if o['spearman'] is None else f'{o['spearman']:.3f}'}</td><td><small>{_e(o['goruntu_kaynagi'])}</small></td></tr>"
        for o in ozetler)
    sayfa = f"""<!doctype html><meta charset="utf-8"><title>Zibilyon pilot raporu</title><style>{STIL}</style>
<h1>Zibilyon pilot raporu</h1><table><tr><th>ID</th><th>Soru</th><th>Tip</th><th>Aday</th>
{''.join(f'<th>{KATMAN_AD[t]}</th>' for t in KATMANLAR)}<th>Spearman LLM↔veri</th><th>Görüntülenme</th></tr>{satir}</table>"""
    (h.kok / "editor" / "rapor.html").write_text(sayfa)
    (h.kok / "cikti" / "pilot_ozet.json").write_text(json.dumps(ozetler, ensure_ascii=False, indent=1))
    return f"Rapor: {h.kok / 'editor' / 'rapor.html'} ({len(ozetler)} soru)"
