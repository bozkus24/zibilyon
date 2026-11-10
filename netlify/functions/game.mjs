// Zibilyon cevap servisi (/api/game). Anahtar yoksa ya da katalog çözülemezse
// kapalı başarısız olur (503); istemciye asla yedek cevap verisi gönderilmez.
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {serverKey, decryptCatalog} from '../../server/crypto.mjs';
import {createService, httpHandler} from '../../server/service.mjs';
let service;
export default async function handler(request) {
  try {
    if (!service) {
      const key = serverKey();
      const data = decryptCatalog(readFileSync(join(process.cwd(), 'server/catalog.enc')), key);
      service = createService({data, key});
    }
    return await httpHandler(request, service);
  } catch { return Response.json({error: 'SERVICE_UNAVAILABLE'}, {status: 503, headers: {'Cache-Control': 'no-store'}}); }
}
export const config = {path: '/api/game', rateLimit: {windowLimit: 120, windowSize: 60, aggregateBy: ['ip', 'domain']}};
