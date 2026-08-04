import {
  StyleSwitchCoordinator,
  bindLayerHandlerOnce,
  createRasterStyle,
  polygonPaintForState,
  selectedFeatureCollection,
} from './map-utils.js';

const base = window.JINKE_BASE || '/';
const assetUrl = path =>
  `${base}${path}`.replace(/\/+/g, '/').replace(':/', '://');

const defaults = {
  limit: 50,
  basemap: 'explore',
  fill: '#68c7c1',
  outline: '#16877f',
  opacity: 0.38,
  width: 2,
  showPoly: true,
  invertFill: false,
  showStations: true,
  showLabels: true,
  stationSize: 7,
};

function savedAppearance() {
  try {
    return JSON.parse(localStorage.getItem('jinkeAppearance') || '{}');
  } catch {
    return {};
  }
}

const state = { ...defaults, ...savedAppearance() };

const osmAttribution =
  '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const cartoAttribution =
  `${osmAttribution} © <a href="https://carto.com/attributions">CARTO</a>`;
const esriAttribution =
  'Tiles © <a href="https://www.esri.com/">Esri</a> and its data providers';

const basemaps = {
  transit: {
    attribution: '© OpenStreetMap contributors. Apple-inspired controls only; no Apple Maps data.',
    style: () =>
      createRasterStyle(
        'transit',
        'osm-standard',
        ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
        osmAttribution,
      ),
  },
  explore: {
    attribution: '© OpenStreetMap contributors © CARTO. Apple Explore-inspired visual treatment only.',
    style: () =>
      createRasterStyle(
        'explore',
        'carto-positron',
        [
          'https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
          'https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
        ],
        cartoAttribution,
      ),
  },
  dark: {
    attribution: '© OpenStreetMap contributors © CARTO',
    style: () =>
      createRasterStyle(
        'dark',
        'carto-dark-matter',
        ['https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'],
        cartoAttribution,
      ),
  },
  satellite: {
    attribution: 'Tiles © Esri and its data providers',
    style: () =>
      createRasterStyle(
        'satellite',
        'esri-world-imagery',
        [
          'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        ],
        esriAttribution,
      ),
  },
  pastel: {
    attribution: '© OpenStreetMap contributors © CARTO — Voyager',
    style: () =>
      createRasterStyle(
        'pastel',
        'carto-voyager',
        [
          'https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
          'https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
          'https://c.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
          'https://d.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
        ],
        cartoAttribution,
      ),
  },
  mono: {
    attribution: '© OpenStreetMap contributors © CARTO',
    style: () =>
      createRasterStyle(
        'mono',
        'carto-positron-no-labels',
        ['https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png'],
        cartoAttribution,
      ),
  },
};

if (!basemaps[state.basemap]) state.basemap = defaults.basemap;
if (![10, 20, 30, 40, 50].includes(Number(state.limit))) {
  state.limit = defaults.limit;
}

document.querySelector('#app').innerHTML = `
  <main>
    <section id="map" aria-label="Reach area map"></section>
    <aside class="panel" aria-label="Map controls">
      <div id="sample" class="sample" hidden role="alert"></div>
      <h1>金科路 Reach Map</h1>
      <p id="stats" aria-live="polite">Loading…</p>
      <div class="segments" role="group" aria-label="Total time limit">
        ${[10, 20, 30, 40, 50]
          .map(
            limit =>
              `<button data-limit="${limit}" aria-pressed="false">${limit}</button>`,
          )
          .join('')}
      </div>
      <label>Basemap
        <select id="basemap">
          ${Object.keys(basemaps)
            .map(key => `<option value="${key}">${key}</option>`)
            .join('')}
        </select>
      </label>
      <p class="provider" id="provider"></p>
      <label>Station search
        <input id="search" list="stations" placeholder="Search station"/>
        <datalist id="stations"></datalist>
      </label>
      <label>Fill<input id="fill" type="color"/></label>
      <label>Outline<input id="outline" type="color"/></label>
      <label>Opacity<input id="opacity" type="range" min="0" max="1" step="0.01"/></label>
      <label>Outline width<input id="width" type="range" min="0" max="8" step="0.5"/></label>
      <label>Station size<input id="stationSize" type="range" min="3" max="18" step="1"/></label>
      <label class="toggle"><input id="showPoly" type="checkbox"/> Show polygon</label>
      <label class="toggle"><input id="invertFill" type="checkbox"/> Invert fill — Shanghai only</label>
      <label class="toggle"><input id="showStations" type="checkbox"/> Show stations</label>
      <label class="toggle"><input id="showLabels" type="checkbox"/> Show labels</label>
      <div class="actions">
        <button id="fit">Fit to area</button>
        <button id="full">Fullscreen</button>
        <button id="reset">Reset appearance</button>
      </div>
    </aside>
  </main>`;

let map;
let styleSwitch;
let stations;
let areas;
let outsideAreas;
let manifest;
let controlsWired = false;

const save = () =>
  localStorage.setItem('jinkeAppearance', JSON.stringify(state));

const selectedAreas = () => selectedFeatureCollection(areas, state.limit);
const selectedOutsideAreas = () =>
  selectedFeatureCollection(outsideAreas, state.limit);

function stationData() {
  return {
    type: 'FeatureCollection',
    features: stations.features.map(feature => {
      const apple = Number(feature.properties.apple);
      return {
        ...feature,
        properties: {
          ...feature.properties,
          selected_limit: state.limit,
          remaining_walk_minutes: Math.max(0, state.limit - apple),
          status:
            apple < state.limit
              ? 'included'
              : apple === state.limit
                ? 'boundary'
                : 'excluded',
        },
      };
    }),
  };
}

function setPaintProperty(layerId, property, value) {
  if (map.getLayer(layerId)) map.setPaintProperty(layerId, property, value);
}

function renderState() {
  document.querySelectorAll('[data-limit]').forEach(button => {
    const active = button.dataset.limit === String(state.limit);
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });

  document.getElementById('provider').textContent =
    basemaps[state.basemap].attribution;

  if (areas) {
    const feature = selectedAreas().features[0];
    document.getElementById('stats').textContent =
      `${state.limit} min: ${feature.properties.included_stations} included, ` +
      `${feature.properties.boundary_stations} boundary stations`;
  }

  save();
}

function applyMapState() {
  renderState();
  if (!areas || !outsideAreas || !stations) return;

  map.getSource('areas')?.setData(selectedAreas());
  map.getSource('outside-areas')?.setData(selectedOutsideAreas());
  map.getSource('stations')?.setData(stationData());

  const polygonPaint = polygonPaintForState(state);
  setPaintProperty('reach-fill', 'fill-color', state.fill);
  setPaintProperty(
    'reach-fill',
    'fill-opacity',
    polygonPaint.reachFillOpacity,
  );
  setPaintProperty('outside-fill', 'fill-color', state.fill);
  setPaintProperty(
    'outside-fill',
    'fill-opacity',
    polygonPaint.inverseFillOpacity,
  );
  setPaintProperty('reach-line', 'line-color', state.outline);
  setPaintProperty('reach-line', 'line-width', polygonPaint.outlineWidth);
  setPaintProperty(
    'station-circle',
    'circle-radius',
    state.showStations
      ? ['case', ['get', 'is_jinke'], state.stationSize + 3, state.stationSize]
      : 0,
  );
  if (map.getLayer('station-label')) {
    map.setLayoutProperty(
      'station-label',
      'visibility',
      state.showLabels ? 'visible' : 'none',
    );
  }
}

function addSourceOnce(id, definition) {
  if (!map.getSource(id)) map.addSource(id, definition);
}

function addLayerOnce(definition) {
  if (!map.getLayer(definition.id)) map.addLayer(definition);
}

function handleStationClick(event) {
  const feature = event.features?.[0];
  if (!feature) return;
  const properties = feature.properties;
  new maplibregl.Popup()
    .setLngLat(feature.geometry.coordinates)
    .setHTML(
      `<b>${properties.station}</b><br/>` +
        `Apple transit: ${properties.apple} min<br/>` +
        `Remaining walk: ${Math.max(0, state.limit - properties.apple)} min<br/>` +
        `Selected limit: ${state.limit} min`,
    )
    .addTo(map);
}

function restoreCustomLayers() {
  if (!areas || !outsideAreas || !stations || !map.isStyleLoaded()) return;

  addSourceOnce('areas', { type: 'geojson', data: selectedAreas() });
  addSourceOnce('outside-areas', {
    type: 'geojson',
    data: selectedOutsideAreas(),
    attribution: 'Shanghai boundary: geoBoundaries (Public Domain)',
  });
  addSourceOnce('stations', { type: 'geojson', data: stationData() });

  addLayerOnce({
    id: 'outside-fill',
    type: 'fill',
    source: 'outside-areas',
    paint: { 'fill-color': state.fill, 'fill-opacity': 0 },
  });
  addLayerOnce({
    id: 'reach-fill',
    type: 'fill',
    source: 'areas',
    paint: { 'fill-color': state.fill, 'fill-opacity': state.opacity },
  });
  addLayerOnce({
    id: 'reach-line',
    type: 'line',
    source: 'areas',
    paint: { 'line-color': state.outline, 'line-width': state.width },
  });
  addLayerOnce({
    id: 'station-circle',
    type: 'circle',
    source: 'stations',
    paint: {
      'circle-color': [
        'case',
        ['get', 'is_jinke'],
        '#f59e0b',
        ['==', ['get', 'status'], 'included'],
        '#136f63',
        ['==', ['get', 'status'], 'boundary'],
        '#ffffff',
        '#9ca3af',
      ],
      'circle-stroke-color': [
        'case',
        ['==', ['get', 'status'], 'boundary'],
        '#111827',
        '#fff',
      ],
      'circle-stroke-width': 2,
      'circle-radius': state.stationSize,
    },
  });
  addLayerOnce({
    id: 'station-label',
    type: 'symbol',
    source: 'stations',
    layout: {
      'text-field': ['get', 'station'],
      'text-size': 12,
      'text-offset': [0, 1.2],
    },
    paint: { 'text-halo-color': '#fff', 'text-halo-width': 1 },
  });

  bindLayerHandlerOnce(map, 'click', 'station-circle', handleStationClick);
  applyMapState();
}

function extendBounds(bounds, coordinates) {
  if (
    Array.isArray(coordinates) &&
    coordinates.length >= 2 &&
    typeof coordinates[0] === 'number'
  ) {
    bounds.extend(coordinates);
    return;
  }
  coordinates.forEach(value => extendBounds(bounds, value));
}

function wireControls() {
  if (controlsWired) return;
  controlsWired = true;

  ['fill', 'outline', 'opacity', 'width', 'stationSize'].forEach(id => {
    const element = document.getElementById(id);
    element.value = state[id];
    element.oninput = () => {
      state[id] =
        element.type === 'range' ? Number(element.value) : element.value;
      applyMapState();
    };
  });

  ['showPoly', 'invertFill', 'showStations', 'showLabels'].forEach(id => {
    const element = document.getElementById(id);
    element.checked = Boolean(state[id]);
    element.onchange = () => {
      state[id] = element.checked;
      applyMapState();
    };
  });

  document.querySelectorAll('[data-limit]').forEach(button => {
    button.onclick = () => {
      state.limit = Number(button.dataset.limit);
      applyMapState();
    };
  });

  const basemap = document.getElementById('basemap');
  basemap.value = state.basemap;
  basemap.onchange = () => {
    if (!basemaps[basemap.value]) return;
    state.basemap = basemap.value;
    renderState();
    styleSwitch.switchTo(state.basemap, basemaps[state.basemap].style());
  };

  document.getElementById('fit').onclick = () => {
    const bounds = new maplibregl.LngLatBounds();
    extendBounds(bounds, selectedAreas().features[0].geometry.coordinates);
    map.fitBounds(bounds, { padding: 50 });
  };
  document.getElementById('full').onclick = () =>
    document.documentElement.requestFullscreen();
  document.getElementById('reset').onclick = () => {
    Object.assign(state, defaults);
    save();
    location.reload();
  };
  document.getElementById('search').onchange = event => {
    const feature = stations.features.find(
      candidate => candidate.properties.station === event.target.value,
    );
    if (feature) map.flyTo({ center: feature.geometry.coordinates, zoom: 13 });
  };
}

async function fetchJson(filename) {
  const response = await fetch(assetUrl(`data/${filename}`));
  if (!response.ok) {
    throw new Error(`Unable to load ${filename}: HTTP ${response.status}`);
  }
  return response.json();
}

Promise.all([
  fetchJson('reach-areas.geojson'),
  fetchJson('outside-reach-areas.geojson'),
  fetchJson('stations.geojson'),
  fetchJson('manifest.json'),
]).then(([reachData, outsideData, stationDataValue, manifestValue]) => {
  areas = reachData;
  outsideAreas = outsideData;
  stations = stationDataValue;
  manifest = manifestValue;

  if (!manifest.production_data) {
    const notice = document.getElementById('sample');
    notice.hidden = false;
    notice.textContent =
      'Development sample data — production ORS polygons have not been generated yet. Do not use this map as final coverage.';
  }

  document.getElementById('stations').innerHTML = stations.features
    .map(feature => `<option value="${feature.properties.station}">`)
    .join('');
  try {
    map = new maplibregl.Map({
      container: 'map',
      style: basemaps[state.basemap].style(),
      center: [121.597836, 31.2064028],
      zoom: 10,
    });
    map.addControl(new maplibregl.NavigationControl(), 'bottom-right');
    styleSwitch = new StyleSwitchCoordinator(
      map,
      state.basemap,
      restoreCustomLayers,
    );
    wireControls();
    renderState();
    if (map.isStyleLoaded()) restoreCustomLayers();
  } catch {
    document.getElementById('stats').textContent =
      'Map rendering is not available in this browser.';
    document.getElementById('map').innerHTML =
      '<div class="map-fallback">This interactive map requires WebGL.</div>';
  }
}).catch(() => {
  document.getElementById('stats').textContent =
    'The map data could not be loaded.';
});
