import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import {
  StyleSwitchCoordinator,
  bindLayerHandlerOnce,
  createRasterStyle,
  createWarmVectorStyle,
  enrichStationFeature,
  findStationMatch,
  matchingStations,
  normalizeStationQuery,
  polygonPaintForState,
  selectedFeatureCollection,
  stationFeatureCollection,
} from '../web/src/map-utils.js';
import {
  AmapLocationSearch,
  LocationSearchError,
  SingleLocationSelection,
  buildLocationSearchUrl,
  filterShanghaiAmapResults,
  gcj02ToWgs84,
  wgs84ToGcj02,
} from '../web/src/location-search.js';


test('raster styles use explicit source IDs and carry basemap identity', () => {
  const style = createRasterStyle(
    'pastel',
    'carto-voyager',
    ['https://example.test/{z}/{x}/{y}.png'],
    'Example attribution',
  );

  assert.equal(style.metadata.jinkeBasemap, 'pastel');
  assert.deepEqual(Object.keys(style.sources), ['carto-voyager']);
  assert.equal(style.sources['carto-voyager'].attribution, 'Example attribution');
  assert.equal(style.layers[0].source, 'carto-voyager');
  assert.equal(style.sources.r, undefined);
});


test('rapid style changes restore only the latest style and its camera', () => {
  const listeners = new Map();
  const styles = [];
  const jumps = [];
  const ready = [];
  let currentStyle = createRasterStyle('explore', 'explore-source', [], '');
  const map = {
    on(eventName, listener) {
      listeners.set(eventName, listener);
    },
    getCenter: () => ({ toArray: () => [121.6, 31.2] }),
    getZoom: () => 10,
    getBearing: () => 15,
    getPitch: () => 25,
    setStyle(style) {
      styles.push(style);
    },
    getStyle: () => currentStyle,
    jumpTo(camera) {
      jumps.push(camera);
    },
  };

  const coordinator = new StyleSwitchCoordinator(
    map,
    'explore',
    value => ready.push(value),
  );
  assert.deepEqual([...listeners.keys()].sort(), ['style.load', 'styledata']);

  const dark = createRasterStyle('dark', 'dark-source', [], '');
  const pastel = createRasterStyle('pastel', 'voyager-source', [], '');
  coordinator.switchTo('dark', dark);
  coordinator.switchTo('pastel', pastel);
  assert.equal(styles.length, 2);

  currentStyle = dark;
  listeners.get('styledata')();
  assert.equal(ready.length, 0);

  currentStyle = pastel;
  listeners.get('styledata')();
  assert.deepEqual(ready, [{ key: 'pastel', requestId: 2 }]);
  assert.deepEqual(jumps, [
    { center: [121.6, 31.2], zoom: 10, bearing: 15, pitch: 25 },
  ]);

  listeners.get('style.load')();
  assert.equal(ready.length, 1);
});


test('style.load restores overlays before basemap sources finish loading', () => {
  const listeners = new Map();
  const ready = [];
  let currentStyle = createRasterStyle(
    'explore',
    'explore-source',
    ['https://example.test/{z}/{x}/{y}.png'],
    '',
  );

  const map = {
    on(eventName, listener) {
      listeners.set(eventName, listener);
    },
    getCenter: () => ({ toArray: () => [121.6, 31.2] }),
    getZoom: () => 10,
    getBearing: () => 0,
    getPitch: () => 0,
    getStyle: () => currentStyle,
    isStyleLoaded: () => false,
    jumpTo() {},
    setStyle(style) {
      currentStyle = style;
    },
  };

  const coordinator = new StyleSwitchCoordinator(
    map,
    'explore',
    event => ready.push(event),
  );

  listeners.get('style.load')();
  assert.deepEqual(ready, [{ key: 'explore', requestId: 0 }]);

  coordinator.switchTo(
    'pastel',
    createRasterStyle(
      'pastel',
      'pastel-source',
      ['https://example.test/{z}/{x}/{y}.png'],
      '',
    ),
  );
  listeners.get('style.load')();
  assert.deepEqual(ready, [
    { key: 'explore', requestId: 0 },
    { key: 'pastel', requestId: 1 },
  ]);
});


