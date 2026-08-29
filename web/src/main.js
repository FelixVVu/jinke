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
  stationPaintForState,
  stationFeatureCollection,
} from './map-utils.js';
import {
  AmapLocationSearch,
  LocationSearchError,
  SingleLocationSelection,
  geoJsonBounds,
  locationQueryLength,
  normalizeLocationQuery,
  pointInGeoJson,
} from './location-search.js';
import {
  formatSensitivityRange,
  formatShanghaiShare,
  formatTrillionCny,
  methodologyText,
  validateEconomyPayload,
} from './economy.js';
import {
  formatOfficeEmployment,
  formatOfficeShare,
  officeMethodologyText,
  validateOfficeDensityPayload,
  validateOfficeEmploymentPayload,
} from './office-employment.js';

const LIMITS = [10, 20, 30, 40, 50];
const base = window.JINKE_BASE || '/';
const assetUrl = path =>
  `${base}${path}`.replace(/\/+/g, '/').replace(':/', '://');
const runtimeLocationSearchEndpoint = () =>
  typeof window.JINKE_LOCATION_SEARCH_ENDPOINT === 'string'
    ? window.JINKE_LOCATION_SEARCH_ENDPOINT.trim()
    : '';
const runtimeCartoBasemapKey = () =>
  typeof window.JINKE_CARTO_BASEMAP_KEY === 'string'
    ? window.JINKE_CARTO_BASEMAP_KEY.trim()
    : '';
const cartoTileUrl = url => {
  const key = runtimeCartoBasemapKey();
  return key ? `${url}?key=${encodeURIComponent(key)}` : url;
};

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
  stationScaling: 'adaptive',
  stationDisplay: 'relevant',
  economicMetric: 'gdp',
  officeBenchmark: 'core_plus_base',
  showOfficeDensity: false,
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
    attribution: '© OpenStreetMap contributors',
    style: () =>
      createRasterStyle(
        'transit',
        'osm-standard',
        ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
        osmAttribution,
      ),
  },
  explore: {
    attribution: '© OpenStreetMap contributors © CARTO',
    style: () =>
      createRasterStyle(
        'explore',
        'carto-positron',
        [
          cartoTileUrl('https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png'),
          cartoTileUrl('https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png'),
        ],
        cartoAttribution,
      ),
  },
  apple: {
    attribution:
      'OpenFreeMap · OpenMapTiles · OpenStreetMap. Independent custom cartography.',
    style: () => createWarmVectorStyle('apple'),
  },
  'apple-transit': {
    attribution:
      'OpenFreeMap · OpenMapTiles · OpenStreetMap · Shanghai metro network and palette (MIT). Independent custom cartography.',
    style: () =>
      createWarmVectorStyle('apple-transit', {
        transit: true,
        metroLines,
        metroStations,
      }),
  },
  dark: {
    attribution: '© OpenStreetMap contributors © CARTO',
    style: () =>
      createRasterStyle(
        'dark',
        'carto-dark-matter',
        [cartoTileUrl('https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png')],
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
          cartoTileUrl('https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png'),
          cartoTileUrl('https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png'),
          cartoTileUrl('https://c.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png'),
          cartoTileUrl('https://d.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png'),
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
        [cartoTileUrl('https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png')],
        cartoAttribution,
      ),
  },
};

if (!basemaps[state.basemap]) state.basemap = defaults.basemap;
if (!LIMITS.includes(Number(state.limit))) state.limit = defaults.limit;
if (!['relevant', 'all'].includes(state.stationDisplay)) {
  state.stationDisplay = defaults.stationDisplay;
}
if (!['adaptive', 'fixed'].includes(state.stationScaling)) {
  state.stationScaling = defaults.stationScaling;
}
if (!['gdp', 'office'].includes(state.economicMetric)) {
  state.economicMetric = defaults.economicMetric;
}
if (!['core_plus_base', 'core'].includes(state.officeBenchmark)) {
  state.officeBenchmark = defaults.officeBenchmark;
}

