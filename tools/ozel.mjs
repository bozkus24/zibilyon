// .server-private/ klasörünün şifreli yedeği (yedek/ozel.enc), repoda yalnız şifreli durur.
//   node tools/ozel.mjs yedekle  -> .server-private/ -> tar.gz -> AES-256-GCM -> yedek/ozel.enc
//   node tools/ozel.mjs ac       -> yedek/ozel.enc -> .server-private/ (var olan klasörün üzerine yazmaz)
// Anahtar: .env içindeki TRPUZZLE_SERVER_KEY'den HKDF ile türetilir (amaç: "yedek").
// Anahtar kaybolursa yedek açılamaz; .env'i güvenli bir yerde saklayın.
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {createCipheriv, createDecipheriv, hkdfSync, randomBytes} from 'node:crypto';
import {serverKey} from '../server/crypto.mjs';

const root = path.resolve(import.meta.dirname, '..');
const envFile = path.join(root, '.env'), ozel = path.join(root, '.server-private'), hedef = path.join(root, 'yedek/ozel.enc');
const AAD = Buffer.from('zibilyon-ozel-yedek-v1');
const anahtar = () => {
  const hex = fs.existsSync(envFile) ? fs.readFileSync(envFile, 'utf8').match(/^TRPUZZLE_SERVER_KEY=(.*)$/m)?.[1] : process.env.TRPUZZLE_SERVER_KEY;
  return Buffer.from(hkdfSync('sha256', serverKey(hex), 'zibilyon-yedek', 'yedek', 32));
};
const islem = process.argv[2];
if (islem === 'yedekle') {
  // Python sanal ortamı ve önbellek dosyaları yedeğe girmez; içerik deterministik sıralanır.
  const tar = execFileSync('tar', ['--sort=name', '--exclude=__pycache__', '-czf', '-', '-C', root, '.server-private'], {maxBuffer: 1 << 30});
  const iv = randomBytes(12), c = createCipheriv('aes-256-gcm', anahtar(), iv); c.setAAD(AAD);
  const govde = Buffer.concat([c.update(tar), c.final()]);
  fs.mkdirSync(path.dirname(hedef), {recursive: true});
  fs.writeFileSync(hedef, Buffer.concat([iv, c.getAuthTag(), govde]));
  console.log(`Şifreli yedek yazıldı: yedek/ozel.enc (${(fs.statSync(hedef).size / 1048576).toFixed(1)} MB).`);
} else if (islem === 'ac') {
  if (fs.existsSync(ozel)) { console.error('.server-private zaten var; üzerine yazılmadı. Önce taşıyın ya da silin.'); process.exit(1); }
  const b = fs.readFileSync(hedef), d = createDecipheriv('aes-256-gcm', anahtar(), b.subarray(0, 12));
  d.setAAD(AAD); d.setAuthTag(b.subarray(12, 28));
  const tar = Buffer.concat([d.update(b.subarray(28)), d.final()]);
  execFileSync('tar', ['-xzf', '-', '-C', root], {input: tar});
  console.log('.server-private geri yüklendi.');
} else { console.error('Kullanım: node tools/ozel.mjs yedekle|ac'); process.exit(2); }