test('styledata restores overlays when style.load never arrives', () => {
  const listeners = new Map();
  const ready = [];
  let currentStyle = createRasterStyle(
    'explore',
    'explore-source',
    ['https://example.test/{z}/{x}/{y}.png'],
    '',
  );

  const map = {
    on(eventName, listener) {
      listeners.set(eventName, listener);
    },
    getCenter: () => ({ toArray: () => [121.6, 31.2] }),
    getZoom: () => 10,
    getBearing: () => 0,
    getPitch: () => 0,
    getStyle: () => currentStyle,
    jumpTo() {},
    setStyle(style) {
      currentStyle = style;
    },
  };

  const coordinator = new StyleSwitchCoordinator(
    map,
    'explore',
    event => ready.push(event),
  );

  coordinator.switchTo(
    'apple',
    createRasterStyle(
      'apple',
      'apple-source',
      ['https://example.test/{z}/{x}/{y}.png'],
      '',
    ),
  );

  listeners.get('styledata')();
  assert.deepEqual(ready, [{ key: 'apple', requestId: 1 }]);

  listeners.get('style.load')();
  assert.equal(ready.length, 1);
});


test('overlay restoration does not wait for all basemap tiles', () => {
  const mainSource = readFileSync(
    new URL('../web/src/main.js', import.meta.url),
    'utf8',
  );
  const restoreBody = mainSource.match(
    /function restoreCustomLayers\(\) \{[\s\S]*?\n\}/,
  )?.[0];

  assert.ok(restoreBody);
  assert.doesNotMatch(restoreBody, /!map\.isStyleLoaded\(\)/);
  assert.match(restoreBody, /!map\?\.getStyle\(\)/);
});


test('station layer handlers bind once across repeated overlay restores', () => {
  const registrations = [];
  const map = {
    on(eventName, layerId, handler) {
      registrations.push({ eventName, layerId, handler });
    },
  };
  const handler = () => {};

  assert.equal(
    bindLayerHandlerOnce(map, 'click', 'station-circle', handler),
    true,
  );
  assert.equal(
    bindLayerHandlerOnce(map, 'click', 'station-circle', handler),
    false,
  );
  assert.equal(registrations.length, 1);
});


test('normal and inverse paint states are mutually exclusive', () => {
  const normal = polygonPaintForState({
    showPoly: true,
    invertFill: false,
    opacity: 0.4,
    width: 2,
  });
  const inverse = polygonPaintForState({
    showPoly: true,
    invertFill: true,
    opacity: 0.4,
    width: 2,
  });
  const hidden = polygonPaintForState({
    showPoly: false,
    invertFill: true,
    opacity: 0.4,
    width: 2,
  });

  assert.deepEqual(normal, {
    reachFillOpacity: 0.4,
    inverseFillOpacity: 0,
    outlineWidth: 2,
  });
  assert.deepEqual(inverse, {
    reachFillOpacity: 0,
    inverseFillOpacity: 0.4,
    outlineWidth: 2,
  });
  assert.deepEqual(hidden, {
    reachFillOpacity: 0,
    inverseFillOpacity: 0,
    outlineWidth: 0,
  });
});


test('limit selection updates both normal and inverse collections', () => {
  const collection = {
    type: 'FeatureCollection',
    features: [10, 20, 30, 40, 50].map(limit => ({
      type: 'Feature',
      properties: { limit },
      geometry: { type: 'Polygon', coordinates: [] },
    })),
  };

  assert.equal(selectedFeatureCollection(collection, 20).features.length, 1);
  assert.equal(
    selectedFeatureCollection(collection, 20).features[0].properties.limit,
    20,
  );
});