document.querySelector('#app').innerHTML = `
  <main>
    <section class="map-shell" aria-label="Reach area map" aria-busy="true">
      <div id="map"></div>
      <div id="mapMessage" class="map-message" role="status" aria-live="polite">
        <span class="loading-spinner" aria-hidden="true"></span>
        <span id="mapMessageText">Loading map data…</span>
      </div>
    </section>
    <aside class="panel" aria-label="Map controls">
      <button
        id="sheetToggle"
        class="sheet-toggle"
        type="button"
        aria-controls="panelControls"
        aria-expanded="false"
      >
        <span>Map options</span>
        <span id="sheetToggleState" class="sheet-toggle-state">Expand</span>
      </button>
      <div id="sample" class="sample" hidden role="alert"></div>
      <header class="panel-header">
        <h1>金科路 Reach Map</h1>
        <p id="stats" class="stats" aria-live="polite">
          <span id="summaryTitle" class="stats-title">Loading map data…</span>
          <span id="summaryCounts" class="stats-counts">Please wait.</span>
        </p>
        <div
          id="economicSummary"
          class="economic-summary"
        >
          <div class="metric-selector" role="group" aria-label="Economic metric">
            <button type="button" data-economic-metric="gdp" aria-pressed="true">GDP</button>
            <button type="button" data-economic-metric="office" aria-pressed="false">Office employment</button>
          </div>
          <label id="officeBenchmarkField" class="office-benchmark-field" for="officeBenchmark" hidden>
            Benchmark
            <select id="officeBenchmark">
              <option value="core_plus_base">Core+ Base</option>
              <option value="core">Core</option>
            </select>
          </label>
          <div id="economicResult" class="economic-result" role="status" aria-live="polite" aria-atomic="true">
            <span id="economicEstimate" class="economic-estimate">Loading economic estimate…</span>
            <span id="economicShare" class="economic-share" hidden></span>
            <span id="economicIncrement" class="economic-detail" hidden></span>
            <span id="economicSensitivity" class="economic-detail" hidden></span>
          </div>
        </div>
      </header>
      <div class="segments" role="group" aria-label="Total time limit">
        ${LIMITS.map(
          limit =>
            `<button type="button" data-limit="${limit}" aria-label="${limit} minutes" aria-pressed="false">${limit}</button>`,
        ).join('')}
      </div>
      <div id="panelControls" class="panel-controls">
        <p class="journey-note">
          Total time = transit time from 金科路 + remaining walking time.
        </p>

        <label class="field" for="basemap">Basemap
          <select id="basemap">
            ${Object.keys(basemaps)
              .map(key => `<option value="${key}">${key}</option>`)
              .join('')}
          </select>
        </label>
        <p class="provider" id="provider"></p>

        <div class="field">
          <label for="search">Station search</label>
          <div class="search-row">
            <input
              id="search"
              list="stations"
              placeholder="Type part of a station name"
              autocomplete="off"
              aria-describedby="searchHint"
              disabled
            />
            <button id="clearSearch" class="clear-search" type="button" hidden>
              Clear
            </button>
          </div>
          <datalist id="stations"></datalist>
          <p id="searchHint" class="hint" aria-live="polite">
            Type part of a station name, then choose a match.
          </p>
        </div>

        <div id="locationSearchField" class="field location-search-field">
          <label for="locationSearch">Location search</label>
          <div class="search-row">
            <input
              id="locationSearch"
              class="location-search-input"
              type="text"
              placeholder="Search places in Shanghai"
              autocomplete="off"
              role="combobox"
              aria-autocomplete="list"
              aria-haspopup="listbox"
              aria-controls="locationSuggestions"
              aria-expanded="false"
              aria-describedby="locationSearchStatus"
              disabled
            />
            <button
              id="clearLocationSearch"
              class="clear-search"
              type="button"
              aria-label="Clear location search"
              hidden
            >
              Clear
            </button>
          </div>
          <ul
            id="locationSuggestions"
            class="location-suggestions"
            role="listbox"
            aria-label="Shanghai location suggestions"
            hidden
          ></ul>
          <p id="locationSearchStatus" class="hint location-search-status" role="status" aria-live="polite">
            Enter at least 2 Chinese or English characters.
          </p>
        </div>

        <label class="field" for="stationDisplay">Station display
          <select id="stationDisplay" disabled>
            <option value="relevant">Relevant only</option>
            <option value="all">All stations</option>
          </select>
        </label>

        <label class="field" for="stationScaling">Station scaling
          <select id="stationScaling" disabled>
            <option value="adaptive">Adaptive to zoom</option>
            <option value="fixed">Fixed size</option>
          </select>
        </label>

        <fieldset class="layer-controls">
          <legend>Map layers</legend>
          <label class="toggle"><input id="showPoly" type="checkbox"/> Show polygon</label>
          <label class="toggle"><input id="invertFill" type="checkbox"/> Invert fill — Shanghai only</label>
          <label class="toggle"><input id="showOfficeDensity" type="checkbox" disabled/> Show office workplace density</label>
          <label class="toggle"><input id="showStations" type="checkbox"/> Show stations</label>
          <label class="toggle"><input id="showLabels" type="checkbox"/> Show labels</label>
        </fieldset>

        <details id="appearance" class="control-section">
          <summary>Appearance</summary>
          <div class="details-content">
            <div class="color-grid">
              <label class="field" for="fill">Fill color
                <input id="fill" type="color"/>
              </label>
              <label class="field" for="outline">Outline color
                <input id="outline" type="color"/>
              </label>
            </div>
            <label class="field" for="opacity">
              <span class="label-line">Opacity <output id="opacityValue"></output></span>
              <input id="opacity" type="range" min="0" max="1" step="0.01"/>
            </label>
            <label class="field" for="width">
              <span class="label-line">Outline width <output id="widthValue"></output></span>
              <input id="width" type="range" min="0" max="8" step="0.5"/>
            </label>
            <label class="field" for="stationSize">
              <span class="label-line">Close-zoom station size <output id="stationSizeValue"></output></span>
              <input id="stationSize" type="range" min="3" max="18" step="1"/>
            </label>
          </div>
        </details>

        <details id="legend" class="control-section legend">
          <summary>Legend</summary>
          <ul class="legend-list">
            <li><span class="legend-mark origin"></span><span><strong>Orange</strong> — 金科路 origin</span></li>
            <li><span class="legend-mark reachable"></span><span><strong>Green</strong> — reachable station</span></li>
            <li><span class="legend-mark boundary"></span><span><strong>White</strong> — boundary station</span></li>
            <li><span class="legend-mark outside"></span><span><strong>Gray</strong> — outside selected time</span></li>
            <li><span class="legend-mark area"></span><span><strong>Turquoise area</strong> — reachable area</span></li>
            <li id="officeDensityLegend" hidden><span class="legend-mark office-density"></span><span><strong>Purple glow</strong> — modelled office workplace density</span></li>
          </ul>
        </details>

        <details id="about" class="control-section about">
          <summary>About this map</summary>
          <div class="details-content">
            <dl class="about-list">
              <div><dt>Last generated</dt><dd id="generatedAt">—</dd></div>
              <div><dt>Available limits</dt><dd id="availableLimits">—</dd></div>
              <div><dt>Data status</dt><dd id="productionStatus">—</dd></div>
            </dl>
            <p id="transitMethod"></p>
            <p id="walkingMethod"></p>
            <section id="economicMethod" class="economic-method" hidden>
              <h3>GDP estimate</h3>
              <p>
                This is a spatial model estimate, not an officially published GDP
                value for the reach polygon.
              </p>
              <p id="gdpCalibrationControl"></p>
              <p id="gdpProxySources"></p>
              <p id="gdpSensitivityMethod"></p>
              <a id="gdpMethodologyLink" class="source-link" target="_blank" rel="noopener noreferrer">
                View full GDP methodology
              </a>
            </section>
            <section id="officeEmploymentMethod" class="economic-method" hidden>
              <div class="method-heading">
                <h3>Office-oriented employment</h3>
                <span id="officeBenchmarkStatus" class="method-status"></span>
              </div>
              <p id="officeDefinition"></p>
              <p id="officeControls"></p>
              <p id="officeBoundaryDisclosure"></p>
              <p id="officeDisplayScope"></p>
              <p id="officeDensityDisclosure"></p>
              <a id="officeMethodologyLink" class="source-link" target="_blank" rel="noopener noreferrer">
                View full office-employment methodology
              </a>
            </section>
            <a id="sourceSheet" class="source-link" target="_blank" rel="noopener noreferrer" hidden>
              Transit source sheet
            </a>
          </div>
        </details>

        <div class="actions">
          <button id="fit" type="button" disabled>Fit to area</button>
          <button id="full" type="button">Fullscreen</button>
          <button id="reset" type="button">Reset appearance</button>
        </div>
      </div>
    </aside>
  </main>`;

