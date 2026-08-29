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

const openFreeMapAttribution =
  '<a href="https://openfreemap.org/">OpenFreeMap</a> © ' +
  '<a href="https://openmaptiles.org/">OpenMapTiles</a> Data © ' +
  '<a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>';

const metroAttribution =
  '<a href="https://github.com/metromancn/MetroMapOpenMiniProgram">Shanghai metro network</a> (MIT) · ' +
  '<a href="https://www.npmjs.com/package/@kyuri-metro/shmetro-palette">line colors</a> (MIT)';

const bilingualName = [
  'case',
  [
    'all',
    ['has', 'name:zh'],
    ['has', 'name:en'],
    ['!=', ['get', 'name:zh'], ['get', 'name:en']],
  ],
  [
    'format',
    ['get', 'name:zh'],
    {},
    '\n',
    {},
    ['get', 'name:en'],
    { 'font-scale': 0.78 },
  ],
  [
    'coalesce',
    ['get', 'name:zh'],
    ['get', 'name:nonlatin'],
    ['get', 'name:en'],
    ['get', 'name'],
  ],
];

const lineGeometryFilter = [
  'match',
  ['geometry-type'],
  ['LineString', 'MultiLineString'],
  true,
  false,
];

const polygonGeometryFilter = [
  'match',
  ['geometry-type'],
  ['Polygon', 'MultiPolygon'],
  true,
  false,
];

function emptyFeatureCollection() {
  return { type: 'FeatureCollection', features: [] };
}

/**
 * Independent warm vector cartography backed only by OpenFreeMap/OpenMapTiles.
 * The transit variant adds the locally committed, MIT-licensed metro GeoJSON.
 */
