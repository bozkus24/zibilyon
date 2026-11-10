// Çalıştırma: node --test tests/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {randomBytes} from 'node:crypto';
import {seal, unseal} from '../server/crypto.mjs';
import {createService, httpHandler, LIMIT} from '../server/service.mjs';
import {play} from '../server/motor.mjs';

const V = JSON.parse(fs.readFileSync(new URL('../ortak/normalize_vektorleri.json', import.meta.url), 'utf8'));
const key = randomBytes(32);
// Fikstür: ortak vektörlerin "meyve" tablosu (12 cevap) yedi soruda tekrar kullanılır.
const cevaplar = ['elma', 'çilek', 'trabzon hurması', 'ağaç kavunu', 'kayısı', 'mandalina', 'nar', 'ali nazik', 'kitap', 'kaplan', 'kiraz', 'kira']
  .map((ad, i) => ({ad, katman: ['toprak', 'komur', 'demir', 'altin', 'elmas'][i % 5]}));
const soru = (metin, cevher = 4) => ({metin, tip: 'cins', kategori_disi_mesaj: 'Bu bir meyve değil.', cevaplar, eslesme: V.tablolar.meyve, cevher,
  ornekler: {toprak: ['elma'], komur: ['çilek'], demir: ['trabzon hurması'], altin: ['ağaç kavunu'], elmas: ['kayısı']}});
const data = {baslangic: '2026-11-01', gunler: [], sorular: {}};
for (let g = 0; g < 10; g++) { const ids = []; for (let i = 0; i < 7; i++) { const id = `s${g}-${i}`; data.sorular[id] = soru(`GİZLİ SORU ${g}-${i}`); ids.push(id); } data.gunler.push(ids); }
const clock = () => new Date('2026-11-08T09:00:00Z');
const svc = createService({data, key, clock});
const start = (x = {}) => svc({action: 'start', game: 'zibilyon', ...x});
const move = (s, m) => svc({action: 'move', token: s.token, move: m});
const metin = v => JSON.stringify(v);

test('başlangıçta yalnız ilk sorunun metni gelir; hiçbir cevap, gelecek soru metni yok', () => {
  const s = start();
  assert.equal(s.view.no, 8); assert.equal(s.view.aktif, 0);
  assert.equal(s.view.sorular[0].metin, 'GİZLİ SORU 7-0');
  assert.equal(s.view.sorular[1].metin, undefined);
  for (const c of cevaplar) assert.equal(metin(s.view).includes(c.ad), false, c.ad);
  assert.equal(metin(s.view).includes('GİZLİ SORU 7-1'), false);
  assert.equal(s.token.includes('elma'), false);
});

test('liste dışı / kategori dışı / tekrar soruyu bitirmez ve cevap sızdırmaz', () => {
  let s = start();
  s = move(s, {s: 0, t: 'armut'}); assert.equal(s.view.sorular[0].denemeler[0].tur, 'liste_disi');
  s = move(s, {s: 0, t: 'Domatesler'}); assert.equal(s.view.sorular[0].denemeler[1].tur, 'kategori_disi');
  assert.equal(s.view.sorular[0].denemeler[1].mesaj, 'Bu bir meyve değil.');
  s = move(s, {s: 0, t: 'ARMUT'}); assert.equal(s.view.sorular[0].denemeler[2].tur, 'tekrar');
  assert.equal(s.view.sorular[0].durum, 'oyunda'); assert.equal(s.view.aktif, 0);
  for (const c of cevaplar) assert.equal(metin(s.view).includes('"' + c.ad + '"'), false, c.ad);
  assert.equal('aciklama' in s.view.sorular[0], false);
});

test('kabul: ek soyma, ASCII katlama, yazım hatası; açıklama ve puan yalnız bitince', () => {
  let s = start();
  s = move(s, {s: 0, t: 'elmalar'});
  const q = s.view.sorular[0];
  assert.equal(q.durum, 'kabul'); assert.deepEqual(q.cevap, {ad: 'elma', katman: 'toprak', puan: 10, cevher: false});
  assert.equal(q.aciklama.cevher, 'kayısı'); assert.equal(q.aciklama.toplam, 12);
  assert.equal(s.view.aktif, 1); assert.equal(s.view.sorular[1].metin, 'GİZLİ SORU 7-1');
  s = move(s, {s: 1, t: 'cilek'}); assert.equal(s.view.sorular[1].cevap.ad, 'çilek');
  s = move(s, {s: 2, t: 'mandalna'}); assert.equal(s.view.sorular[2].cevap.ad, 'mandalina');
  s = move(s, {s: 3, t: 'zerdali'}); assert.equal(s.view.sorular[3].cevap.cevher, true); assert.equal(s.view.cevher, 1);
  assert.equal(s.view.puan, 10 + 25 + 10 + 100); // mandalina: sıra 5 -> toprak
});

test('belirsiz yazım hatası ve sözlük kelimesi reddedilir', () => {
  let s = start();
  s = move(s, {s: 0, t: 'kaptan'}); assert.equal(s.view.sorular[0].denemeler[0].tur, 'liste_disi');
  s = move(s, {s: 0, t: 'mandal'}); assert.equal(s.view.sorular[0].denemeler[1].tur, 'liste_disi');
});

