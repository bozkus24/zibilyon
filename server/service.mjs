// trpuzzlemain/server/service.mjs desenini izler: durumsuz, şifreli token; aynı
// token + aynı hamle aynı görünümü verir ve ikinci bir deneme saymaz.
import {randomUUID} from 'node:crypto';
import {seal, unseal} from './crypto.mjs';
import {play, SORU_SAYISI, SORU_BASI_DENEME} from './motor.mjs';

export const LIMIT = SORU_SAYISI * SORU_BASI_DENEME; // 84: oturum başına en çok hamle
export const IZINLI_ORIGIN = new Set(['https://trpuzzle.com', 'https://www.trpuzzle.com', 'https://trpuzzle-zibilyon.netlify.app']);
const dateKey = d => new Date(d.getTime() + 10800000).toISOString().slice(0, 10); // Europe/Istanbul (UTC+3)
function validDate(s) { return typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && Number.isFinite(Date.parse(s)) && new Date(s).toISOString().slice(0, 10) === s; }
function ensure(c, code = 'INVALID_REQUEST') { if (!c) throw new Error(code); }

export function createService({data, key, clock = () => new Date()}) {
  ensure(data && validDate(data.baslangic) && Array.isArray(data.gunler) && data.sorular, 'SERVER_NOT_CONFIGURED');
  function validateSession(s) {
    ensure(s && s.v === 1 && s.game === 'zibilyon' && ['daily', 'archive'].includes(s.mode) && validDate(s.date), 'INVALID_SESSION');
    ensure(s.date >= data.baslangic && s.date <= dateKey(clock()), 'PUZZLE_UNAVAILABLE');
    ensure(Array.isArray(s.moves) && s.moves.length <= LIMIT, 'INVALID_SESSION');
  }
  return function handle(body) {
    ensure(body && typeof body === 'object' && !Array.isArray(body));
    let session;
    if (body.action === 'start') {
      ensure(body.game === 'zibilyon', 'INVALID_GAME');
      const mode = body.mode || 'daily', date = body.date || dateKey(clock());
      ensure(['daily', 'archive'].includes(mode));          // pratik modu ilk sürümde yok
      ensure(mode !== 'daily' || date === dateKey(clock()));
      session = {v: 1, id: randomUUID(), game: 'zibilyon', date, mode, moves: []};
      validateSession(session);
    } else if (body.action === 'resume' || body.action === 'move') {
      session = unseal(body.token, key); validateSession(session);
      if (body.action === 'move') {
        ensure(session.moves.length < LIMIT, 'GAME_FINISHED');
        ensure(!play(session, data).done, 'GAME_FINISHED');
        ensure(body.move !== undefined);
        session.moves.push(body.move);
      }
    } else throw new Error('INVALID_REQUEST');
    return {token: seal(session, key), view: play(session, data)};
  };
}

export async function httpHandler(request, service) {
  const headers = {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Vary': 'Origin'};
  const out = (body, status = 200) => new Response(JSON.stringify(body), {status, headers});
  if (request.method !== 'POST') return out({error: 'METHOD_NOT_ALLOWED'}, 405);
  const url = new URL(request.url), origin = request.headers.get('origin');
  if (origin && origin !== url.origin && !IZINLI_ORIGIN.has(origin)) return out({error: 'ORIGIN_NOT_ALLOWED'}, 403);
  if (request.headers.get('sec-fetch-site') === 'cross-site' && !IZINLI_ORIGIN.has(origin)) return out({error: 'ORIGIN_NOT_ALLOWED'}, 403);
  if (!/^application\/json(?:;|$)/i.test(request.headers.get('content-type') || '')) return out({error: 'JSON_REQUIRED'}, 415);
  if (Number(request.headers.get('content-length') || 0) > 32768) return out({error: 'REQUEST_TOO_LARGE'}, 413);
  try {
    const reader = request.body?.getReader(); if (!reader) return out({error: 'INVALID_REQUEST'}, 400);
    const chunks = []; let total = 0;
    for (;;) { const {done, value} = await reader.read(); if (done) break; total += value.length; if (total > 32768) { await reader.cancel(); return out({error: 'REQUEST_TOO_LARGE'}, 413); } chunks.push(Buffer.from(value)); }
    let body; try { body = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { return out({error: 'INVALID_JSON'}, 400); }
    return out(service(body));
  } catch (e) {
    const known = ['INVALID_REQUEST', 'INVALID_SESSION', 'INVALID_MOVE', 'INVALID_GAME', 'PUZZLE_UNAVAILABLE', 'GAME_FINISHED'];
    return out({error: known.includes(e.message) ? e.message : 'SERVICE_UNAVAILABLE'}, known.includes(e.message) ? 400 : 503);
  }
}
