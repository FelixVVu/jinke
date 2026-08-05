export const BASEMAP_METADATA_KEY = 'jinkeBasemap';

export function createRasterStyle(key, sourceId, tiles, attribution) {
  return {
    version: 8,
    metadata: { [BASEMAP_METADATA_KEY]: key },
    sources: {
      [sourceId]: {
        type: 'raster',
        tiles,
        tileSize: 256,
        attribution,
      },
    },
    layers: [{ id: `${sourceId}-tiles`, type: 'raster', source: sourceId }],
  };
}

export function selectedFeatureCollection(collection, limit) {
  return {
    type: 'FeatureCollection',
    features: collection.features.filter(
      feature => Number(feature.properties.limit) === Number(limit),
    ),
  };
}

export function normalizeStationQuery(value) {
  return String(value ?? '')
    .normalize('NFKC')
    .trim()
    .toLocaleLowerCase();
}

export function matchingStations(features, query, maximum = 12) {
  const normalizedQuery = normalizeStationQuery(query);
  if (!normalizedQuery) return features.slice(0, maximum);

  return features
    .map((feature, index) => {
      const name = normalizeStationQuery(feature.properties?.station);
      const rank =
        name === normalizedQuery
          ? 0
          : name.startsWith(normalizedQuery)
            ? 1
            : name.includes(normalizedQuery)
              ? 2
              : 3;
      return { feature, index, rank };
    })
    .filter(result => result.rank < 3)
    .sort((left, right) => left.rank - right.rank || left.index - right.index)
    .slice(0, maximum)
    .map(result => result.feature);
}

export function findStationMatch(features, query) {
  return matchingStations(features, query, 1)[0] ?? null;
}

export function stationStatus(feature, limit) {
  const transitMinutes = Number(feature.properties?.apple);
  if (transitMinutes < Number(limit)) return 'included';
  if (transitMinutes === Number(limit)) return 'boundary';
  return 'excluded';
}

export function enrichStationFeature(feature, limit) {
  const transitMinutes = Number(feature.properties?.apple);
  return {
    ...feature,
    properties: {
      ...feature.properties,
      selected_limit: Number(limit),
      remaining_walk_minutes: Math.max(0, Number(limit) - transitMinutes),
      status: stationStatus(feature, limit),
    },
  };
}

export function stationFeatureCollection(collection, limit, display) {
  const features = collection.features
    .map(feature => enrichStationFeature(feature, limit))
    .filter(
      feature =>
        display === 'all' ||
        Boolean(feature.properties.is_jinke) ||
        feature.properties.status !== 'excluded',
    );

  return { type: 'FeatureCollection', features };
}

export function polygonPaintForState(state) {
  const visible = Boolean(state.showPoly);
  return {
    reachFillOpacity: visible && !state.invertFill ? state.opacity : 0,
    inverseFillOpacity: visible && state.invertFill ? state.opacity : 0,
    outlineWidth: visible ? state.width : 0,
  };
}

const layerHandlerBindings = new WeakMap();

export function bindLayerHandlerOnce(map, eventName, layerId, handler) {
  let bindings = layerHandlerBindings.get(map);
  if (!bindings) {
    bindings = new Set();
    layerHandlerBindings.set(map, bindings);
  }

  const key = `${eventName}\u0000${layerId}`;
  if (bindings.has(key)) return false;

  map.on(eventName, layerId, handler);
  bindings.add(key);
  return true;
}

function readCamera(map) {
  const center = map.getCenter();
  return {
    center:
      typeof center.toArray === 'function'
        ? center.toArray()
        : [center.lng, center.lat],
    zoom: map.getZoom(),
    bearing: map.getBearing(),
    pitch: map.getPitch(),
  };
}

export class StyleSwitchCoordinator {
  constructor(map, initialKey, onStyleReady) {
    this.map = map;
    this.onStyleReady = onStyleReady;
    this.requestId = 0;
    this.lastHandledRequestId = -1;
    this.pending = { key: initialKey, requestId: 0, camera: null };
    this.handleStyleLoad = this.handleStyleLoad.bind(this);
    this.map.on('style.load', this.handleStyleLoad);
  }

  switchTo(key, style) {
    this.requestId += 1;
    this.pending = {
      key,
      requestId: this.requestId,
      camera: readCamera(this.map),
    };
    this.map.setStyle(style);
  }

  handleStyleLoad() {
    if (!this.pending || !this.map.isStyleLoaded()) return false;

    const loadedKey = this.map.getStyle()?.metadata?.[BASEMAP_METADATA_KEY];
    if (loadedKey !== this.pending.key) return false;
    if (this.lastHandledRequestId === this.pending.requestId) return false;

    const { camera, key, requestId } = this.pending;
    if (camera) this.map.jumpTo(camera);
    this.lastHandledRequestId = requestId;
    this.onStyleReady({ key, requestId });
    return true;
  }
}
