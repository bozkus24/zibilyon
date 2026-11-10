// Zibilyon şifreli katalog bakımı (trpuzzlemain/tools/catalog.mjs deseni).
//   node tools/catalog.mjs anahtar   -> .env içinde TRPUZZLE_SERVER_KEY yoksa üretir (0600)
//   node tools/catalog.mjs encrypt   -> .server-private/zibilyon/cikti/{katalog,takvim}.json -> server/catalog.enc
//   node tools/catalog.mjs dogrula   -> server/catalog.enc çözülür, yapı denetlenir (düz metin yazılmaz)
// Düz metin cevaplar YALNIZ .server-private altında durur; dist'e ve repoya girmez.
import {gzipSync} from 'node:zlib';
import fs from 'node:fs';
import path from 'node:path';
import {randomBytes, createCipheriv} from 'node:crypto';
import {serverKey, decryptCatalog} from '../server/crypto.mjs';
import {SORU_SAYISI, KATMANLAR} from '../server/motor.mjs';

const root = path.resolve(import.meta.dirname, '..'), envFile = path.join(root, '.env');
const enc = path.join(root, 'server/catalog.enc'), ozel = path.join(root, '.server-private/zibilyon/cikti');
const action = process.argv[2];
const anahtarOku = () => serverKey(fs.existsSync(envFile) ? fs.readFileSync(envFile, 'utf8').match(/^TRPUZZLE_SERVER_KEY=(.*)$/m)?.[1] : process.env.TRPUZZLE_SERVER_KEY);

export function denetle(data) {
  const hata = [];
  if (!/^\d{4}-\d{2}-\d{2}$/.test(data.baslangic || '')) hata.push('baslangic yok');
  for (const [i, g] of (data.gunler || []).entries()) {
    if (!Array.isArray(g) || g.length !== SORU_SAYISI) hata.push(`gün ${i + 1}: ${SORU_SAYISI} soru değil`);
    else for (const id of g) if (!data.sorular[id]) hata.push(`gün ${i + 1}: ${id} katalogda yok`);
  }
  for (const [id, s] of Object.entries(data.sorular || {})) {
    if (!s.metin || !Array.isArray(s.cevaplar) || !s.cevaplar.length || !s.eslesme?.tam) { hata.push(`${id}: eksik alan`); continue; }
    if (s.cevaplar.some(c => !KATMANLAR.includes(c.katman))) hata.push(`${id}: geçersiz katman`);
    for (const t of KATMANLAR) if (s.cevaplar.filter(c => c.katman === t).length < 2 && t !== 'elmas') hata.push(`${id}: ${t} katmanında 2'den az cevap`);
  }
  return hata;
}

if (action === 'anahtar') {
  if (fs.existsSync(envFile) && /^TRPUZZLE_SERVER_KEY=/m.test(fs.readFileSync(envFile, 'utf8'))) { console.log('.env zaten anahtar içeriyor; değiştirilmedi.'); process.exit(0); }
  fs.appendFileSync(envFile, 'TRPUZZLE_SERVER_KEY=' + randomBytes(32).toString('hex') + '\n', {mode: 0o600});
  fs.chmodSync(envFile, 0o600);
  console.log('Yeni anahtar .env dosyasına yazıldı (git dışı). Güvenli bir yere yedekleyin; kaybolursa katalog çözülemez.');
} else if (action === 'encrypt') {
  const key = anahtarOku();
  const kat = JSON.parse(fs.readFileSync(path.join(ozel, 'katalog.json'), 'utf8'));
  const tak = JSON.parse(fs.readFileSync(path.join(ozel, 'takvim.json'), 'utf8'));
  const data = {surum: 1, baslangic: tak.baslangic, gunler: tak.gunler.map(g => g.sorular), sorular: kat.sorular};
  const hata = denetle(data);
  if (hata.length) { console.error('Katalog geçersiz:\n' + hata.join('\n')); process.exit(1); }
  const iv = randomBytes(12), c = createCipheriv('aes-256-gcm', key, iv); c.setAAD(Buffer.from('trpuzzle-catalog-v1'));
  const body = Buffer.concat([c.update(gzipSync(JSON.stringify(data))), c.final()]);
  fs.writeFileSync(enc, Buffer.concat([iv, c.getAuthTag(), body]));
  console.log(`Şifreli katalog yazıldı: ${Object.keys(data.sorular).length} soru, ${data.gunler.length} gün. Yayın yapılmadı.`);
} else if (action === 'dogrula') {
  const data = decryptCatalog(fs.readFileSync(enc), anahtarOku());
  const hata = denetle(data);
  console.log(hata.length ? 'Sorunlar:\n' + hata.join('\n') : `Geçerli: ${Object.keys(data.sorular).length} soru, ${data.gunler.length} gün, başlangıç ${data.baslangic}.`);
  process.exit(hata.length ? 1 : 0);
} else if (import.meta.url === `file://${process.argv[1]}`) {
  console.error('Kullanım: node tools/catalog.mjs anahtar|encrypt|dogrula'); process.exit(2);
}