let map;
let styleSwitch;
let stations;
let areas;
let outsideAreas;
let manifest;
let metroLines;
let metroStations;
let controlsWired = false;
let activePopup;
let highlightedStation;
let highlightTimer;
let shanghaiBoundary;
let shanghaiSearchBounds;
let locationSearchService;
let locationSearchTimer;
let locationSearchResults = [];
let activeLocationIndex = -1;
let locationSearchComposing = false;
let locationSelection;
let selectedLocationResult;
let economyData;
let gdpMethodology;
let economyLoadState = 'loading';
let officeEmploymentData;
let officeEmploymentMethodology;
let officeEmploymentLoadState = 'loading';
let officeDensityData;
let officeDensityLoadState = 'loading';

const mobileQuery = window.matchMedia('(max-width: 760px)');
const byId = id => document.getElementById(id);

function save() {
  try {
    localStorage.setItem('jinkeAppearance', JSON.stringify(state));
  } catch {
    // The map remains usable when browser storage is unavailable.
  }
}

const selectedAreas = () => selectedFeatureCollection(areas, state.limit);
const selectedOutsideAreas = () =>
  selectedFeatureCollection(outsideAreas, state.limit);

function stationData() {
  return stationFeatureCollection(
    stations,
    state.limit,
    state.stationDisplay,
  );
}

function highlightedStationData() {
  return {
    type: 'FeatureCollection',
    features: highlightedStation ? [highlightedStation] : [],
  };
}

function setMapMessage(message, { error = false, hidden = false } = {}) {
  const shell = document.querySelector('.map-shell');
  const notice = byId('mapMessage');
  byId('mapMessageText').textContent = message;
  notice.hidden = hidden;
  notice.classList.toggle('is-error', error);
  shell.setAttribute('aria-busy', String(!hidden && !error));
}

function hideEconomicDetails() {
  ['economicShare', 'economicIncrement', 'economicSensitivity'].forEach(id => {
    byId(id).hidden = true;
  });
}

function renderGdpSummary() {
  const estimate = byId('economicEstimate');
  const record = economyData?.recordsByLimit?.get(Number(state.limit));

  if (economyLoadState === 'loading') {
    estimate.textContent = 'Loading GDP estimate…';
    hideEconomicDetails();
    return;
  }
  if (economyLoadState !== 'ready' || !record) {
    estimate.textContent = 'Economic estimate unavailable.';
    hideEconomicDetails();
    return;
  }

  estimate.textContent =
    `Estimated GDP within reach: ${formatTrillionCny(
      record.estimated_gdp_100m_cny,
    )}`;
  const share = byId('economicShare');
  share.textContent =
    `${formatShanghaiShare(record.percentage_of_shanghai_gdp)} of Shanghai GDP`;
  share.hidden = false;

  const increment = byId('economicIncrement');
  if (Number(state.limit) === LIMITS[0]) {
    increment.hidden = true;
  } else {
    increment.textContent =
      `Added vs ${Number(state.limit) - 10} minutes: ` +
      `+${formatTrillionCny(record.incremental_gdp_100m_cny)}`;
    increment.hidden = false;
  }

  const sensitivity = byId('economicSensitivity');
  sensitivity.textContent =
    `Sensitivity scenarios: ${formatSensitivityRange(record)}`;
  sensitivity.hidden = false;
}

function renderOfficeEmploymentSummary() {
  const estimate = byId('economicEstimate');
  const benchmark = officeEmploymentData?.benchmarksByKey?.get(
    state.officeBenchmark,
  );
  const record = benchmark?.recordsByLimit?.get(Number(state.limit));

  if (officeEmploymentLoadState === 'loading') {
    estimate.textContent = 'Loading office-employment estimate…';
    hideEconomicDetails();
    return;
  }
  if (officeEmploymentLoadState !== 'ready' || !record || !benchmark) {
    estimate.textContent = 'Office-employment estimate unavailable.';
    hideEconomicDetails();
    return;
  }

  estimate.textContent =
    `Office-oriented employment within reach: ` +
    formatOfficeEmployment(record.employment_inside_reach);
  const share = byId('economicShare');
  share.textContent =
    `${formatOfficeShare(record.percentage_of_shanghai)} of Shanghai ` +
    `${state.officeBenchmark === 'core' ? 'Core' : 'Core+'} office-oriented employment`;
  share.hidden = false;

  const increment = byId('economicIncrement');
  if (Number(state.limit) === LIMITS[0]) {
    increment.hidden = true;
  } else {
    increment.textContent =
      `Added vs ${Number(state.limit) - 10} minutes: ` +
      `+${formatOfficeEmployment(record.incremental_employment)}`;
    increment.hidden = false;
  }

  const definition = byId('economicSensitivity');
  definition.textContent =
    `${benchmark.label} · exact Shanghai denominator: ` +
    `${formatOfficeEmployment(benchmark.denominator)}`;
  definition.hidden = false;
}

function renderEconomy() {
  const isOffice = state.economicMetric === 'office';
  const unavailable = isOffice
    ? officeEmploymentLoadState === 'unavailable'
    : economyLoadState === 'unavailable';
  byId('economicSummary').classList.toggle('is-office', isOffice);
  byId('economicSummary').classList.toggle('is-unavailable', unavailable);
  byId('officeBenchmarkField').hidden = !isOffice;
  byId('officeBenchmark').value = state.officeBenchmark;

  document.querySelectorAll('[data-economic-metric]').forEach(button => {
    const active = button.dataset.economicMetric === state.economicMetric;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });

  if (isOffice) renderOfficeEmploymentSummary();
  else renderGdpSummary();
}

function renderEconomicMethodology() {
  const section = byId('economicMethod');
  if (economyLoadState !== 'ready' || !gdpMethodology) {
    section.hidden = true;
    return;
  }
  const copy = methodologyText(gdpMethodology);
  byId('gdpCalibrationControl').textContent = copy.calibration;
  byId('gdpProxySources').textContent = copy.proxies;
  byId('gdpSensitivityMethod').textContent = copy.sensitivity;
  byId('gdpMethodologyLink').href = assetUrl('data/gdp-methodology.json');
  section.hidden = false;
}

