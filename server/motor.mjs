// Zibilyon sunucu motoru. Tüm cevap verisi bu modülde kalır; istemciye yalnız
// dönen görünüm (view) gider. Bitmemiş ya da henüz açılmamış soruların cevapları
// ve gelecek soruların metinleri ASLA görünüme girmez.
import {eslestir, normalize} from './eslestir.mjs';

export const SORU_SAYISI = 7;
export const SORU_BASI_DENEME = 12;
export const KATMANLAR = ['toprak', 'komur', 'demir', 'altin', 'elmas'];
export const PUAN = {toprak: 10, komur: 25, demir: 50, altin: 75, elmas: 100};
const MESAJ = {
  liste_disi: 'Bunu bilemedik, başka dene.',
  tekrar: 'Bunu zaten denedin.',
  hak_bitti: 'Bu soru için deneme hakkın bitti.',
};
const gun = s => Date.parse(s + 'T00:00:00Z') / 864e5;
const hata = (kod = 'INVALID_MOVE') => { throw new Error(kod); };

export function gunlukSorular(data, date) {
  const n = gun(date) - gun(data.baslangic);
  const g = data.gunler[n];
  if (!Array.isArray(g) || g.length !== SORU_SAYISI || !g.every(id => data.sorular[id])) hata('PUZZLE_UNAVAILABLE');
  return {no: n + 1, idler: g};
}

function hamleGecerli(m) {
  if (!m || typeof m !== 'object' || Array.isArray(m) || !Number.isInteger(m.s) || m.s < 0 || m.s >= SORU_SAYISI) return false;
  const anahtar = Object.keys(m).sort().join(',');
  if (anahtar === 'pas,s') return m.pas === true;
  if (anahtar === 's,t') return typeof m.t === 'string' && m.t.length >= 1 && m.t.length <= 60;
  return false;
}

/** Oturumu baştan oynatıp görünümü üretir. Geçersiz hamle INVALID_MOVE fırlatır. */
export function play(session, data) {
  const {date, mode, moves} = session;
  const {no, idler} = gunlukSorular(data, date);
  const durum = idler.map(() => ({denemeler: [], onceki: [], bitti: false, kabul: null}));
  let aktif = 0;
  for (const m of moves) {
    if (!hamleGecerli(m) || aktif >= SORU_SAYISI || m.s !== aktif) hata();
    const d = durum[aktif], soru = data.sorular[idler[aktif]];
    if (m.pas) { d.bitti = true; d.sonuc = 'sure'; aktif++; continue; }
    const r = eslestir(m.t, soru.eslesme, d.onceki);
    if (r.tur === 'bos') hata();
    const n = normalize(m.t);
    const kayit = {t: m.t.trim().slice(0, 60), tur: r.tur};
    if (r.tur === 'kategori_disi') kayit.mesaj = soru.kategori_disi_mesaj;
    else if (MESAJ[r.tur]) kayit.mesaj = MESAJ[r.tur];
    d.denemeler.push(kayit);
    if (r.tur !== 'tekrar') d.onceki.push(n);
    if (r.tur === 'kabul') {
      d.bitti = true; d.sonuc = 'kabul'; d.kabul = r.i; aktif++;
    } else if (d.denemeler.length >= SORU_BASI_DENEME) {
      d.bitti = true; d.sonuc = 'sure'; d.hakBitti = true; aktif++;
    }
  }
  let puan = 0, cevher = 0, enDerin = null;
  const sorular = idler.map((id, i) => {
    const soru = data.sorular[id], d = durum[i];
    const durumAdi = d.bitti ? d.sonuc : i === aktif ? 'oyunda' : 'bekliyor';
    const g = {s: i, durum: durumAdi};
    if (durumAdi === 'bekliyor') return g;           // gelecek sorunun metni bile gitmez
    g.metin = soru.metin;
    g.denemeler = d.denemeler;
    if (d.hakBitti) g.mesaj = MESAJ.hak_bitti;
    if (!d.bitti) return g;                           // oynanan sorunun cevapları gitmez
    if (d.kabul !== null) {
      const c = soru.cevaplar[d.kabul];
      g.cevap = {ad: c.ad, katman: c.katman, puan: PUAN[c.katman], cevher: d.kabul === soru.cevher};
      puan += PUAN[c.katman];
      if (g.cevap.cevher) cevher++;
      if (!enDerin || PUAN[c.katman] > PUAN[enDerin.katman]) enDerin = {s: i, ad: c.ad, katman: c.katman};
    } else g.cevap = null;
    g.aciklama = {
      cevher: soru.cevher === null || soru.cevher === undefined ? null : soru.cevaplar[soru.cevher].ad,
      ornekler: soru.ornekler,
      toplam: soru.cevaplar.length,
    };
    return g;
  });
  const done = aktif >= SORU_SAYISI;
  return {game: 'zibilyon', date, mode, no, done, win: done, attempts: moves.length, aktif: done ? null : aktif,
    sorular, puan, derinlik: puan * 10, cevher, enDerin, karot: done ? sorular.map(x => x.cevap ? x.cevap.katman : null) : null};
}