const station = (name, apple, isJinke = false) => ({
  type: 'Feature',
  properties: { station: name, apple, is_jinke: isJinke },
  geometry: { type: 'Point', coordinates: [121.5, 31.2] },
});


test('station search supports normalized partial matching', () => {
  const features = [
    station('南京西路', 30),
    station('静安寺', 30),
    station('West Nanjing Road', 35),
  ];

  assert.equal(findStationMatch(features, '静安').properties.station, '静安寺');
  assert.equal(
    findStationMatch(features, 'NANJING').properties.station,
    'West Nanjing Road',
  );
  assert.equal(normalizeStationQuery('  ＡBC '), 'abc');
  assert.deepEqual(
    matchingStations(features, '南京').map(value => value.properties.station),
    ['南京西路'],
  );
  assert.equal(findStationMatch(features, 'not-a-station'), null);
});


test('relevant station display keeps origin, included, and boundary only', () => {
  const collection = {
    type: 'FeatureCollection',
    features: [
      station('金科路', 99, true),
      station('Included', 29),
      station('Boundary', 30),
      station('Outside', 31),
    ],
  };

  const relevant = stationFeatureCollection(collection, 30, 'relevant');
  const all = stationFeatureCollection(collection, 30, 'all');

  assert.deepEqual(
    relevant.features.map(value => value.properties.station),
    ['金科路', 'Included', 'Boundary'],
  );
  assert.equal(all.features.length, 4);
  assert.equal(all.features[3].properties.status, 'excluded');
  assert.equal(
    enrichStationFeature(collection.features[1], 30).properties
      .remaining_walk_minutes,
    1,
  );
});


const metroLines = JSON.parse(
  readFileSync(
    new URL('../web/public/data/shanghai-metro-lines.geojson', import.meta.url),
    'utf8',
  ),
);
const metroStations = JSON.parse(
  readFileSync(
    new URL('../web/public/data/shanghai-metro-stations.geojson', import.meta.url),
    'utf8',
  ),
);


test('warm vector styles use attributed OpenFreeMap tiles and local transit data', () => {
  const warm = createWarmVectorStyle('apple');
  assert.equal(warm.metadata.jinkeBasemap, 'apple');
  assert.equal(warm.sources.openfreemap.type, 'vector');
  assert.equal(
    warm.sources.openfreemap.url,
    'https://tiles.openfreemap.org/planet',
  );
  assert.match(warm.sources.openfreemap.attribution, /OpenFreeMap/);
  assert.match(warm.sources.openfreemap.attribution, /OpenStreetMap/);
  assert.equal(warm.sources['shanghai-metro-lines'], undefined);

  const transit = createWarmVectorStyle('apple-transit', {
    transit: true,
    metroLines,
    metroStations,
  });
  assert.equal(transit.metadata.jinkeBasemap, 'apple-transit');
  assert.equal(transit.sources['shanghai-metro-lines'].data, metroLines);
  assert.equal(
    transit.sources['shanghai-metro-stations'].data,
    metroStations,
  );

  const layerIds = transit.layers.map(layer => layer.id);
  assert.ok(
    layerIds.indexOf('metro-lines') <
      layerIds.indexOf('metro-station-labels'),
  );
  assert.deepEqual(
    transit.layers.find(layer => layer.id === 'metro-lines').paint[
      'line-color'
    ],
    ['get', 'color'],
  );
});