function renderOfficeEmploymentMethodology() {
  const section = byId('officeEmploymentMethod');
  if (
    officeEmploymentLoadState !== 'ready' ||
    !officeEmploymentMethodology
  ) {
    section.hidden = true;
    return;
  }
  const copy = officeMethodologyText(officeEmploymentMethodology);
  byId('officeBenchmarkStatus').textContent =
    officeEmploymentMethodology.classification;
  byId('officeDefinition').textContent = copy.definition;
  byId('officeControls').textContent = copy.controls;
  byId('officeBoundaryDisclosure').textContent = copy.boundaries;
  byId('officeDisplayScope').textContent = copy.scope;
  byId('officeDensityDisclosure').textContent = copy.disclosure;
  byId('officeMethodologyLink').href = assetUrl(
    'data/office-employment-methodology.json',
  );
  section.hidden = false;
}

function renderAbout() {
  if (!manifest) return;

  const generatedAt = new Date(manifest.generated_at);
  const generatedText = Number.isNaN(generatedAt.getTime())
    ? 'Not provided'
    : generatedAt.toLocaleString(undefined, {
        dateStyle: 'medium',
        timeStyle: 'short',
      });
  byId('generatedAt').textContent = generatedText;
  if (manifest.generated_at) byId('generatedAt').title = manifest.generated_at;

  const limits = Array.isArray(manifest.limits) ? manifest.limits : [];
  byId('availableLimits').textContent = limits.length
    ? `${limits.join(' · ')} minutes`
    : 'Not provided';

  const productionStatus = byId('productionStatus');
  productionStatus.textContent = manifest.production_data
    ? 'Production data'
    : 'Development sample';
  productionStatus.className = manifest.production_data
    ? 'status-value is-production'
    : 'status-value is-sample';

  byId('transitMethod').textContent =
    'Transit: times from 金科路 are read from the published source sheet.';
  byId('walkingMethod').textContent =
    `Walking: ORS walking-time areas use the remaining minutes; polygons are merged with ${
      manifest.geometry_union || 'a polygon union'
    }.`;

  const sourceLink = byId('sourceSheet');
  if (
    typeof manifest.source_sheet === 'string' &&
    /^https?:\/\//.test(manifest.source_sheet)
  ) {
    sourceLink.href = manifest.source_sheet;
    sourceLink.hidden = false;
  }
  renderEconomicMethodology();
  renderOfficeEmploymentMethodology();
}

function renderState() {
  document.querySelectorAll('[data-limit]').forEach(button => {
    const active = button.dataset.limit === String(state.limit);
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });

  byId('provider').textContent = basemaps[state.basemap].attribution;
  byId('stationDisplay').value = state.stationDisplay;
  byId('stationScaling').value = state.stationScaling;
  document.documentElement.style.setProperty('--reach-color', state.fill);

  if (areas) {
    const feature = selectedAreas().features[0];
    if (feature) {
      byId('summaryTitle').textContent =
        `${state.limit}-minute total journey`;
      byId('summaryCounts').textContent =
        `${feature.properties.included_stations} reachable stations · ` +
        `${feature.properties.boundary_stations} boundary stations`;
    }
  }
  renderEconomy();

  save();
}

function updateAppearanceOutputs() {
  byId('opacityValue').textContent = `${Math.round(state.opacity * 100)}%`;
  byId('widthValue').textContent = `${state.width}px`;
  byId('stationSizeValue').textContent = `${state.stationSize}px`;
}

function setControlValues() {
  ['fill', 'outline', 'opacity', 'width', 'stationSize'].forEach(id => {
    byId(id).value = state[id];
  });
  [
    'showPoly',
    'invertFill',
    'showOfficeDensity',
    'showStations',
    'showLabels',
  ].forEach(id => {
    byId(id).checked = Boolean(state[id]);
  });
  byId('basemap').value = state.basemap;
  byId('stationDisplay').value = state.stationDisplay;
  byId('stationScaling').value = state.stationScaling;
  byId('officeBenchmark').value = state.officeBenchmark;
  updateAppearanceOutputs();
}

function setPaintProperty(layerId, property, value) {
  if (map?.getLayer(layerId)) map.setPaintProperty(layerId, property, value);
}

