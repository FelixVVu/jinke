const DEFAULT_LIMIT = 8;
const DEFAULT_CACHE_TTL_MS = 2 * 60 * 1000;
const GCJ_A = 6378245;
const GCJ_EE = 0.006693421622965943;

export class LocationSearchError extends Error {
  constructor(code, message, { status, cause } = {}) {
    super(message, { cause });
    this.name = 'LocationSearchError';
    this.code = code;
    this.status = status;
  }
}

export function normalizeLocationQuery(value) {
  return String(value ?? '').normalize('NFKC').trim();
}

export function locationQueryLength(value) {
  return [...normalizeLocationQuery(value)].length;
}

function validPosition(value) {
  return (
    Array.isArray(value) &&
    value.length >= 2 &&
    Number.isFinite(Number(value[0])) &&
    Number.isFinite(Number(value[1]))
  );
}

export function featureCoordinates(feature) {
  const coordinates = validPosition(feature?.center)
    ? feature.center
    : feature?.geometry?.type === 'Point' &&
        validPosition(feature.geometry.coordinates)
      ? feature.geometry.coordinates
      : null;

  return coordinates
    ? [Number(coordinates[0]), Number(coordinates[1])]
    : null;
}

function pointOnSegment([x, y], [x1, y1], [x2, y2]) {
  const epsilon = 1e-10;
  const cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1);
  if (Math.abs(cross) > epsilon) return false;
  return (
    x >= Math.min(x1, x2) - epsilon &&
    x <= Math.max(x1, x2) + epsilon &&
    y >= Math.min(y1, y2) - epsilon &&
    y <= Math.max(y1, y2) + epsilon
  );
}

function ringContains(point, ring) {
  if (!Array.isArray(ring) || ring.length < 3) {
    return { inside: false, boundary: false };
  }

  let inside = false;
  for (let index = 0, previous = ring.length - 1; index < ring.length; previous = index++) {
    const currentPoint = ring[index];
    const previousPoint = ring[previous];
    if (!validPosition(currentPoint) || !validPosition(previousPoint)) continue;
    if (pointOnSegment(point, previousPoint, currentPoint)) {
      return { inside: true, boundary: true };
    }

    const [x, y] = point;
    const [x1, y1] = previousPoint;
    const [x2, y2] = currentPoint;
    const crosses =
      (y1 > y) !== (y2 > y) &&
      x < ((x2 - x1) * (y - y1)) / (y2 - y1) + x1;
    if (crosses) inside = !inside;
  }
  return { inside, boundary: false };
}

function polygonContains(point, coordinates) {
  if (!Array.isArray(coordinates) || !coordinates.length) return false;
  const shell = ringContains(point, coordinates[0]);
  if (shell.boundary) return true;
  if (!shell.inside) return false;

  for (const hole of coordinates.slice(1)) {
    const result = ringContains(point, hole);
    if (result.boundary) return true;
    if (result.inside) return false;
  }
  return true;
}

export function pointInGeoJson(point, geojson) {
  if (!validPosition(point) || !geojson) return false;
  if (geojson.type === 'FeatureCollection') {
    return geojson.features?.some(feature => pointInGeoJson(point, feature));
  }
  if (geojson.type === 'Feature') {
    return pointInGeoJson(point, geojson.geometry);
  }
  if (geojson.type === 'Polygon') {
    return polygonContains(point, geojson.coordinates);
  }
  if (geojson.type === 'MultiPolygon') {
    return geojson.coordinates?.some(polygon => polygonContains(point, polygon));
  }
  return false;
}

function visitCoordinates(value, bounds) {
  if (validPosition(value)) {
    const longitude = Number(value[0]);
    const latitude = Number(value[1]);
    bounds[0] = Math.min(bounds[0], longitude);
    bounds[1] = Math.min(bounds[1], latitude);
    bounds[2] = Math.max(bounds[2], longitude);
    bounds[3] = Math.max(bounds[3], latitude);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach(item => visitCoordinates(item, bounds));
  }
}