test('static Shanghai metro GeoJSON is licensed, valid, and complete', () => {
  assert.equal(metroLines.metadata.source.license, 'MIT');
  assert.equal(metroLines.metadata.source.retrieved_date, '2026-08-05');
  assert.equal(metroStations.metadata.source.license, 'MIT');
  assert.equal(metroLines.features.length, 19);
  assert.deepEqual(
    new Set(metroLines.features.map(feature => feature.properties.line_id)),
    new Set([
      ...Array.from({ length: 18 }, (_, index) => String(index + 1)),
      'pujiang',
    ]),
  );

  const expectedColors = {
    1: '#E3002B',
    2: '#8CC220',
    3: '#FCD600',
    4: '#461D84',
    5: '#944D9A',
    6: '#D40068',
    7: '#ED6F00',
    8: '#0094D8',
    9: '#87CAED',
    10: '#C6AFD4',
    11: '#871C2B',
    12: '#007B61',
    13: '#E999C0',
    14: '#626020',
    15: '#BCA886',
    16: '#98D1C0',
    17: '#BC796F',
    18: '#C4984F',
    pujiang: '#B3B3C5',
  };
  assert.deepEqual(
    Object.fromEntries(
      metroLines.features.map(feature => [
        feature.properties.line_id,
        feature.properties.color,
      ]),
    ),
    expectedColors,
  );

  assert.ok(metroLines.features.every(feature =>
    ['LineString', 'MultiLineString'].includes(feature.geometry.type),
  ));
  assert.ok(metroStations.features.length > 400);
  assert.ok(
    metroStations.features.every(feature => feature.geometry.type === 'Point'),
  );
  assert.ok(
    metroStations.features.some(feature => feature.properties.interchange),
  );
});


test('rapid warm-vector switching still restores only the newest request', () => {
  const listeners = new Map();
  const ready = [];
  const jumps = [];
  let loaded = true;
  let style = createRasterStyle('explore', 'explore-source', [], '');
  const map = {
    on(eventName, handler) {
      listeners.set(eventName, handler);
    },
    getCenter: () => ({ toArray: () => [121.6, 31.2] }),
    getZoom: () => 10,
    getBearing: () => 8,
    getPitch: () => 18,
    setStyle() {
      loaded = false;
    },
    getStyle: () => style,
    isStyleLoaded: () => loaded,
    jumpTo(camera) {
      jumps.push(camera);
    },
  };
  const coordinator = new StyleSwitchCoordinator(
    map,
    'explore',
    event => ready.push(event),
  );

  coordinator.switchTo('apple', createWarmVectorStyle('apple'));
  coordinator.switchTo(
    'apple-transit',
    createWarmVectorStyle('apple-transit'),
  );
  style = createWarmVectorStyle('apple-transit');
  loaded = true;
  listeners.get('styledata')();
  listeners.get('style.load')();

  assert.deepEqual(ready, [{ key: 'apple-transit', requestId: 2 }]);
  assert.deepEqual(jumps, [
    { center: [121.6, 31.2], zoom: 10, bearing: 8, pitch: 18 },
  ]);
});


const squareBoundary = {
  type: 'Feature',
  geometry: {
    type: 'Polygon',
    coordinates: [[
      [120.8, 30.7],
      [122.2, 30.7],
      [122.2, 31.9],
      [120.8, 31.9],
      [120.8, 30.7],
    ]],
  },
};

function poi(name, wgs84, overrides = {}) {
  const gcj02 = wgs84ToGcj02(...wgs84);
  return {
    id: name,
    name,
    location: `${gcj02[0]},${gcj02[1]}`,
    type: '商务住宅;楼宇;商务写字楼',
    adname: '浦东新区',
    address: '张江路1号',
    ...overrides,
  };
}

function response(pois) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ status: '1', info: 'OK', infocode: '10000', pois }),
  };
}

test('client routes Chinese and English searches through the current Site origin without a key', () => {
  for (const query of ['惠生', 'Wison']) {
    const url = buildLocationSearchUrl(query, {
      endpoint: '/api/location-search',
      origin: 'https://jinke.example',
      bbox: [120.8, 30.7, 122.2, 31.9],
      proximity: [121.6, 31.2],
      limit: 8,
    });
    assert.equal(url.origin, 'https://jinke.example');
    assert.equal(url.pathname, '/api/location-search');
    assert.equal(url.searchParams.get('q'), query);
    assert.equal(url.searchParams.has('key'), false);
  }
});

