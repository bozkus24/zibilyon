// Zibilyon cevap normalizasyonu ve eşleştirme (sunucu, JS).
// tools/veri/zibilyon_veri/normalize.py ile birebir aynı kurallar; ikisi de
// ortak/normalize_vektorleri.json ile test edilir. Biri değişirse diğeri de değişmeli.
const KESME = new Set(["'", '’', '‘', '`', '´', 'ʼ']);
const SAPKA = {'â': 'a', 'î': 'i', 'û': 'u'};
const KATLA = {'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u'};
const EKLER = [...new Set(['lar', 'ler', 'ı', 'i', 'u', 'ü', 'yı', 'yi', 'yu', 'yü', 'sı', 'si', 'su', 'sü',
  'a', 'e', 'ya', 'ye', 'da', 'de', 'ta', 'te', 'dan', 'den', 'tan', 'ten',
  'ın', 'in', 'un', 'ün', 'nın', 'nin', 'nun', 'nün'])]
  .sort((a, b) => b.length - a.length || (a < b ? -1 : a > b ? 1 : 0));
const YUMUSAMA = {b: 'p', c: 'ç', d: 't', 'ğ': 'k', g: 'k'};
const EN_KISA_KOK = 2;
const HARF = /[\p{L}\p{N}]/u;

export function normalize(metin) {
  let s = String(metin).normalize('NFC').toLocaleLowerCase('tr-TR').normalize('NFC');
  let out = '';
  for (const ch of s) {
    const c = SAPKA[ch] || ch;
    if (KESME.has(c)) continue;
    out += HARF.test(c) || c === ' ' ? c : ' ';
  }
  return out.replace(/\s+/g, ' ').trim();
}
export const bosluksuz = s => s.replace(/ /g, '');
export const katla = s => [...s].map(c => KATLA[c] || c).join('');
export const tolerans = n => n <= 4 ? 0 : n <= 7 ? 1 : 2;

/** Damerau-Levenshtein (optimal string alignment). */
export function mesafe(a, b, sinir = 99) {
  a = [...a]; b = [...b];
  if (Math.abs(a.length - b.length) > sinir) return sinir + 1;
  let onceki2 = null, onceki = Array.from({length: b.length + 1}, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const simdi = [i, ...Array(b.length).fill(0)];
    for (let j = 1; j <= b.length; j++) {
      const m = a[i - 1] === b[j - 1] ? 0 : 1;
      simdi[j] = Math.min(onceki[j] + 1, simdi[j - 1] + 1, onceki[j - 1] + m);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) simdi[j] = Math.min(simdi[j], onceki2[j - 2] + 1);
    }
    onceki2 = onceki; onceki = simdi;
  }
  return onceki[b.length];
}

export function kokler(s) {
  const sonuc = [];
  const ekle = k => {
    if ([...bosluksuz(k)].length >= EN_KISA_KOK && !sonuc.includes(k)) {
      sonuc.push(k);
      const son = k.slice(-1);
      if (YUMUSAMA[son]) { const y = k.slice(0, -1) + YUMUSAMA[son]; if (!sonuc.includes(y)) sonuc.push(y); }
    }
  };
  const birinci = EKLER.filter(e => s.endsWith(e) && s.length > e.length).map(e => s.slice(0, -e.length));
  for (const k of birinci) ekle(k);
  for (const k of birinci) for (const e of EKLER) if (k.endsWith(e) && k.length > e.length) ekle(k.slice(0, -e.length));
  return sonuc;
}

/**
 * Bir girdiyi sınıflandırır. tablo: katalogdaki derlenmiş {tam, kat, red, niteleyici, engel}.
 * Dönüş: {tur: kabul|liste_disi|kategori_disi|tekrar|bos, i?, adim?, belirsiz?}
 */
export function eslestir(girdi, tablo, onceki = []) {
  const n = normalize(girdi);
  if (!bosluksuz(n)) return {tur: 'bos'};
  if (onceki.includes(n)) return {tur: 'tekrar'};
  const {tam, kat} = tablo, red = new Set(tablo.red), has = (o, k) => Object.hasOwn(o, k);
  const bak = (adaylar, harita) => {
    const b = new Set(adaylar.filter(k => has(harita, k)).map(k => harita[k]));
    if (!b.size) return null;
    if (b.size > 1 || b.has(-1)) return -1;
    return [...b][0];
  };
  const sonuc = (r, adim) => r >= 0 ? {tur: 'kabul', i: r, adim} : {tur: 'liste_disi', belirsiz: true};
  const bicimler = s => {
    const out = [s, bosluksuz(s)];
    for (const nit of tablo.niteleyici || []) if (s.startsWith(nit + ' ') && s.length > nit.length + 1) { const k = s.slice(nit.length + 1); out.push(k, bosluksuz(k)); }
    return out;
  };
  const temel = bicimler(n);
  let r = bak(temel, tam);
  if (r !== null) return sonuc(r, 'a');
  if (temel.some(k => red.has(k))) return {tur: 'kategori_disi'};
  const soyulmus = temel.flatMap(kokler);
  r = bak(soyulmus, tam);
  if (r !== null) return sonuc(r, 'b');
  if (soyulmus.some(k => red.has(k))) return {tur: 'kategori_disi'};
  const katli = [...temel, ...soyulmus].map(katla), redKatli = new Set([...red].map(katla));
  r = bak(katli, kat);
  if (r !== null) return sonuc(r, 'c');
  if (katli.some(k => redKatli.has(k))) return {tur: 'kategori_disi'};
  const g = katla(bosluksuz(n));
  if ((tablo.engel || []).includes(g)) return {tur: 'liste_disi'};
  const hedefler = new Set();
  let redYakin = false;
  for (const [k, i] of Object.entries(kat)) { const kk = bosluksuz(k), t = tolerans([...kk].length); if (t && mesafe(g, kk, t) <= t) hedefler.add(i); }
  for (const k of red) { const kk = katla(bosluksuz(k)), t = tolerans([...kk].length); if (t && mesafe(g, kk, t) <= t) redYakin = true; }
  if (hedefler.size === 1 && !hedefler.has(-1) && !redYakin) return {tur: 'kabul', i: [...hedefler][0], adim: 'd'};
  if (!hedefler.size && redYakin) return {tur: 'kategori_disi'};
  return hedefler.size ? {tur: 'liste_disi', belirsiz: true} : {tur: 'liste_disi'};
}