function applyMapState() {
  renderState();
  updateAppearanceOutputs();
  byId('officeDensityLegend').hidden = !(
    state.showOfficeDensity && officeDensityLoadState === 'ready'
  );
  if (!map || !areas || !outsideAreas || !stations) return;

  map.getSource('areas')?.setData(selectedAreas());
  map.getSource('outside-areas')?.setData(selectedOutsideAreas());
  map.getSource('stations')?.setData(stationData());
  map.getSource('station-highlight')?.setData(highlightedStationData());

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
    'office-density-heatmap',
    'heatmap-opacity',
    state.showOfficeDensity && officeDensityLoadState === 'ready' ? 0.86 : 0,
  );
  const stationPaint = stationPaintForState(state);
  setPaintProperty('station-circle', 'circle-radius', stationPaint.radius);
  setPaintProperty(
    'station-circle',
    'circle-stroke-width',
    stationPaint.strokeWidth,
  );
  setPaintProperty(
    'station-circle',
    'circle-opacity',
    state.showStations ? 1 : 0,
  );
  setPaintProperty(
    'station-circle',
    'circle-stroke-opacity',
    state.showStations ? 1 : 0,
  );
  setPaintProperty(
    'station-highlight',
    'circle-radius',
    stationPaint.highlightRadius,
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

function addLayerOnce(definition, beforeId) {
  if (!map.getLayer(definition.id)) {
    map.addLayer(
      definition,
      beforeId && map.getLayer(beforeId) ? beforeId : undefined,
    );
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function locationResultDetails(result) {
  const values = [result.category, result.district, result.secondary]
    .map(value => String(value || '').trim())
    .filter(Boolean);
  return values.filter(
    (value, index) =>
      values.findIndex(
        candidate => candidate.toLocaleLowerCase() === value.toLocaleLowerCase(),
      ) === index,
  );
}

function setLocationSearchStatus(message, { error = false, loading = false } = {}) {
  const status = byId('locationSearchStatus');
  status.textContent = message;
  status.classList.toggle('is-error', error);
  status.classList.toggle('is-loading', loading);
}

function setActiveLocationIndex(index, { scroll = true } = {}) {
  const input = byId('locationSearch');
  const options = [...byId('locationSuggestions').querySelectorAll('[role="option"]')];
  activeLocationIndex =
    options.length && index >= 0
      ? Math.min(options.length - 1, Math.max(0, index))
      : -1;

  options.forEach((option, optionIndex) => {
    const active = optionIndex === activeLocationIndex;
    option.classList.toggle('is-active', active);
    option.setAttribute('aria-selected', String(active));
  });
  if (activeLocationIndex >= 0) {
    const activeOption = options[activeLocationIndex];
    input.setAttribute('aria-activedescendant', activeOption.id);
    if (scroll) activeOption.scrollIntoView({ block: 'nearest' });
  } else {
    input.removeAttribute('aria-activedescendant');
  }
}

function closeLocationSuggestions({ resetActive = true } = {}) {
  const input = byId('locationSearch');
  const list = byId('locationSuggestions');
  list.hidden = true;
  input.setAttribute('aria-expanded', 'false');
  if (resetActive) setActiveLocationIndex(-1, { scroll: false });
}

function renderLocationSuggestions() {
  const list = byId('locationSuggestions');
  list.replaceChildren(
    ...locationSearchResults.map((result, index) => {
      const option = document.createElement('li');
      option.id = `location-suggestion-${index}`;
      option.dataset.index = String(index);
      option.setAttribute('role', 'option');
      option.setAttribute('aria-selected', 'false');

      const name = document.createElement('strong');
      name.className = 'location-suggestion-name';
      name.textContent = result.name;
      const details = document.createElement('span');
      details.className = 'location-suggestion-details';
      details.textContent = locationResultDetails(result).join(' · ');
      option.append(name, details);
      return option;
    }),
  );

  const hasResults = locationSearchResults.length > 0;
  list.hidden = !hasResults;
  byId('locationSearch').setAttribute('aria-expanded', String(hasResults));
  setActiveLocationIndex(hasResults ? 0 : -1, { scroll: false });
}

function locationSearchProximity() {
  const fallback = [121.597836, 31.2064028];
  const center = map?.getCenter?.();
  const coordinates = center
    ? [Number(center.lng), Number(center.lat)]
    : fallback;
  return pointInGeoJson(coordinates, shanghaiBoundary) ? coordinates : fallback;
}

function locationZoom(result) {
  if (['poi', 'address'].includes(result.placeType)) return 16;
  if (['street', 'neighbourhood', 'locality'].includes(result.placeType)) {
    return 15;
  }
  return 13;
}

function createLocationVisual(result) {
  if (!map) return {};

  const markerElement = document.createElement('button');
  markerElement.type = 'button';
  markerElement.className = 'location-marker';
  markerElement.setAttribute('aria-label', `Selected location: ${result.name}`);
  markerElement.title = result.name;
  const pin = document.createElement('span');
  pin.className = 'location-marker-pin';
  pin.setAttribute('aria-hidden', 'true');
  markerElement.append(pin);

  const details = locationResultDetails(result);
  const popup = new maplibregl.Popup({ offset: 26 })
    .setLngLat(result.coordinates)
    .setHTML(
      `<div class="location-popup">` +
        `<strong>${escapeHtml(result.name)}</strong>` +
        `<span>${escapeHtml(result.category)}</span>` +
        (details.slice(1).length
          ? `<p>${escapeHtml(details.slice(1).join(' · '))}</p>`
          : '') +
        `</div>`,
    );
  const marker = new maplibregl.Marker({
    element: markerElement,
    anchor: 'bottom',
  })
    .setLngLat(result.coordinates)
    .setPopup(popup)
    .addTo(map);
  popup.addTo(map);
  return { marker, popup };
}

function initializeLocationSelection() {
  if (!map || locationSelection) return;
  locationSelection = new SingleLocationSelection({
    createVisual: createLocationVisual,
    isPresent: marker => Boolean(marker.getElement?.()?.isConnected),
  });
  if (selectedLocationResult) locationSelection.select(selectedLocationResult);
}

function selectLocationResult(result) {
  if (!result) return;
  selectedLocationResult = result;
  const input = byId('locationSearch');
  input.value = result.name;
  byId('clearLocationSearch').hidden = false;
  locationSearchResults = [];
  closeLocationSuggestions();
  setLocationSearchStatus(`Showing ${result.name} in Shanghai.`);

  if (map) {
    initializeLocationSelection();
    locationSelection.select(result);
    map.flyTo({
      center: result.coordinates,
      zoom: locationZoom(result),
      essential: true,
    });
  }
}

function clearLocationSearch({ focus = true } = {}) {
  window.clearTimeout(locationSearchTimer);
  locationSearchService?.cancel();
  selectedLocationResult = null;
  locationSelection?.clear();
  locationSearchResults = [];
  activeLocationIndex = -1;
  const input = byId('locationSearch');
  input.value = '';
  byId('clearLocationSearch').hidden = true;
  byId('locationSuggestions').replaceChildren();
  closeLocationSuggestions();
  setLocationSearchStatus('Enter at least 2 Chinese or English characters.');
  if (focus && !input.disabled) input.focus();
}

function showLocationSearchError(error) {
  locationSearchResults = [];
  renderLocationSuggestions();
  if (error instanceof LocationSearchError && error.code === 'missing-config') {
    setLocationSearchStatus(
      'Location search is unavailable because its configuration is missing.',
      { error: true },
    );
  } else if (error instanceof LocationSearchError && error.code === 'rate-limit') {
    setLocationSearchStatus(
      'Location search is temporarily rate-limited. Please try again shortly.',
      { error: true },
    );
  } else if (error instanceof LocationSearchError && error.code === 'invalid-response') {
    setLocationSearchStatus(
      'Location search returned an invalid response. Please try again.',
      { error: true },
    );
  } else if (error instanceof LocationSearchError && error.code === 'service-unavailable') {
    setLocationSearchStatus(
      'Location search is temporarily unavailable. Please try again shortly.',
      { error: true },
    );
  } else {
    setLocationSearchStatus(
      'Location search could not be completed. Please try again.',
      { error: true },
    );
  }
}

async function runLocationSearch(query) {
  if (!locationSearchService) return;
  const normalizedQuery = normalizeLocationQuery(query);
  setLocationSearchStatus('Searching Shanghai…', { loading: true });
  try {
    const response = await locationSearchService.search(normalizedQuery, {
      bbox: shanghaiSearchBounds,
      proximity: locationSearchProximity(),
      limit: 8,
    });
    if (response.status === 'stale') return;
    if (
      normalizeLocationQuery(byId('locationSearch').value) !== normalizedQuery
    ) {
      return;
    }
    locationSearchResults = response.results;
    renderLocationSuggestions();
    if (!locationSearchResults.length) {
      setLocationSearchStatus('No matching place found in Shanghai.');
      return;
    }
    setLocationSearchStatus(
      `${locationSearchResults.length} Shanghai suggestions. Use arrow keys and Enter to choose.`,
    );
  } catch (error) {
    showLocationSearchError(error);
  }
}

function scheduleLocationSearch(query) {
  window.clearTimeout(locationSearchTimer);
  const normalizedQuery = normalizeLocationQuery(query);
  byId('clearLocationSearch').hidden = !normalizedQuery;
  if (locationQueryLength(normalizedQuery) < 2) {
    locationSearchService?.cancel();
    if (!normalizedQuery) {
      selectedLocationResult = null;
      locationSelection?.clear();
    }
    locationSearchResults = [];
    renderLocationSuggestions();
    setLocationSearchStatus('Enter at least 2 Chinese or English characters.');
    return;
  }
  setLocationSearchStatus('Waiting to search…', { loading: true });
  locationSearchTimer = window.setTimeout(
    () => runLocationSearch(normalizedQuery),
    300,
  );
}

async function initializeLocationSearch() {
  const input = byId('locationSearch');
  try {
    const boundary = await fetchJson('shanghai-boundary.geojson');
    const bounds = geoJsonBounds(boundary);
    if (!bounds) throw new Error('Invalid Shanghai boundary');
    shanghaiBoundary = boundary;
    shanghaiSearchBounds = bounds;
    locationSearchService = new AmapLocationSearch({
      endpointProvider: runtimeLocationSearchEndpoint,
      boundary: shanghaiBoundary,
    });
    if (!runtimeLocationSearchEndpoint()) {
      setLocationSearchStatus(
        'Location search is unavailable because its configuration is missing.',
        { error: true },
      );
      return;
    }
    input.disabled = false;
    setLocationSearchStatus('Enter at least 2 Chinese or English characters.');
  } catch {
    input.disabled = true;
    setLocationSearchStatus(
      'Location search is unavailable because the Shanghai boundary could not be loaded.',
      { error: true },
    );
  }
}

function openStationPopup(feature) {
  if (!map) return;
  const enriched = enrichStationFeature(feature, state.limit);
  const properties = enriched.properties;
  activePopup?.remove();
  activePopup = new maplibregl.Popup()
    .setLngLat(enriched.geometry.coordinates)
    .setHTML(
      `<strong>${escapeHtml(properties.station)}</strong>` +
        `<dl class="station-popup">` +
        `<div><dt>Transit from 金科路</dt><dd>${properties.apple} min</dd></div>` +
        `<div><dt>Remaining walk</dt><dd>${properties.remaining_walk_minutes} min</dd></div>` +
        `<div><dt>Selected total</dt><dd>${state.limit} min</dd></div>` +
        `</dl>`,
    )
    .addTo(map);
}

function handleStationClick(event) {
  const feature = event.features?.[0];
  if (feature) openStationPopup(feature);
}

function clearHighlight() {
  highlightedStation = null;
  window.clearTimeout(highlightTimer);
  map?.getSource('station-highlight')?.setData(highlightedStationData());
}

function highlightStation(feature) {
  highlightedStation = enrichStationFeature(feature, state.limit);
  map?.getSource('station-highlight')?.setData(highlightedStationData());
  window.clearTimeout(highlightTimer);
  highlightTimer = window.setTimeout(clearHighlight, 4500);
}

function restoreCustomLayers() {
  // Restore as soon as MapLibre exposes the new style. Do not wait for all
  // remote basemap sources or tiles: overlays are local and independent.
  if (!areas || !outsideAreas || !stations || !map?.getStyle()) return false;

  addSourceOnce('areas', { type: 'geojson', data: selectedAreas() });
  addSourceOnce('outside-areas', {
    type: 'geojson',
    data: selectedOutsideAreas(),
    attribution:
      'Shanghai boundary: <a href="https://openfreemap.org/">OpenFreeMap</a> / ' +
      '<a href="https://openmaptiles.org/">OpenMapTiles</a> · © ' +
      '<a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> (ODbL)',
  });
  addSourceOnce('stations', { type: 'geojson', data: stationData() });
  addSourceOnce('station-highlight', {
    type: 'geojson',
    data: highlightedStationData(),
  });
  if (officeDensityData) {
    addSourceOnce('office-density', {
      type: 'geojson',
      data: officeDensityData,
      attribution:
        'Office density: Shanghai 2023 Economic Census controls · JRC built volume · ' +
        '<a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> (ODbL) · Overture Maps',
    });
  }

  addLayerOnce({
    id: 'outside-fill',
    type: 'fill',
    source: 'outside-areas',
    paint: {
      'fill-antialias': true,
      'fill-color': state.fill,
      'fill-opacity': 0,
    },
  });
  addLayerOnce({
    id: 'reach-fill',
    type: 'fill',
    source: 'areas',
    paint: {
      'fill-antialias': true,
      'fill-color': state.fill,
      'fill-opacity': state.opacity,
    },
  });
  if (officeDensityData) {
    addLayerOnce(
      {
        id: 'office-density-heatmap',
        type: 'heatmap',
        source: 'office-density',
        paint: {
          'heatmap-weight': [
            'interpolate',
            ['linear'],
            ['coalesce', ['to-number', ['get', 'j']], 0],
            0,
            0,
            100,
            0.05,
            400,
            0.15,
            1_200,
            0.4,
            2_200,
            0.65,
            5_400,
            0.95,
            14_000,
            1,
          ],
          'heatmap-intensity': [
            'interpolate',
            ['linear'],
            ['zoom'],
            8,
            0.52,
            11,
            0.82,
            14,
            1.12,
          ],
          'heatmap-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            8,
            11,
            11,
            22,
            14,
            34,
          ],
          'heatmap-color': [
            'interpolate',
            ['linear'],
            ['heatmap-density'],
            0,
            'rgba(88,28,135,0)',
            0.14,
            'rgba(126,34,206,0.28)',
            0.34,
            'rgba(168,85,247,0.5)',
            0.58,
            'rgba(217,70,239,0.7)',
            0.8,
            'rgba(236,72,153,0.86)',
            1,
            'rgba(126,20,122,1)',
          ],
          'heatmap-opacity': state.showOfficeDensity ? 0.86 : 0,
        },
      },
      'reach-line',
    );
  }
  addLayerOnce({
    id: 'reach-line',
    type: 'line',
    source: 'areas',
    paint: { 'line-color': state.outline, 'line-width': state.width },
  });
  const stationPaint = stationPaintForState(state);
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
        '#ffffff',
      ],
      'circle-stroke-width': stationPaint.strokeWidth,
      'circle-radius': stationPaint.radius,
    },
  });
  addLayerOnce({
    id: 'station-highlight',
    type: 'circle',
    source: 'station-highlight',
    paint: {
      'circle-color': 'rgba(255,255,255,0)',
      'circle-stroke-color': '#f97316',
      'circle-stroke-width': 4,
      'circle-radius': stationPaint.highlightRadius,
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
    paint: { 'text-halo-color': '#ffffff', 'text-halo-width': 1 },
  });

  bindLayerHandlerOnce(map, 'click', 'station-circle', handleStationClick);
  applyMapState();
  initializeLocationSelection();
  locationSelection?.ensure();
  byId('fit').disabled = false;
  setMapMessage('', { hidden: true });
  return true;
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

function updateSearchSuggestions(query = '') {
  if (!stations) return;
  const datalist = byId('stations');
  datalist.replaceChildren(
    ...matchingStations(stations.features, query, 14).map(feature => {
      const option = document.createElement('option');
      option.value = feature.properties.station;
      return option;
    }),
  );
}

function selectStation(feature) {
  if (!feature) return;
  const input = byId('search');
  input.value = feature.properties.station;
  byId('clearSearch').hidden = false;
  byId('searchHint').textContent =
    `Showing ${feature.properties.station}. Highlight fades after a few seconds.`;

  if (!map) return;
  map.flyTo({
    center: feature.geometry.coordinates,
    zoom: Math.max(map.getZoom(), 13),
  });
  highlightStation(feature);
  openStationPopup(feature);
}

function clearStationSearch({ focus = true } = {}) {
  const input = byId('search');
  input.value = '';
  byId('clearSearch').hidden = true;
  byId('searchHint').textContent =
    'Type part of a station name, then choose a match.';
  updateSearchSuggestions();
  clearHighlight();
  activePopup?.remove();
  activePopup = undefined;
  if (focus) input.focus();
}

function setSheetExpanded(expanded) {
  const panel = document.querySelector('.panel');
  panel.classList.toggle('is-expanded', expanded);
  byId('sheetToggle').setAttribute('aria-expanded', String(expanded));
  byId('sheetToggleState').textContent = expanded ? 'Collapse' : 'Expand';
  window.setTimeout(() => map?.resize(), 220);
}

function wireControls() {
  if (controlsWired) return;
  controlsWired = true;

  setControlValues();
  byId('legend').open = !mobileQuery.matches;
  setSheetExpanded(!mobileQuery.matches);

  byId('sheetToggle').onclick = () => {
    const expanded = !document
      .querySelector('.panel')
      .classList.contains('is-expanded');
    setSheetExpanded(expanded);
  };

  if (typeof mobileQuery.addEventListener === 'function') {
    mobileQuery.addEventListener('change', event => {
      setSheetExpanded(!event.matches);
      if (event.matches) byId('legend').open = false;
    });
  }

  ['fill', 'outline', 'opacity', 'width', 'stationSize'].forEach(id => {
    const element = byId(id);
    element.oninput = () => {
      state[id] =
        element.type === 'range' ? Number(element.value) : element.value;
      applyMapState();
    };
  });

  [
    'showPoly',
    'invertFill',
    'showOfficeDensity',
    'showStations',
    'showLabels',
  ].forEach(id => {
    const element = byId(id);
    element.onchange = () => {
      state[id] = element.checked;
      applyMapState();
    };
  });

  document.querySelectorAll('[data-economic-metric]').forEach(button => {
    button.onclick = () => {
      state.economicMetric = button.dataset.economicMetric;
      renderState();
    };
  });

  byId('officeBenchmark').onchange = event => {
    state.officeBenchmark = event.target.value;
    renderState();
  };

  document.querySelectorAll('[data-limit]').forEach(button => {
    button.onclick = () => {
      state.limit = Number(button.dataset.limit);
      if (highlightedStation) {
        highlightedStation = enrichStationFeature(
          highlightedStation,
          state.limit,
        );
      }
      applyMapState();
      if (activePopup && byId('search').value) {
        const feature = findStationMatch(
          stations?.features || [],
          byId('search').value,
        );
        if (feature) openStationPopup(feature);
      }
    };
  });

  const basemap = byId('basemap');
  basemap.onchange = () => {
    if (!basemaps[basemap.value]) return;
    state.basemap = basemap.value;
    renderState();
    if (styleSwitch) {
      setMapMessage('Changing basemap…');
      styleSwitch.switchTo(state.basemap, basemaps[state.basemap].style());
    }
  };

  byId('stationDisplay').onchange = event => {
    state.stationDisplay = event.target.value;
    applyMapState();
  };

  byId('stationScaling').onchange = event => {
    state.stationScaling = event.target.value;
    applyMapState();
  };

  byId('fit').onclick = () => {
    if (!map || !areas) return;
    const feature = selectedAreas().features[0];
    if (!feature) return;
    const bounds = new maplibregl.LngLatBounds();
    extendBounds(bounds, feature.geometry.coordinates);
    map.fitBounds(bounds, { padding: 50 });
  };

  byId('full').onclick = () => {
    if (document.fullscreenElement) {
      document.exitFullscreen?.();
    } else {
      document.documentElement.requestFullscreen?.();
    }
  };

  byId('reset').onclick = () => {
    const previousBasemap = state.basemap;
    Object.assign(state, defaults);
    setControlValues();
    clearStationSearch({ focus: false });
    renderState();
    if (styleSwitch && previousBasemap !== state.basemap) {
      setMapMessage('Changing basemap…');
      styleSwitch.switchTo(state.basemap, basemaps[state.basemap].style());
    } else {
      applyMapState();
    }
  };

  const search = byId('search');
  search.oninput = event => {
    const query = event.target.value;
    byId('clearSearch').hidden = !query;
    updateSearchSuggestions(query);
    const exact = (stations?.features || []).find(
      feature =>
        normalizeStationQuery(feature.properties.station) ===
        normalizeStationQuery(query),
    );
    if (exact) selectStation(exact);
  };
  search.onchange = event => {
    const feature = findStationMatch(
      stations?.features || [],
      event.target.value,
    );
    if (feature) selectStation(feature);
  };
  search.onkeydown = event => {
    if (event.key !== 'Enter') return;
    const feature = findStationMatch(
      stations?.features || [],
      event.currentTarget.value,
    );
    if (feature) {
      event.preventDefault();
      selectStation(feature);
    }
  };
  byId('clearSearch').onclick = () => clearStationSearch();

  const locationInput = byId('locationSearch');
  const locationList = byId('locationSuggestions');
  locationInput.oncompositionstart = () => {
    locationSearchComposing = true;
  };
  locationInput.oncompositionend = event => {
    locationSearchComposing = false;
    scheduleLocationSearch(event.currentTarget.value);
  };
  locationInput.oninput = event => {
    if (!locationSearchComposing) {
      scheduleLocationSearch(event.currentTarget.value);
    }
  };
  locationInput.onfocus = () => {
    if (locationSearchResults.length) renderLocationSuggestions();
  };
  locationInput.onkeydown = event => {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeLocationSuggestions();
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (!locationSearchResults.length) return;
      event.preventDefault();
      if (byId('locationSuggestions').hidden) renderLocationSuggestions();
      const direction = event.key === 'ArrowDown' ? 1 : -1;
      const nextIndex =
        activeLocationIndex < 0
          ? direction > 0
            ? 0
            : locationSearchResults.length - 1
          : (activeLocationIndex + direction + locationSearchResults.length) %
            locationSearchResults.length;
      setActiveLocationIndex(nextIndex);
      return;
    }
    if (event.key === 'Enter' && activeLocationIndex >= 0) {
      const result = locationSearchResults[activeLocationIndex];
      if (result) {
        event.preventDefault();
        selectLocationResult(result);
      }
    }
  };
  locationList.onmousedown = event => event.preventDefault();
  locationList.onclick = event => {
    const option = event.target.closest('[role="option"]');
    if (!option) return;
    selectLocationResult(locationSearchResults[Number(option.dataset.index)]);
  };
  byId('clearLocationSearch').onclick = () => clearLocationSearch();
  document.addEventListener('pointerdown', event => {
    if (!byId('locationSearchField').contains(event.target)) {
      closeLocationSuggestions();
    }
  });
}