test('client rejects missing and cross-origin search configuration', () => {
  assert.throws(
    () => buildLocationSearchUrl('惠生'),
    error => error instanceof LocationSearchError && error.code === 'missing-config',
  );
  assert.throws(
    () => buildLocationSearchUrl('惠生', {
      endpoint: 'https://other.example/search',
      origin: 'https://jinke.example',
    }),
    error => error instanceof LocationSearchError && error.code === 'missing-config',
  );
});

test('GCJ-02 coordinates are converted back to WGS-84 before map placement', () => {
  const original = [121.597836, 31.2064028];
  const gcj02 = wgs84ToGcj02(...original);
  const converted = gcj02ToWgs84(...gcj02);
  assert.ok(Math.abs(gcj02[0] - original[0]) > 0.003);
  assert.ok(Math.abs(converted[0] - original[0]) < 1e-7);
  assert.ok(Math.abs(converted[1] - original[1]) < 1e-7);
});

test('Shanghai filtering preserves Gaode relevance order and removes nearby non-Shanghai POIs', () => {
  const results = filterShanghaiAmapResults([
    poi('first-shanghai', [121.60, 31.20]),
    poi('nearby-jiangsu', [120.70, 31.50], { adname: '昆山市' }),
    poi('second-shanghai', [121.45, 31.24]),
  ], squareBoundary, 8);
  assert.deepEqual(results.map(result => result.name), [
    'first-shanghai',
    'second-shanghai',
  ]);
  assert.equal(results.every(result => result.provider === 'amap'), true);
});

test('Gaode client returns normalized Shanghai POIs through the same-origin endpoint', async () => {
  const requests = [];
  const search = new AmapLocationSearch({
    endpointProvider: () => '/api/location-search',
    boundary: squareBoundary,
    fetchFn: async url => {
      requests.push(new URL(url));
      return response([poi('惠生中心', [121.5959, 31.1821])]);
    },
  });

  const result = await search.search('Wison', {
    bbox: [120.8, 30.7, 122.2, 31.9],
    proximity: [121.6, 31.2],
  });
  assert.equal(result.status, 'ok');
  assert.equal(result.results[0].name, '惠生中心');
  assert.equal(requests.length, 1);
  assert.equal(requests[0].origin, 'http://localhost');
  assert.equal(requests[0].searchParams.has('key'), false);
});

test('browser fetch keeps the global receiver and sends the same-origin request', async () => {
  let requestedUrl;
  function browserFetch(url) {
    assert.equal(this, globalThis);
    requestedUrl = new URL(url);
    return Promise.resolve(response([poi('东郊宾馆', [121.62, 31.22])]));
  }

  const search = new AmapLocationSearch({
    endpointProvider: () => '/api/location-search',
    boundary: squareBoundary,
    fetchFn: browserFetch,
  });

  const result = await search.search('东郊宾馆');
  assert.equal(result.status, 'ok');
  assert.equal(result.results[0].name, '东郊宾馆');
  assert.equal(requestedUrl.pathname, '/api/location-search');
  assert.equal(requestedUrl.searchParams.get('q'), '东郊宾馆');
});

test('stale Gaode responses cannot overwrite a newer query', async () => {
  let resolveOld;
  const search = new AmapLocationSearch({
    endpointProvider: () => '/api/location-search',
    boundary: squareBoundary,
    fetchFn: async url => {
      const query = new URL(url).searchParams.get('q');
      if (query === '旧地址') {
        return new Promise(resolve => { resolveOld = resolve; });
      }
      return response([poi('新结果', [121.59, 31.21])]);
    },
  });

  const oldRequest = search.search('旧地址');
  const newRequest = search.search('new address');
  const latest = await newRequest;
  resolveOld(response([poi('旧结果', [121.50, 31.20])]));
  const stale = await oldRequest;
  assert.equal(latest.results[0].name, '新结果');
  assert.equal(stale.status, 'stale');
});

