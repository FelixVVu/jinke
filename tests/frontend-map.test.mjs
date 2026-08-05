import assert from 'node:assert/strict';
import test from 'node:test';

import {
  StyleSwitchCoordinator,
  bindLayerHandlerOnce,
  createRasterStyle,
  enrichStationFeature,
  findStationMatch,
  matchingStations,
  normalizeStationQuery,
  polygonPaintForState,
  selectedFeatureCollection,
  stationFeatureCollection,
} from '../web/src/map-utils.js';


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