async function fetchJson(filename) {
  const response = await fetch(assetUrl(`data/${filename}`));
  if (!response.ok) {
    throw new Error(`Unable to load ${filename}: HTTP ${response.status}`);
  }
  return response.json();
}

async function loadEconomicData() {
  try {
    const [records, methodology] = await Promise.all([
      fetchJson('reach-economy.json'),
      fetchJson('gdp-methodology.json'),
    ]);
    economyData = validateEconomyPayload(records, methodology, LIMITS);
    gdpMethodology = methodology;
    economyLoadState = 'ready';
  } catch (error) {
    console.warn('Economic estimate load failed', error);
    economyData = undefined;
    gdpMethodology = undefined;
    economyLoadState = 'unavailable';
  }
  renderEconomy();
  renderEconomicMethodology();
}

async function loadOfficeEmploymentData() {
  try {
    const [records, methodology] = await Promise.all([
      fetchJson('reach-office-employment.json'),
      fetchJson('office-employment-methodology.json'),
    ]);
    officeEmploymentData = validateOfficeEmploymentPayload(
      records,
      methodology,
      LIMITS,
    );
    officeEmploymentMethodology = methodology;
    officeEmploymentLoadState = 'ready';
  } catch (error) {
    console.warn('Office-employment estimate load failed', error);
    officeEmploymentData = undefined;
    officeEmploymentMethodology = undefined;
    officeEmploymentLoadState = 'unavailable';
  }
  renderEconomy();
  renderOfficeEmploymentMethodology();
}

