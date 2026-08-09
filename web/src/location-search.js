export const MAPTILER_GEOCODING_ENDPOINT =
  'https://api.maptiler.com/geocoding/';

const DEFAULT_LIMIT = 8;
const DEFAULT_CACHE_TTL_MS = 2 * 60 * 1000;

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

function localizedText(value) {
  if (typeof value === 'string') return value.trim();
  if (!value || typeof value !== 'object') return '';
  return String(value.zh ?? value.en ?? value.default ?? '').trim();
}

function contextText(context) {
  return localizedText(
    context?.text_zh ?? context?.text_en ?? context?.text ?? context?.name,
  );
}

function titleCase(value) {
  return String(value || '')
    .replaceAll('_', ' ')
    .replaceAll('-', ' ')
    .replace(/\b\w/g, character => character.toUpperCase());
}

export function normalizeMapTilerFeature(feature, index = 0) {
  const coordinates = featureCoordinates(feature);
  if (!coordinates) return null;

  const properties = feature?.properties || {};
  const primaryName = localizedText(
    feature.text_zh ??
      feature.text_en ??
      feature.text ??
      properties.name ??
      properties.name_zh ??
      properties.name_en,
  );
  const placeName = localizedText(
    feature.place_name_zh ??
      feature.place_name_en ??
      feature.place_name ??
      properties.full_address,
  );
  const name = primaryName || placeName.split(',')[0]?.trim() || 'Unnamed place';
  const placeTypes = Array.isArray(feature.place_type)
    ? feature.place_type
    : [properties.feature_type ?? properties.type].filter(Boolean);
  const categoryValue =
    (Array.isArray(feature.categories) && feature.categories[0]) ||
    (Array.isArray(properties.categories) && properties.categories[0]) ||
    properties.category ||
    properties.place_designation ||
    placeTypes[0] ||
    'place';
  const contexts = Array.isArray(feature.context) ? feature.context : [];
  const contextKind = item =>
    String(item?.id ?? item?.type ?? '').toLowerCase();
  const districtContext =
    contexts.find(item => /municipal_district|district|borough/.test(contextKind(item))) ||
    contexts.find(item => /county/.test(contextKind(item))) ||
    contexts.find(item =>
      /locality|neighbourhood|municipality|place/.test(contextKind(item)),
    );
  const addressContext = contexts.find(item =>
    /^address[.]/.test(contextKind(item)),
  );
  const district =
    contextText(districtContext) ||
    localizedText(
      properties.district ??
        properties.locality ??
        properties.municipality ??
        properties.place,
    );
  const placeRemainder = placeName
    .replace(new RegExp(`^${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*,?\\s*`, 'i'), '')
    .trim();
  const secondary = localizedText(
    properties.full_address ??
      properties.address ??
      feature.address ??
      (contextText(addressContext) || placeRemainder),
  );

  return {
    id: String(feature.id ?? `maptiler-result-${index}`),
    name,
    category: titleCase(categoryValue),
    district,
    secondary,
    coordinates,
    placeType: String(placeTypes[0] || 'place'),
    providerFeature: feature,
  };
}

export function filterShanghaiResults(features, boundary, maximum = DEFAULT_LIMIT) {
  if (!Array.isArray(features)) return [];
  const results = [];
  for (let index = 0; index < features.length; index += 1) {
    const result = normalizeMapTilerFeature(features[index], index);
    if (result && pointInGeoJson(result.coordinates, boundary)) {
      results.push(result);
    }
    if (results.length >= maximum) break;
  }
  return results;
}

export function buildMapTilerGeocodingUrl(
  query,
  { key, bbox, proximity, limit = DEFAULT_LIMIT } = {},
) {
  const normalizedQuery = normalizeLocationQuery(query);
  if (!key || !String(key).trim()) {
    throw new LocationSearchError(
      'missing-config',
      'Map search configuration is missing.',
    );
  }
  if (locationQueryLength(normalizedQuery) < 2) {
    throw new LocationSearchError(
      'query-too-short',
      'Enter at least two characters.',
    );
  }

  const url = new URL(
    `${MAPTILER_GEOCODING_ENDPOINT}${encodeURIComponent(normalizedQuery)}.json`,
  );
  url.searchParams.set('key', String(key).trim());
  url.searchParams.set('country', 'cn');
  if (Array.isArray(bbox) && bbox.length === 4) {
    url.searchParams.set('bbox', bbox.join(','));
  }
  if (validPosition(proximity)) {
    url.searchParams.set('proximity', `${proximity[0]},${proximity[1]}`);
  }
  url.searchParams.set('language', 'zh,en');
  url.searchParams.set(
    'types',
    'poi,address,street,place,locality,neighbourhood,municipality',
  );
  url.searchParams.set('autocomplete', 'true');
  url.searchParams.set('fuzzyMatch', 'true');
  url.searchParams.set('limit', String(Math.min(10, Math.max(1, limit))));
  return url;
}

export function buildLocationSearchUrl(
  query,
  {
    key,
    endpoint,
    bbox,
    proximity,
    limit = DEFAULT_LIMIT,
    origin = globalThis.location?.origin || 'http://localhost',
  } = {},
) {
  const configuredEndpoint = String(endpoint || '').trim();
  if (!configuredEndpoint) {
    return buildMapTilerGeocodingUrl(query, {
      key,
      bbox,
      proximity,
      limit,
    });
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

export class MapTilerLocationSearch {
  constructor({
    keyProvider,
    endpointProvider = () => '',
    boundary,
    fetchFn = globalThis.fetch,
    cacheTtlMs = DEFAULT_CACHE_TTL_MS,
    now = Date.now,
  }) {
    this.keyProvider = keyProvider;
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

    let response;
    try {
      const url = buildLocationSearchUrl(normalizedQuery, {
        key: this.keyProvider?.(),
        endpoint: this.endpointProvider?.(),
        bbox,
        proximity,
        limit,
      });
      response = await this.fetchFn(url, {
        signal: controller.signal,
        headers: { Accept: 'application/json' },
      });
      if (requestId !== this.requestId) return { status: 'stale', results: [] };
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
      if (requestId !== this.requestId) return { status: 'stale', results: [] };
      if (payload?.type !== 'FeatureCollection' || !Array.isArray(payload.features)) {
        throw new LocationSearchError(
          'invalid-response',
          'Map search returned an invalid response.',
        );
      }

      const results = filterShanghaiResults(payload.features, this.boundary, limit);
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
