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
  LocationSearchError,
  MapTilerLocationSearch,
  SingleLocationSelection,
  buildMapTilerGeocodingUrl,
  filterShanghaiResults,
  geoJsonBounds,
  locationQueryLength,
  pointInGeoJson,
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
  const listeners = [];
  const styles = [];
  const jumps = [];
  const ready = [];
  let currentStyle = createRasterStyle('explore', 'explore-source', [], '');
  let loaded = true;
  const map = {
    on(eventName, listener) {
      assert.equal(eventName, 'style.load');
      listeners.push(listener);
    },
    getCenter: () => ({ toArray: () => [121.6, 31.2] }),
    getZoom: () => 10,
    getBearing: () => 15,
    getPitch: () => 25,
    setStyle(style) {
      styles.push(style);
      loaded = false;
    },
    getStyle: () => currentStyle,
    isStyleLoaded: () => loaded,
    jumpTo(camera) {
      jumps.push(camera);
    },
  };

  const coordinator = new StyleSwitchCoordinator(
    map,
    'explore',
    value => ready.push(value),
  );
  assert.equal(listeners.length, 1);

  const dark = createRasterStyle('dark', 'dark-source', [], '');
  const pastel = createRasterStyle('pastel', 'voyager-source', [], '');
  coordinator.switchTo('dark', dark);
  coordinator.switchTo('pastel', pastel);
  assert.equal(styles.length, 2);

  currentStyle = dark;
  loaded = true;
  listeners[0]();
  assert.equal(ready.length, 0);

  currentStyle = pastel;
  listeners[0]();
  assert.deepEqual(ready, [{ key: 'pastel', requestId: 2 }]);
  assert.deepEqual(jumps, [
    { center: [121.6, 31.2], zoom: 10, bearing: 15, pitch: 25 },
  ]);

  listeners[0]();
  assert.equal(ready.length, 1);
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
  const listeners = [];
  const ready = [];
  const jumps = [];
  let loaded = true;
  let style = createRasterStyle('explore', 'explore-source', [], '');
  const map = {
    on(eventName, handler) {
      assert.equal(eventName, 'style.load');
      listeners.push(handler);
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
  listeners[0]();
  listeners[0]();

  assert.deepEqual(ready, [{ key: 'apple-transit', requestId: 2 }]);
  assert.deepEqual(jumps, [
    { center: [121.6, 31.2], zoom: 10, bearing: 8, pitch: 18 },
  ]);
});


const squareBoundary = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: {},
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [120.8, 30.7],
            [122.2, 30.7],
            [122.2, 31.9],
            [120.8, 31.9],
            [120.8, 30.7],
          ],
        ],
      },
    },
  ],
};

const locationFeature = (id, name, coordinates, placeType = 'poi') => ({
  type: 'Feature',
  id,
  center: coordinates,
  geometry: { type: 'Point', coordinates },
  text: name,
  text_zh: name,
  place_name: `${name}, Shanghai, China`,
  place_type: [placeType],
  properties: { categories: ['landmark'] },
  context: [
    { id: 'municipal_district.1', text: 'Pudong', text_zh: '浦东新区' },
  ],
});


test('MapTiler URL reuses one supplied runtime key and applies Shanghai filters', () => {
  const url = buildMapTilerGeocodingUrl('上海博物馆', {
    key: 'existing-browser-key',
    bbox: geoJsonBounds(squareBoundary),
    proximity: [121.48, 31.23],
    limit: 8,
  });

  assert.equal(url.origin, 'https://api.maptiler.com');
  assert.equal(url.searchParams.get('key'), 'existing-browser-key');
  assert.equal(url.searchParams.getAll('key').length, 1);
  assert.equal(url.searchParams.get('country'), 'cn');
  assert.equal(url.searchParams.get('bbox'), '120.8,30.7,122.2,31.9');
  assert.equal(url.searchParams.get('proximity'), '121.48,31.23');
  assert.equal(url.searchParams.get('language'), 'zh,en');
  assert.match(url.searchParams.get('types'), /poi/);
  assert.equal(url.searchParams.get('limit'), '8');
  assert.equal(locationQueryLength('中文'), 2);
  assert.equal(locationQueryLength('EN'), 2);
});


test('Shanghai filtering removes all nearby non-Shanghai results without reordering', () => {
  const features = [
    locationFeature('inside-1', 'First', [121.47, 31.23]),
    locationFeature('outside-jiangsu', 'Suzhou', [120.58, 31.3]),
    locationFeature('inside-2', 'Second', [121.6, 31.1]),
    locationFeature('outside-zhejiang', 'Jiaxing', [120.75, 30.75]),
    locationFeature('inside-3', 'Third', [121.8, 31.4]),
  ];

  const results = filterShanghaiResults(features, squareBoundary, 8);
  assert.deepEqual(
    results.map(result => result.id),
    ['inside-1', 'inside-2', 'inside-3'],
  );
  assert.ok(results.every(result => pointInGeoJson(result.coordinates, squareBoundary)));
  assert.equal(results[0].category, 'Landmark');
  assert.equal(results[0].district, '浦东新区');
});