export function geoJsonBounds(geojson) {
  const bounds = [Infinity, Infinity, -Infinity, -Infinity];
  const visit = value => {
    if (!value) return;
    if (value.type === 'FeatureCollection') {
      value.features?.forEach(visit);
    } else if (value.type === 'Feature') {
      visit(value.geometry);
    } else if (value.coordinates) {
      visitCoordinates(value.coordinates, bounds);
    }
  };
  visit(geojson);
  return bounds.every(Number.isFinite) ? bounds : null;
}

function titleCase(value) {
  return String(value || '')
    .replaceAll('_', ' ')
    .replaceAll('-', ' ')
    .replace(/\b\w/g, character => character.toUpperCase());
}

function outsideChina(longitude, latitude) {
  return longitude < 72.004 || longitude > 137.8347 || latitude < 0.8293 || latitude > 55.8271;
}

function transformLatitude(longitude, latitude) {
  let result =
    -100 + 2 * longitude + 3 * latitude + 0.2 * latitude ** 2 +
    0.1 * longitude * latitude + 0.2 * Math.sqrt(Math.abs(longitude));
  result +=
    ((20 * Math.sin(6 * longitude * Math.PI) + 20 * Math.sin(2 * longitude * Math.PI)) * 2) / 3;
  result +=
    ((20 * Math.sin(latitude * Math.PI) + 40 * Math.sin((latitude / 3) * Math.PI)) * 2) / 3;
  result +=
    ((160 * Math.sin((latitude / 12) * Math.PI) + 320 * Math.sin((latitude * Math.PI) / 30)) * 2) / 3;
  return result;
}

function transformLongitude(longitude, latitude) {
  let result =
    300 + longitude + 2 * latitude + 0.1 * longitude ** 2 +
    0.1 * longitude * latitude + 0.1 * Math.sqrt(Math.abs(longitude));
  result +=
    ((20 * Math.sin(6 * longitude * Math.PI) + 20 * Math.sin(2 * longitude * Math.PI)) * 2) / 3;
  result +=
    ((20 * Math.sin(longitude * Math.PI) + 40 * Math.sin((longitude / 3) * Math.PI)) * 2) / 3;
  result +=
    ((150 * Math.sin((longitude / 12) * Math.PI) + 300 * Math.sin((longitude / 30) * Math.PI)) * 2) / 3;
  return result;
}

export function wgs84ToGcj02(longitude, latitude) {
  const lng = Number(longitude);
  const lat = Number(latitude);
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null;
  if (outsideChina(lng, lat)) return [lng, lat];

  let latitudeDelta = transformLatitude(lng - 105, lat - 35);
  let longitudeDelta = transformLongitude(lng - 105, lat - 35);
  const radians = (lat / 180) * Math.PI;
  let magic = Math.sin(radians);
  magic = 1 - GCJ_EE * magic ** 2;
  const squareRootMagic = Math.sqrt(magic);
  latitudeDelta =
    (latitudeDelta * 180) /
    (((GCJ_A * (1 - GCJ_EE)) / (magic * squareRootMagic)) * Math.PI);
  longitudeDelta =
    (longitudeDelta * 180) /
    ((GCJ_A / squareRootMagic) * Math.cos(radians) * Math.PI);
  return [lng + longitudeDelta, lat + latitudeDelta];
}

export function gcj02ToWgs84(longitude, latitude) {
  const lng = Number(longitude);
  const lat = Number(latitude);
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null;
  if (outsideChina(lng, lat)) return [lng, lat];

  let wgsLongitude = lng;
  let wgsLatitude = lat;
  for (let iteration = 0; iteration < 10; iteration += 1) {
    const converted = wgs84ToGcj02(wgsLongitude, wgsLatitude);
    const longitudeError = converted[0] - lng;
    const latitudeError = converted[1] - lat;
    wgsLongitude -= longitudeError;
    wgsLatitude -= latitudeError;
    if (Math.abs(longitudeError) < 1e-8 && Math.abs(latitudeError) < 1e-8) break;
  }
  return [wgsLongitude, wgsLatitude];
}

