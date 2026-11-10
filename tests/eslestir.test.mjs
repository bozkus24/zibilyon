// Çalıştırma: node --test tests/
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {normalize, eslestir} from '../server/eslestir.mjs';
const V = JSON.parse(fs.readFileSync(new URL('../ortak/normalize_vektorleri.json', import.meta.url), 'utf8'));
test('normalize: ortak vektörler Python ile aynı', () => {
  for (const [g, b] of V.normalize) assert.equal(normalize(g), b, JSON.stringify(g));
});
test('eşleştirme: ortak vektörler Python ile aynı (tam, ek, katlama, yazım, red, belirsiz)', () => {
  for (const s of V.eslesme) {
    const r = eslestir(s.girdi, V.tablolar[s.tablo]);
    const gercek = Object.fromEntries(['tur', 'i', 'adim'].filter(k => k in r).map(k => [k, r[k]]));
    assert.deepEqual(gercek, s.beklenen, s.tablo + ': ' + s.girdi);
  }
});
test('tekrar: aynı girdi ikinci kez sayılmaz', () => {
  for (const s of V.tekrar) {
    const onceki = [], sonuc = [];
    for (const g of s.girdiler) { sonuc.push(eslestir(g, V.tablolar[s.tablo], onceki).tur); onceki.push(normalize(g)); }
    assert.deepEqual(sonuc, s.beklenen);
  }
});
