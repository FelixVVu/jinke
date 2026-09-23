// Server-only shared transport. Never return URLs, credentials, or upstream error bodies.
export class AmapError extends Error {
  constructor(code, retryable = false) { super(code); this.code = code; this.retryable = retryable; }
}
export async function requestAmap(env, operation, parameters, fetchFn = fetch) {
  if (!env?.JINKE_AMAP_KEY) throw new AmapError('AMAP_NOT_CONFIGURED');
  if (!['text', 'polygon'].includes(operation) || Object.keys(parameters).some(k => ['key', 'sig', 'callback'].includes(k))) throw new AmapError('INVALID_QUERY');
  const url = new URL(`https://restapi.amap.com/v5/place/${operation}`);
  url.search = new URLSearchParams({ ...parameters, key: env.JINKE_AMAP_KEY }).toString();
  let response;
  try { response = await fetchFn(url.toString(), { signal: AbortSignal.timeout(12000), redirect: 'error', headers: { Accept: 'application/json' } }); }
  catch { throw new AmapError('AMAP_NETWORK', true); }
  if (!response.ok) throw new AmapError(response.status === 429 ? 'AMAP_RATE_LIMIT' : `AMAP_HTTP_${response.status}`, response.status >= 500);
  let payload;
  try { payload = await response.json(); } catch { throw new AmapError('AMAP_INVALID_JSON'); }
  if (String(payload?.status) !== '1' || !Array.isArray(payload.pois)) throw new AmapError('AMAP_PROVIDER_REJECTED');
  // A provider must never echo the credential into cached responses.
  if (JSON.stringify(payload).includes(env.JINKE_AMAP_KEY)) throw new AmapError('AMAP_UNSAFE_RESPONSE');
  return payload;
}