function amapText(value) {
  if (Array.isArray(value)) return value.map(amapText).find(Boolean) || '';
  return typeof value === 'string' ? value.trim() : '';
}

export function amapFeatureCoordinates(poi) {
  const location = amapText(poi?.location);
  const parts = location.split(',').map(Number);
  if (parts.length !== 2 || !parts.every(Number.isFinite)) return null;
  return gcj02ToWgs84(parts[0], parts[1]);
}

export function normalizeAmapPoi(poi, index = 0) {
  const coordinates = amapFeatureCoordinates(poi);
  if (!coordinates) return null;
  const types = amapText(poi?.type).split(';').map(value => value.trim()).filter(Boolean);
  const name = amapText(poi?.name) || 'Unnamed place';
  return {
    id: String(poi?.id || `amap-result-${index}`),
    name,
    category: titleCase(types.at(-1) || 'place'),
    district: amapText(poi?.adname) || amapText(poi?.cityname),
    secondary: amapText(poi?.address),
    coordinates,
    placeType: 'poi',
    provider: 'amap',
  };
}

export function filterShanghaiAmapResults(pois, boundary, maximum = DEFAULT_LIMIT) {
  if (!Array.isArray(pois)) return [];
  const results = [];
  for (let index = 0; index < pois.length; index += 1) {
    const result = normalizeAmapPoi(pois[index], index);
    if (result && pointInGeoJson(result.coordinates, boundary)) results.push(result);
    if (results.length >= maximum) break;
  }
  return results;
}

export function buildLocationSearchUrl(
  query,
  {
    endpoint,
    bbox,
    proximity,
    limit = DEFAULT_LIMIT,
    origin = globalThis.location?.origin || 'http://localhost',
  } = {},
) {
  const configuredEndpoint = String(endpoint || '').trim();
  if (!configuredEndpoint) {
    throw new LocationSearchError(
      'missing-config',
      'Map search configuration is missing.',
    );
  }

  const normalizedQuery = normalizeLocationQuery(query);
  if (locationQueryLength(normalizedQuery) < 2) {
    throw new LocationSearchError(
      'query-too-short',
      'Enter at least two characters.',
    );
  }

  let url;
  try {
    url = new URL(configuredEndpoint, origin);
  } catch (cause) {
    throw new LocationSearchError(
      'missing-config',
      'Map search configuration is invalid.',
      { cause },
    );
  }
  if (url.origin !== new URL(origin).origin) {
    throw new LocationSearchError(
      'missing-config',
      'Map search proxy must use the current Site origin.',
    );
  }

  url.searchParams.set('q', normalizedQuery);
  if (Array.isArray(bbox) && bbox.length === 4) {
    url.searchParams.set('bbox', bbox.join(','));
  }
  if (validPosition(proximity)) {
    url.searchParams.set('proximity', `${proximity[0]},${proximity[1]}`);
  }
  url.searchParams.set('limit', String(Math.min(10, Math.max(1, limit))));
  return url;
}

export class AmapLocationSearch {
  constructor({
    endpointProvider = () => '',
    boundary,
    fetchFn = globalThis.fetch,
    cacheTtlMs = DEFAULT_CACHE_TTL_MS,
    now = Date.now,
  }) {
    this.endpointProvider = endpointProvider;
    this.boundary = boundary;
    this.fetchFn = fetchFn;
    this.cacheTtlMs = cacheTtlMs;
    this.now = now;
    this.cache = new Map();
    this.requestId = 0;
    this.abortController = null;
  }

  cancel() {
    this.requestId += 1;
    this.abortController?.abort();
    this.abortController = null;
  }