test('stale MapTiler responses cannot overwrite a newer Chinese or English query', async () => {
  const pending = [];
  const fetchFn = url =>
    new Promise(resolve => pending.push({ url, resolve }));
  const search = new MapTilerLocationSearch({
    keyProvider: () => 'existing-browser-key',
    boundary: squareBoundary,
    fetchFn,
  });

  const older = search.search('中文', {
    bbox: geoJsonBounds(squareBoundary),
    proximity: [121.5, 31.2],
  });
  const newer = search.search('English', {
    bbox: geoJsonBounds(squareBoundary),
    proximity: [121.5, 31.2],
  });
  assert.equal(pending.length, 2);

  pending[1].resolve({
    ok: true,
    status: 200,
    json: async () => ({
      type: 'FeatureCollection',
      features: [locationFeature('newer', 'Newer', [121.5, 31.2])],
    }),
  });
  assert.deepEqual((await newer).results.map(result => result.id), ['newer']);

  pending[0].resolve({
    ok: true,
    status: 200,
    json: async () => ({
      type: 'FeatureCollection',
      features: [locationFeature('older', 'Older', [121.5, 31.2])],
    }),
  });
  assert.equal((await older).status, 'stale');
});


test('single location selection replaces markers and clearing removes only its visuals', () => {
  const created = [];
  const removed = [];
  const selection = new SingleLocationSelection({
    createVisual(result) {
      created.push(result.id);
      return {
        marker: { remove: () => removed.push(`marker:${result.id}`) },
        popup: { remove: () => removed.push(`popup:${result.id}`) },
      };
    },
  });

  selection.select({ id: 'first' });
  assert.equal(selection.activeResult.id, 'first');
  selection.select({ id: 'second' });
  assert.equal(selection.activeResult.id, 'second');
  assert.deepEqual(created, ['first', 'second']);
  assert.deepEqual(removed, ['marker:first', 'popup:first']);

  const unrelatedMapState = { limit: 30, inverse: true, labels: false };
  selection.clear();
  assert.equal(selection.activeResult, null);
  assert.deepEqual(removed.slice(-2), ['marker:second', 'popup:second']);
  assert.deepEqual(unrelatedMapState, { limit: 30, inverse: true, labels: false });
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

  polygonPaintForState({
    showPoly: true,
    invertFill: true,
    opacity: 0.4,
    width: 2,
  });
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


test('missing, failed, rate-limited, and invalid search configuration degrade safely', async () => {
  assert.throws(
    () => buildMapTilerGeocodingUrl('上海', { key: '' }),
    error => error instanceof LocationSearchError && error.code === 'missing-config',
  );

  for (const [status, code] of [
    [429, 'rate-limit'],
    [503, 'request-failed'],
  ]) {
    const search = new MapTilerLocationSearch({
      keyProvider: () => 'existing-browser-key',
      boundary: squareBoundary,
      fetchFn: async () => ({ ok: false, status }),
    });
    await assert.rejects(
      search.search('上海', { bbox: geoJsonBounds(squareBoundary) }),
      error => error instanceof LocationSearchError && error.code === code,
    );
  }

  const invalid = new MapTilerLocationSearch({
    keyProvider: () => 'existing-browser-key',
    boundary: squareBoundary,
    fetchFn: async () => ({
      ok: true,
      status: 200,
      json: async () => ({ features: 'not-an-array' }),
    }),
  });
  await assert.rejects(
    invalid.search('上海', { bbox: geoJsonBounds(squareBoundary) }),
    error =>
      error instanceof LocationSearchError && error.code === 'invalid-response',
  );
});


test('runtime config has one empty assignment and the browser key is not duplicated', () => {
  const runtimeConfig = readFileSync(
    new URL('../runtime-config.js', import.meta.url),
    'utf8',
  );
  const mainSource = readFileSync(
    new URL('../web/src/main.js', import.meta.url),
    'utf8',
  );
  assert.equal(runtimeConfig.trim(), "window.JINKE_MAPTILER_KEY ??= '';");
  assert.equal((runtimeConfig.match(/JINKE_MAPTILER_KEY/g) || []).length, 1);
  assert.match(mainSource, /window\.JINKE_MAPTILER_KEY/);
  assert.equal(runtimeConfig.includes('existing-browser-key'), false);
});