async function loadOfficeDensityData() {
  const toggle = byId('showOfficeDensity');
  try {
    const density = await fetchJson('office-density-display.geojson');
    officeDensityData = validateOfficeDensityPayload(
      density,
      officeEmploymentMethodology,
    );
    officeDensityLoadState = 'ready';
    toggle.disabled = false;
    toggle.title = '';
    if (map?.getStyle()) restoreCustomLayers();
    else applyMapState();
  } catch (error) {
    console.warn('Office-density display load failed', error);
    officeDensityData = undefined;
    officeDensityLoadState = 'unavailable';
    state.showOfficeDensity = false;
    toggle.checked = false;
    toggle.disabled = true;
    toggle.title = 'Office workplace density is unavailable.';
    applyMapState();
  }
}

wireControls();
initializeLocationSearch();
void loadEconomicData();
void loadOfficeEmploymentData().then(loadOfficeDensityData);

Promise.all([
  fetchJson('reach-areas.geojson'),
  fetchJson('outside-reach-areas.geojson'),
  fetchJson('stations.geojson'),
  fetchJson('manifest.json'),
  fetchJson('shanghai-metro-lines.geojson'),
  fetchJson('shanghai-metro-stations.geojson'),
])
  .then(
    ([
      reachData,
      outsideData,
      stationDataValue,
      manifestValue,
      metroLineData,
      metroStationData,
    ]) => {
      areas = reachData;
      outsideAreas = outsideData;
      stations = stationDataValue;
      manifest = manifestValue;
      metroLines = metroLineData;
      metroStations = metroStationData;

      if (!manifest.production_data) {
        const notice = byId('sample');
        notice.hidden = false;
        notice.textContent =
          'Development sample data — production ORS polygons have not been generated yet. Do not use this map as final coverage.';
      }

      byId('search').disabled = false;
      byId('stationDisplay').disabled = false;
      byId('stationScaling').disabled = false;
      updateSearchSuggestions();
      renderAbout();
      renderState();

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
        if (map.isStyleLoaded()) restoreCustomLayers();
      } catch (error) {
        console.error('Map rendering failed', error);
        setMapMessage(
          'Map rendering is not available in this browser. The data and controls are still available.',
          { error: true },
        );
      }
    },
  )
  .catch(error => {
    console.error('Jinke data load failed', error);
    byId('summaryTitle').textContent = 'Map data unavailable';
    byId('summaryCounts').textContent = 'Refresh the page to try again.';
    setMapMessage(
      'The map data could not be loaded. Check your connection and refresh the page.',
      { error: true },
    );
  });
