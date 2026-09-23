// Adapted from production Site v32 (5899143); review branch only.
import { requestAmap } from './amap-client.mjs';
export function runtimeConfig(env) {
  return new Response(
    "window.JINKE_LOCATION_SEARCH_ENDPOINT='/api/amap-place-search';\n" +
    "window.JINKE_LOCATION_SEARCH_PROVIDER='amap';\n" +
    'window.JINKE_CARTO_BASEMAP_KEY=' + JSON.stringify(env.JINKE_CARTO_BASEMAP_KEY || '').replaceAll('<', '\\u003c') + ';\n',
    { headers: { 'Content-Type': 'application/javascript; charset=utf-8', 'Cache-Control': 'no-store' } },
  );
}

const json = (body, status = 200) => Response.json(body, { status, headers: { 'Cache-Control': 'no-store' } });

export async function searchPlaces(request, env, fetchFn = fetch) {
  const input = new URL(request.url);
  const q = (input.searchParams.get('q') || '').trim();
  if (q.length < 2 || q.length > 80) return json({ error: 'Invalid search query' }, 400);
  if (!env.JINKE_AMAP_KEY) return json({ error: 'Search unavailable' }, 503);
  try {
    const payload = await requestAmap(env, 'text', {
      keywords: q, region: '310000', city_limit: 'true', page_size: '25', page_num: '1',
    }, fetchFn);
    // Coordinates remain GCJ-02; the unchanged client converts to WGS84 once.
    const fields = ['id', 'name', 'location', 'type', 'typecode', 'address', 'adname', 'adcode', 'cityname', 'citycode', 'pname', 'pcode'];
    const pois = payload.pois.map(poi => Object.fromEntries(fields.filter(k => k in poi).map(k => [k, poi[k]])));
    return json({ status: '1', count: String(pois.length), pois });
  } catch (error) {
    return json({ error: 'Search unavailable' }, error.code === 'AMAP_RATE_LIMIT' ? 429 : 502);
  }
}