test('pas / süre doldu 0 puan verir; tam gün sonunda karot ve derinlik', () => {
  let s = start();
  s = move(s, {s: 0, pas: true}); assert.equal(s.view.sorular[0].durum, 'sure'); assert.equal(s.view.sorular[0].cevap, null);
  assert.ok(s.view.sorular[0].aciklama.ornekler);
  for (let i = 1; i < 7; i++) s = move(s, {s: i, t: 'kayısı'});
  assert.equal(s.view.done, true); assert.equal(s.view.puan, 600); assert.equal(s.view.derinlik, 6000);
  assert.deepEqual(s.view.karot, [null, 'elmas', 'elmas', 'elmas', 'elmas', 'elmas', 'elmas']);
  assert.throws(() => move(s, {s: 6, t: 'elma'}), /GAME_FINISHED/);
});

test('geçersiz sıra, bitmiş soruya hamle ve bozuk hamleler reddedilir', () => {
  let s = start();
  for (const m of [{s: 1, t: 'elma'}, {s: 0}, {s: 0, t: ''}, {s: 0, t: '   '}, {s: 0, t: 'x'.repeat(61)}, {s: 0, pas: false}, {s: 0, t: 'elma', pas: true}, {s: 7, t: 'elma'}, 'elma', null, [0, 'elma']])
    assert.throws(() => move(s, m), /INVALID_MOVE|INVALID_REQUEST/, metin(m));
  s = move(s, {s: 0, t: 'elma'});
  assert.throws(() => move(s, {s: 0, t: 'nar'}), /INVALID_MOVE/);
});

test('aynı token + aynı hamle aynı görünüm; ikinci deneme sayılmaz; devam etme', () => {
  const s = start();
  const a = move(s, {s: 0, t: 'armut'}), b = move(s, {s: 0, t: 'armut'});
  assert.deepEqual(a.view, b.view); assert.equal(a.view.attempts, 1);
  assert.deepEqual(svc({action: 'resume', token: a.token}).view, a.view);
  assert.equal(svc({action: 'resume', token: s.token}).view.attempts, 0);
});

test('soru başına 12 deneme: 12. başarısız denemede soru 0 puanla kapanır', () => {
  let s = start();
  for (let i = 0; i < 12; i++) s = move(s, {s: 0, t: 'yanlis' + 'abcdefghijkl'[i]});
  assert.equal(s.view.sorular[0].durum, 'sure'); assert.equal(s.view.sorular[0].mesaj, 'Bu soru için deneme hakkın bitti.');
  assert.equal(s.view.aktif, 1); assert.equal(LIMIT, 84);
});

test('tarih sınırı: yarın açılmaz, başlangıç öncesi yok, arşiv çalışır, oturum değiştirilemez', () => {
  assert.throws(() => start({date: '2026-11-09', mode: 'archive'}), /PUZZLE_UNAVAILABLE/);
  assert.throws(() => start({date: '2026-10-31', mode: 'archive'}), /PUZZLE_UNAVAILABLE/);
  assert.throws(() => start({date: '2026-11-07'}), /INVALID_REQUEST/);       // günlük mod yalnız bugün
  assert.throws(() => start({mode: 'practice'}), /INVALID_REQUEST/);
  assert.equal(start({date: '2026-11-01', mode: 'archive'}).view.no, 1);
  const gece = createService({data, key, clock: () => new Date('2026-11-08T20:59:59Z')});
  assert.equal(gece({action: 'start', game: 'zibilyon'}).view.date, '2026-11-08');
  const yarin = createService({data, key, clock: () => new Date('2026-11-08T21:00:00Z')});
  assert.equal(yarin({action: 'start', game: 'zibilyon'}).view.date, '2026-11-09');
  const t = seal({v: 1, game: 'zibilyon', date: '2026-11-08', mode: 'daily', moves: []}, randomBytes(32));
  assert.throws(() => svc({action: 'resume', token: t}), /INVALID_SESSION/);
  const sahte = unseal(start().token, key); sahte.date = '2026-11-09';
  assert.throws(() => svc({action: 'resume', token: seal(sahte, key)}), /PUZZLE_UNAVAILABLE/);
});

test('HTTP: GET, JSON dışı, yabancı origin, bozuk ve büyük gövde reddedilir; izinli origin geçer', async () => {
  const req = (body, h = {}) => new Request('http://localhost/api/game', {method: 'POST', headers: {'Content-Type': 'application/json', ...h}, body});
  for (const [r, code] of [[new Request('http://localhost/api/game'), 405], [req('{}', {'Content-Type': 'text/plain'}), 415],
    [req('{}', {origin: 'https://evil.example'}), 403], [req('{'), 400], [req('x'.repeat(40000)), 413]])
    assert.equal((await httpHandler(r, svc)).status, code);
  const ok = await httpHandler(req(JSON.stringify({action: 'start', game: 'zibilyon'}), {origin: 'https://trpuzzle-zibilyon.netlify.app'}), svc);
  assert.equal(ok.status, 200); assert.equal(ok.headers.get('cache-control'), 'no-store');
  assert.equal((await httpHandler(req(JSON.stringify({action: 'start', game: 'harfle'})), svc)).status, 400);
});

test('motor doğrudan: başka günün oturumu kendi sorularını kullanır', () => {
  const v = play({date: '2026-11-03', mode: 'archive', moves: []}, data);
  assert.equal(v.sorular[0].metin, 'GİZLİ SORU 2-0');
});