export function createWarmVectorStyle(
  key,
  { transit = false, metroLines, metroStations } = {},
) {
  const roadOpacity = transit ? 0.58 : 0.9;
  const labelOpacity = transit ? 0.5 : 0.88;
  const poiOpacity = transit ? 0.22 : 0.5;
  const font = ['Noto Sans Regular'];

  const sources = {
    openfreemap: {
      type: 'vector',
      url: 'https://tiles.openfreemap.org/planet',
      attribution: openFreeMapAttribution,
    },
  };

  if (transit) {
    sources['shanghai-metro-lines'] = {
      type: 'geojson',
      data: metroLines || emptyFeatureCollection(),
      attribution: metroAttribution,
    };
    sources['shanghai-metro-stations'] = {
      type: 'geojson',
      data: metroStations || emptyFeatureCollection(),
    };
  }

  const layers = [
    {
      id: 'warm-background',
      type: 'background',
      paint: { 'background-color': '#f7f3eb' },
    },
    {
      id: 'warm-landcover',
      type: 'fill',
      source: 'openfreemap',
      'source-layer': 'landcover',
      filter: polygonGeometryFilter,
      paint: {
        'fill-color': [
          'match',
          ['get', 'class'],
          ['wood', 'grass', 'farmland'],
          '#e8f1df',
          '#f4f1e9',
        ],
        'fill-opacity': transit ? 0.58 : 0.8,
      },
    },
    {
      id: 'warm-landuse',
      type: 'fill',
      source: 'openfreemap',
      'source-layer': 'landuse',
      filter: polygonGeometryFilter,
      paint: {
        'fill-color': [
          'match',
          ['get', 'class'],
          ['park', 'cemetery'],
          '#e4efdc',
          ['hospital', 'school'],
          '#f2eee6',
          '#f6f2eb',
        ],
        'fill-opacity': transit ? 0.54 : 0.74,
      },
    },
    {
      id: 'warm-park',
      type: 'fill',
      source: 'openfreemap',
      'source-layer': 'park',
      filter: polygonGeometryFilter,
      paint: {
        'fill-color': '#dcebcf',
        'fill-opacity': transit ? 0.68 : 0.92,
      },
    },
    {
      id: 'warm-water',
      type: 'fill',
      source: 'openfreemap',
      'source-layer': 'water',
      filter: polygonGeometryFilter,
      paint: { 'fill-color': '#75bce8' },
    },
    {
      id: 'warm-waterway',
      type: 'line',
      source: 'openfreemap',
      'source-layer': 'waterway',
      filter: lineGeometryFilter,
      paint: {
        'line-color': '#69afe0',
        'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.4, 16, 2],
        'line-opacity': 0.84,
      },
    },
    {
      id: 'warm-buildings',
      type: 'fill',
      source: 'openfreemap',
      'source-layer': 'building',
      minzoom: 13,
      paint: {
        'fill-color': transit ? '#ebe8e1' : '#e4e0d8',
        'fill-outline-color': '#d6d2ca',
        'fill-opacity': transit ? 0.5 : 0.72,
      },
    },
    {
      id: 'warm-paths',
      type: 'line',
      source: 'openfreemap',
      'source-layer': 'transportation',
      minzoom: 13,
      filter: ['all', lineGeometryFilter, ['==', ['get', 'class'], 'path']],
      paint: {
        'line-color': '#dedbd5',
        'line-width': ['interpolate', ['linear'], ['zoom'], 13, 0.3, 18, 1.5],
        'line-dasharray': [2, 1.5],
        'line-opacity': roadOpacity * 0.7,
      },
    },
    {
      id: 'warm-local-roads',
      type: 'line',
      source: 'openfreemap',
      'source-layer': 'transportation',
      minzoom: 10,
      filter: [
        'all',
        lineGeometryFilter,
        ['match', ['get', 'class'], ['minor', 'service', 'track'], true, false],
      ],
      paint: {
        'line-color': '#e2e0dc',
        'line-width': ['interpolate', ['linear'], ['zoom'], 10, 0.35, 15, 1.5, 18, 4.8],
        'line-opacity': roadOpacity,
      },
    },
    {
      id: 'warm-major-road-casing',
      type: 'line',
      source: 'openfreemap',
      'source-layer': 'transportation',
      minzoom: 7,
      filter: [
        'all',
        lineGeometryFilter,
        ['match', ['get', 'class'], ['primary', 'secondary', 'tertiary', 'trunk'], true, false],
      ],
      paint: {
        'line-color': '#aaa9a4',
        'line-width': ['interpolate', ['linear'], ['zoom'], 7, 0.9, 12, 2.4, 17, 8],
        'line-opacity': roadOpacity,
      },
    },
    {
      id: 'warm-major-roads',
      type: 'line',
      source: 'openfreemap',
      'source-layer': 'transportation',
      minzoom: 7,
      filter: [
        'all',
        lineGeometryFilter,
        ['match', ['get', 'class'], ['primary', 'secondary', 'tertiary', 'trunk'], true, false],
      ],
      paint: {
        'line-color': '#d0cfca',
        'line-width': ['interpolate', ['linear'], ['zoom'], 7, 0.5, 12, 1.45, 17, 6.3],
        'line-opacity': roadOpacity,
      },
    },
    {
      id: 'warm-motorway-casing',
      type: 'line',
      source: 'openfreemap',
      'source-layer': 'transportation',
      minzoom: 5,
      filter: ['all', lineGeometryFilter, ['==', ['get', 'class'], 'motorway']],
      paint: {
        'line-color': '#c6a87e',
        'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1, 12, 3.5, 17, 10],
        'line-opacity': roadOpacity,
      },
    },
    {
      id: 'warm-motorways',
      type: 'line',
      source: 'openfreemap',
      'source-layer': 'transportation',
      minzoom: 5,
      filter: ['all', lineGeometryFilter, ['==', ['get', 'class'], 'motorway']],
      paint: {
        'line-color': '#f3d4a5',
        'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.55, 12, 2.35, 17, 7.6],
        'line-opacity': roadOpacity,
      },
    },
    {
      id: 'warm-rail',
      type: 'line',
      source: 'openfreemap',
      'source-layer': 'transportation',
      minzoom: 11,
      filter: ['all', lineGeometryFilter, ['==', ['get', 'class'], 'rail']],
      paint: {
        'line-color': '#b9b7b1',
        'line-width': ['interpolate', ['linear'], ['zoom'], 11, 0.4, 16, 1.2],
        'line-dasharray': [3, 2],
        'line-opacity': transit ? 0.22 : 0.52,
      },
    },
    {
      id: 'warm-boundaries',
      type: 'line',
      source: 'openfreemap',
      'source-layer': 'boundary',
      filter: ['all', lineGeometryFilter, ['!=', ['get', 'maritime'], 1]],
      paint: {
        'line-color': '#a9a8a3',
        'line-width': ['interpolate', ['linear'], ['zoom'], 4, 0.4, 12, 1],
        'line-dasharray': [3, 2],
        'line-opacity': 0.45,
      },
    },
    {
      id: 'warm-water-labels',
      type: 'symbol',
      source: 'openfreemap',
      'source-layer': 'water_name',
      minzoom: 8,
      layout: {
        'text-field': bilingualName,
        'text-font': font,
        'text-size': ['interpolate', ['linear'], ['zoom'], 8, 10, 16, 13],
        'symbol-placement': 'point',
      },
      paint: {
        'text-color': '#2d75a6',
        'text-halo-color': '#f7f3eb',
        'text-halo-width': 1.2,
        'text-opacity': labelOpacity,
      },
    },
    {
      id: 'warm-road-labels',
      type: 'symbol',
      source: 'openfreemap',
      'source-layer': 'transportation_name',
      minzoom: transit ? 13.5 : 12,
      filter: [
        'all',
        lineGeometryFilter,
        ['match', ['get', 'class'], ['primary', 'secondary', 'tertiary', 'trunk', 'minor'], true, false],
      ],
      layout: {
        'symbol-placement': 'line',
        'text-field': bilingualName,
        'text-font': font,
        'text-size': ['interpolate', ['linear'], ['zoom'], 12, 9.5, 17, 12.5],
        'symbol-spacing': 350,
      },
      paint: {
        'text-color': '#565654',
        'text-halo-color': '#faf8f3',
        'text-halo-width': 1.4,
        'text-opacity': labelOpacity,
      },
    },
    {
      id: 'warm-place-labels',
      type: 'symbol',
      source: 'openfreemap',
      'source-layer': 'place',
      minzoom: 3,
      filter: ['match', ['get', 'class'], ['country', 'state', 'city', 'town', 'village'], true, false],
      layout: {
        'text-field': bilingualName,
        'text-font': font,
        'text-size': [
          'interpolate',
          ['linear'],
          ['zoom'],
          3,
          10,
          9,
          13,
          14,
          15,
        ],
        'text-max-width': 9,
      },
      paint: {
        'text-color': '#343432',
        'text-halo-color': '#faf8f3',
        'text-halo-width': 1.5,
        'text-opacity': labelOpacity,
      },
    },
    {
      id: 'warm-poi-labels',
      type: 'symbol',
      source: 'openfreemap',
      'source-layer': 'poi',
      minzoom: transit ? 16 : 15,
      layout: {
        'text-field': bilingualName,
        'text-font': font,
        'text-size': 10.5,
        'text-max-width': 8,
      },
      paint: {
        'text-color': '#6c6a65',
        'text-halo-color': '#faf8f3',
        'text-halo-width': 1.2,
        'text-opacity': poiOpacity,
      },
    },
  ];

  if (transit) {
    layers.push(
      {
        id: 'metro-line-casing',
        type: 'line',
        source: 'shanghai-metro-lines',
        minzoom: 7,
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': '#ffffff',
          'line-width': ['interpolate', ['linear'], ['zoom'], 7, 2.7, 11, 4.6, 16, 8.5],
          'line-opacity': 0.94,
        },
      },
      {
        id: 'metro-lines',
        type: 'line',
        source: 'shanghai-metro-lines',
        minzoom: 7,
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['interpolate', ['linear'], ['zoom'], 7, 1.45, 11, 2.8, 16, 5.7],
          'line-opacity': 0.96,
        },
      },
      {
        id: 'metro-line-labels',
        type: 'symbol',
        source: 'shanghai-metro-lines',
        minzoom: 9.5,
        layout: {
          'symbol-placement': 'line',
          'symbol-spacing': 520,
          'text-field': ['get', 'line_id'],
          'text-font': ['Noto Sans Bold'],
          'text-size': 10,
        },
        paint: {
          'text-color': '#202124',
          'text-halo-color': '#ffffff',
          'text-halo-width': 2,
        },
      },
      {
        id: 'metro-stations',
        type: 'circle',
        source: 'shanghai-metro-stations',
        minzoom: 10.5,
        filter: ['==', ['get', 'interchange'], false],
        paint: {
          'circle-color': '#ffffff',
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 10.5, 2.1, 16, 4.1],
          'circle-stroke-color': '#4a4a48',
          'circle-stroke-width': 1.15,
        },
      },
      {
        id: 'metro-interchanges',
        type: 'circle',
        source: 'shanghai-metro-stations',
        minzoom: 8.5,
        filter: ['==', ['get', 'interchange'], true],
        paint: {
          'circle-color': '#ffffff',
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 8.5, 3.2, 16, 6.2],
          'circle-stroke-color': '#2f302f',
          'circle-stroke-width': 2,
        },
      },
      {
        id: 'metro-station-labels',
        type: 'symbol',
        source: 'shanghai-metro-stations',
        minzoom: 11.5,
        layout: {
          'text-field': [
            'format',
            ['get', 'name_zh'],
            {},
            '\n',
            {},
            ['get', 'name_latin'],
            { 'font-scale': 0.68 },
          ],
          'text-font': font,
          'text-size': ['interpolate', ['linear'], ['zoom'], 11.5, 9.5, 16, 12],
          'text-offset': [0, 1.05],
          'text-anchor': 'top',
          'text-optional': true,
          'symbol-sort-key': ['-', 4, ['get', 'line_count']],
        },
        paint: {
          'text-color': '#262725',
          'text-halo-color': '#ffffff',
          'text-halo-width': 1.7,
          'text-opacity': 0.94,
        },
      },
    );
  }

  return {
    version: 8,
    metadata: {
      [BASEMAP_METADATA_KEY]: key,
      'jinke:cartography':
        'Independent custom vector cartography using OpenFreeMap/OpenMapTiles data.',
    },
    glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    sources,
    layers,
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

const roundStationSize = value => Math.round(value * 100) / 100;

export function stationPaintForState(state) {
  const requestedSize = Number(state.stationSize);
  const stationSize = Number.isFinite(requestedSize)
    ? Math.max(3, requestedSize)
    : 7;

  if (state.stationScaling === 'fixed') {
    return {
      radius: [
        'case',
        ['get', 'is_jinke'],
        stationSize + 3,
        stationSize,
      ],
      strokeWidth: 2,
      highlightRadius: stationSize + 7,
    };
  }

  const radiusStops = [
    [7, roundStationSize(Math.max(1.8, stationSize * 0.3)), 1.8, 3.5],
    [9, roundStationSize(Math.max(2.3, stationSize * 0.38)), 2.05, 4],
    [11, roundStationSize(Math.max(3.2, stationSize * 0.55)), 2.3, 5],
    [13, roundStationSize(Math.max(4.6, stationSize * 0.78)), 2.65, 6],
    [15, stationSize, 3, 7],
    [18, roundStationSize(stationSize * 1.08), 3.2, 7],
  ];
  const radius = [
    'interpolate',
    ['linear'],
    ['zoom'],
    ...radiusStops.flatMap(([zoom, value, originBoost]) => [
      zoom,
      [
        'case',
        ['get', 'is_jinke'],
        roundStationSize(value + originBoost),
        value,
      ],
    ]),
  ];

  return {
    radius,
    strokeWidth: [
      'interpolate',
      ['linear'],
      ['zoom'],
      7,
      0.75,
      9,
      1,
      11,
      1.25,
      13,
      1.6,
      15,
      2,
      18,
      2,
    ],
    highlightRadius: [
      'interpolate',
      ['linear'],
      ['zoom'],
      ...radiusStops.flatMap(([zoom, value, , highlightGap]) => [
        zoom,
        roundStationSize(value + highlightGap),
      ]),
    ],
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
    // `styledata` is emitted as soon as the new style is usable. Waiting only
    // for `style.load` can deadlock overlays when a remote basemap source keeps
    // the style in a loading state indefinitely.
    this.map.on('styledata', this.handleStyleLoad);
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
    if (!this.pending) return false;

    const loadedKey = this.map.getStyle()?.metadata?.[BASEMAP_METADATA_KEY];
    if (loadedKey !== this.pending.key) return false;
    if (this.lastHandledRequestId === this.pending.requestId) return false;

    const { camera, key, requestId } = this.pending;
    if (camera) this.map.jumpTo(camera);
    const restored = this.onStyleReady({ key, requestId });
    if (restored === false) return false;
    this.lastHandledRequestId = requestId;
    return true;
  }
}