  async search(query, { bbox, proximity, limit = DEFAULT_LIMIT } = {}) {
    const normalizedQuery = normalizeLocationQuery(query);
    const requestId = ++this.requestId;
    this.abortController?.abort();
    const controller = new AbortController();
    this.abortController = controller;

    const cacheKey = [
      normalizedQuery.toLocaleLowerCase(),
      bbox?.join(',') || '',
      proximity?.map(value => Number(value).toFixed(3)).join(',') || '',
      limit,
    ].join('|');
    const cached = this.cache.get(cacheKey);
    if (cached && cached.expiresAt > this.now()) {
      this.abortController = null;
      return { status: cached.results.length ? 'ok' : 'empty', results: cached.results, cached: true };
    }

    const configuredEndpoint = this.endpointProvider?.();

    const fetchPayload = async url => {
      let response;
      try {
        response = await this.fetchFn(String(url), {
          signal: controller.signal,
          headers: { Accept: 'application/json' },
          credentials:
            globalThis.location?.origin &&
            url.origin === globalThis.location.origin
              ? 'same-origin'
              : 'omit',
          cache: 'no-store',
        });
      } catch (cause) {
        throw new LocationSearchError(
          'network-error',
          'Map search could not reach the network.',
          { cause },
        );
      }
      if (requestId !== this.requestId) return null;
      if (response.status === 429) {
        throw new LocationSearchError(
          'rate-limit',
          'Map search is temporarily rate-limited.',
          { status: response.status },
        );
      }
      if ([502, 503, 504].includes(response.status)) {
        throw new LocationSearchError(
          'service-unavailable',
          'Map search service is temporarily unavailable.',
          { status: response.status },
        );
      }
      if (!response.ok) {
        throw new LocationSearchError(
          'request-failed',
          'Map search request failed.',
          { status: response.status },
        );
      }

      let payload;
      try {
        payload = await response.json();
      } catch (cause) {
        throw new LocationSearchError(
          'invalid-response',
          'Map search returned invalid JSON.',
          { cause },
        );
      }
      if (requestId !== this.requestId) return null;
      if (String(payload?.status) !== '1' || !Array.isArray(payload.pois)) {
        throw new LocationSearchError(
          'invalid-response',
          'Map search returned an invalid response.',
        );
      }
      return payload;
    };

    try {
      const primaryUrl = buildLocationSearchUrl(normalizedQuery, {
        endpoint: configuredEndpoint,
        bbox,
        proximity,
        limit,
      });
      const payload = await fetchPayload(primaryUrl);
      if (!payload || requestId !== this.requestId) {
        return { status: 'stale', results: [] };
      }

      const results = filterShanghaiAmapResults(payload.pois, this.boundary, limit);
      this.cache.set(cacheKey, {
        results,
        expiresAt: this.now() + this.cacheTtlMs,
      });
      return { status: results.length ? 'ok' : 'empty', results, cached: false };
    } catch (error) {
      if (
        requestId !== this.requestId ||
        controller.signal.aborted ||
        error?.name === 'AbortError'
      ) {
        return { status: 'stale', results: [] };
      }
      if (error instanceof LocationSearchError) throw error;
      throw new LocationSearchError(
        'network-error',
        'Map search could not reach the network.',
        { cause: error },
      );
    } finally {
      if (requestId === this.requestId) this.abortController = null;
    }
  }
}

export class SingleLocationSelection {
  constructor({ createVisual, isPresent = marker => Boolean(marker) }) {
    this.createVisual = createVisual;
    this.isPresent = isPresent;
    this.activeResult = null;
    this.marker = null;
    this.popup = null;
  }

  removeVisuals() {
    this.marker?.remove();
    this.popup?.remove();
    this.marker = null;
    this.popup = null;
  }

  select(result) {
    this.removeVisuals();
    this.activeResult = result;
    const visuals = this.createVisual(result) || {};
    this.marker = visuals.marker || null;
    this.popup = visuals.popup || null;
    return result;
  }

  ensure() {
    if (
      this.activeResult &&
      (!this.marker || !this.isPresent(this.marker))
    ) {
      const result = this.activeResult;
      this.removeVisuals();
      const visuals = this.createVisual(result) || {};
      this.marker = visuals.marker || null;
      this.popup = visuals.popup || null;
    }
    return this.activeResult;
  }

  clear() {
    this.removeVisuals();
    this.activeResult = null;
  }
}
