// trpuzzlemain/server/crypto.mjs ile aynı şema (merkezi servise taşınabilirlik için birebir).
import {gunzipSync} from 'node:zlib';
import {createCipheriv,createDecipheriv,createHmac,randomBytes,hkdfSync} from 'node:crypto';
export function serverKey(value=process.env.TRPUZZLE_SERVER_KEY){
  if(!/^[0-9a-f]{64}$/i.test(value||''))throw new Error('SERVER_NOT_CONFIGURED');
  return Buffer.from(value,'hex');
}
const derive=(key,purpose)=>Buffer.from(hkdfSync('sha256',key,'trpuzzle-v1',purpose,32));
export function seal(value,key,purpose='session'){
  const iv=randomBytes(12),c=createCipheriv('aes-256-gcm',derive(key,purpose),iv);
  c.setAAD(Buffer.from('trpuzzle-'+purpose+'-v1'));
  return Buffer.concat([iv,c.update(JSON.stringify(value)),c.final(),c.getAuthTag()]).toString('base64url');
}
export function unseal(token,key,purpose='session'){
  if(typeof token!=='string'||token.length>24000||!/^[A-Za-z0-9_-]+$/.test(token))throw new Error('INVALID_SESSION');
  try{
    const b=Buffer.from(token,'base64url');if(b.length<29)throw 0;
    const d=createDecipheriv('aes-256-gcm',derive(key,purpose),b.subarray(0,12));
    d.setAAD(Buffer.from('trpuzzle-'+purpose+'-v1'));d.setAuthTag(b.subarray(-16));
    return JSON.parse(Buffer.concat([d.update(b.subarray(12,-16)),d.final()]).toString('utf8'));
  }catch{throw new Error('INVALID_SESSION');}
}
export function decryptCatalog(bytes,key){
  const d=createDecipheriv('aes-256-gcm',key,bytes.subarray(0,12));
  d.setAAD(Buffer.from('trpuzzle-catalog-v1'));d.setAuthTag(bytes.subarray(12,28));
  let plain=Buffer.concat([d.update(bytes.subarray(28)),d.final()]);
  if(plain[0]===0x1f&&plain[1]===0x8b)plain=gunzipSync(plain,{maxOutputLength:32*1024*1024});
  return JSON.parse(plain.toString('utf8'));
}
export function seed(key,value){return createHmac('sha256',derive(key,'selection')).update(value).digest().readUInt32BE(0);}