test('selection creates exactly one marker, replaces it, and clears only its visuals', () => {
  const markers = [];
  const popups = [];
  const selection = new SingleLocationSelection({
    createVisual: result => {
      const marker = { result, removed: false, remove() { this.removed = true; } };
      const popup = { result, removed: false, remove() { this.removed = true; } };
      markers.push(marker);
      popups.push(popup);
      return { marker, popup };
    },
  });

  selection.select({ name: 'A' });
  selection.select({ name: 'B' });
  assert.equal(markers.length, 2);
  assert.equal(markers[0].removed, true);
  assert.equal(popups[0].removed, true);
  assert.equal(selection.marker.result.name, 'B');
  selection.clear();
  assert.equal(markers[1].removed, true);
  assert.equal(popups[1].removed, true);
  assert.equal(selection.activeResult, null);
});

test('failed search configuration degrades without changing map state', async () => {
  const search = new AmapLocationSearch({
    endpointProvider: () => '',
    boundary: squareBoundary,
    fetchFn: async () => { throw new Error('should not run'); },
  });
  await assert.rejects(
    search.search('惠生'),
    error => error instanceof LocationSearchError && error.code === 'missing-config',
  );
});


test('location selection survives overlay updates and restores only when absent', () => {
  let present = true;
  let creates = 0;
  const selection = new SingleLocationSelection({
    createVisual() {
      creates += 1;
      return { marker: { remove() {} }, popup: { remove() {} } };
    },
    isPresent: () => present,
  });
  selection.select({ id: 'selected' });
  polygonPaintForState({ showPoly: true, invertFill: true, opacity: 0.4, width: 2 });
  stationFeatureCollection(
    { type: 'FeatureCollection', features: [station('A', 20)] },
    30,
    'relevant',
  );
  selection.ensure();
  assert.equal(creates, 1);
  present = false;
  selection.ensure();
  assert.equal(creates, 2);
  assert.equal(selection.activeResult.id, 'selected');
});


test('rate-limited, failed, and invalid Gaode responses degrade safely', async () => {
  for (const [status, code] of [[429, 'rate-limit'], [503, 'service-unavailable'], [400, 'request-failed']]) {
    const search = new AmapLocationSearch({
      endpointProvider: () => '/api/location-search',
      boundary: squareBoundary,
      fetchFn: async () => ({ ok: false, status }),
    });
    await assert.rejects(
      search.search('上海'),
      error => error instanceof LocationSearchError && error.code === code,
    );
  }
  const invalid = new AmapLocationSearch({
    endpointProvider: () => '/api/location-search',
    boundary: squareBoundary,
    fetchFn: async () => ({
      ok: true,
      status: 200,
      json: async () => ({ status: '1', pois: 'not-an-array' }),
    }),
  });
  await assert.rejects(
    invalid.search('上海'),
    error => error instanceof LocationSearchError && error.code === 'invalid-response',
  );
});


test('runtime config declares one same-origin endpoint and no browser API key', () => {
  const runtimeConfig = readFileSync(new URL('../runtime-config.js', import.meta.url), 'utf8');
  const mainSource = readFileSync(new URL('../web/src/main.js', import.meta.url), 'utf8');
  assert.equal(
    runtimeConfig.trim(),
    "window.JINKE_LOCATION_SEARCH_ENDPOINT ??= '';\nwindow.JINKE_LOCATION_SEARCH_PROVIDER ??= 'amap';",
  );
  assert.equal((runtimeConfig.match(/JINKE_LOCATION_SEARCH_ENDPOINT/g) || []).length, 1);
  assert.equal((runtimeConfig.match(/JINKE_LOCATION_SEARCH_PROVIDER/g) || []).length, 1);
  assert.doesNotMatch(runtimeConfig, /KEY|maptiler/i);
  assert.doesNotMatch(mainSource, /JINKE_MAPTILER_KEY|MapTilerLocationSearch/);
  assert.match(mainSource, /AmapLocationSearch/);
});
