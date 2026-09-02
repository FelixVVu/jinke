import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { gzipSync } from 'node:zlib';
import test from 'node:test';

const testDirectory = dirname(new URL(import.meta.url).pathname);
const sitesSourceDirectory = resolve(testDirectory, '../public/web/src');
const sourceDirectory = existsSync(sitesSourceDirectory)
  ? sitesSourceDirectory
  : resolve(testDirectory, '../web/src');
const sitesDataDirectory = resolve(testDirectory, '../public/data');
const dataDirectory = existsSync(sitesDataDirectory)
  ? sitesDataDirectory
  : resolve(testDirectory, '../web/public/data');

const officeModule = await import(
  pathToFileURL(resolve(sourceDirectory, 'office-employment.js'))
);
const reachPath = resolve(dataDirectory, 'reach-office-employment.json');
const methodologyPath = resolve(
  dataDirectory,
  'office-employment-methodology.json',
);
const densityPath = resolve(dataDirectory, 'office-density-display.geojson');
const reach = JSON.parse(readFileSync(reachPath, 'utf8'));
const methodology = JSON.parse(readFileSync(methodologyPath, 'utf8'));
const density = JSON.parse(readFileSync(densityPath, 'utf8'));

test('office benchmarks preserve approved exact results and denominators', () => {
  const validated = officeModule.validateOfficeEmploymentPayload(
    reach,
    methodology,
  );
  const core = validated.benchmarksByKey.get('core');
  const corePlus = validated.benchmarksByKey.get('core_plus_base');

  assert.equal(core.denominator, 2_477_585);
  assert.equal(corePlus.denominator, 3_220_710);
  assert.deepEqual([...core.recordsByLimit.keys()], [10, 20, 30, 40, 50]);
  assert.deepEqual([...corePlus.recordsByLimit.keys()], [10, 20, 30, 40, 50]);
  assert.equal(
    core.recordsByLimit.get(50).employment_inside_reach,
    945_831.5409696298,
  );
  assert.equal(
    corePlus.recordsByLimit.get(50).employment_inside_reach,
    1_212_066.7132367718,
  );
  assert.equal(
    officeModule.formatOfficeShare(
      corePlus.recordsByLimit.get(50).percentage_of_shanghai,
    ),
    '37.63%',
  );
  assert.equal(
    officeModule.formatOfficeEmployment(
      corePlus.recordsByLimit.get(50).employment_inside_reach,
    ),
    '1,212,067',
  );
});

test('Core+ definition and methodology retain the approved disclosure', () => {
  assert.deepEqual(
    methodology.definitions.core_plus_base.industry_codes,
    ['I', 'J', 'M', '721', '723', '724', '725'],
  );
  assert.equal(
    methodology.definitions.core_plus_base.industry_codes.includes('726'),
    false,
  );
  assert.equal(methodology.classification, 'USABLE WITH CAUTION');
  assert.equal(
    methodology.required_disclosure,
    officeModule.OFFICE_DENSITY_DISCLOSURE,
  );
  assert.equal(methodology.reach_statistics.rendered_heatmap_used, false);
});

test('office-density display is lightweight, visual-only, and valid', () => {
  officeModule.validateOfficeDensityPayload(density, methodology);
  assert.equal(density.features.length, 12_261);
  assert.equal(density.metadata.aggregation_metres, 400);
  assert.equal(density.metadata.analytical_all_city_jobs, 3_220_710);
  assert.ok(density.metadata.retained_share_of_all_city_grid > 0.998);
  assert.ok(statSync(densityPath).size < 1_500_000);
  assert.ok(gzipSync(readFileSync(densityPath)).length < 175_000);

  const shippedFiles = readdirSync(dataDirectory).map(name => name.toLowerCase());
  assert.equal(shippedFiles.some(name => name.endsWith('.parquet')), false);
  assert.equal(shippedFiles.some(name => name.includes('office-grid')), false);
});

test('UI layers office heatmap above reach fill and below outline and stations', () => {
  const mainSource = readFileSync(resolve(sourceDirectory, 'main.js'), 'utf8');
  const outsideLayerIndex = mainSource.indexOf("id: 'outside-fill'");
  const reachFillLayerIndex = mainSource.indexOf("id: 'reach-fill'");
  const allBandsLayerIndex = mainSource.indexOf("id: 'all-reach-bands-fill'");
  const densityLayerIndex = mainSource.indexOf("id: 'office-density-heatmap'");
  const reachLineLayerIndex = mainSource.indexOf("id: 'reach-line'");
  const allContoursLayerIndex = mainSource.indexOf("id: 'all-reach-contours'");
  const outerBoundaryLayerIndex = mainSource.indexOf(
    "id: 'all-reach-outer-boundary'",
  );
  const stationLayerIndex = mainSource.indexOf("id: 'station-circle'");
  const densityLayerDefinition = mainSource.slice(
    densityLayerIndex,
    reachLineLayerIndex,
  );
  const weightExpression = mainSource.slice(
    mainSource.indexOf("'heatmap-weight'", densityLayerIndex),
    mainSource.indexOf("'heatmap-intensity'", densityLayerIndex),
  );

  assert.ok(outsideLayerIndex >= 0);
  assert.ok(reachFillLayerIndex > outsideLayerIndex);
  assert.ok(allBandsLayerIndex > reachFillLayerIndex);
  assert.ok(densityLayerIndex > allBandsLayerIndex);
  assert.ok(reachLineLayerIndex > densityLayerIndex);
  assert.ok(allContoursLayerIndex > reachLineLayerIndex);
  assert.ok(outerBoundaryLayerIndex > allContoursLayerIndex);
  assert.ok(stationLayerIndex > outerBoundaryLayerIndex);
  assert.doesNotMatch(densityLayerDefinition, /maxzoom/);
  assert.match(weightExpression, /\['get', 'j'\]/);
  assert.doesNotMatch(weightExpression, /\['get', 'w'\]/);
  assert.match(
    weightExpression,
    /100,\s+0\.05,\s+400,\s+0\.15,\s+1_200,\s+0\.4,\s+2_200,\s+0\.65,\s+5_400,\s+0\.95,\s+14_000,\s+1/,
  );
  assert.match(mainSource, /data-economic-metric="gdp"/);
  assert.match(mainSource, /data-economic-metric="office"/);
  assert.match(mainSource, /Show office workplace density/);
  assert.match(mainSource, /data-limit="\$\{limit\}"/);
  assert.match(mainSource, /All reach contours · 10–50 minutes/);
  assert.match(mainSource, /reach-office-employment\.json/);
  assert.match(mainSource, /office-density-display\.geojson/);
});

test('CARTO raster basemaps use the runtime public key', () => {
  const mainSource = readFileSync(resolve(sourceDirectory, 'main.js'), 'utf8');
  const keyedCartoUrls = [
    ...mainSource.matchAll(
      /cartoTileUrl\('https:\/\/[a-d]\.basemaps\.cartocdn\.com\/[^']+'\)/g,
    ),
  ];

  assert.equal(keyedCartoUrls.length, 8);
  assert.match(mainSource, /window\.JINKE_CARTO_BASEMAP_KEY/);
  assert.match(mainSource, /\?key=\$\{encodeURIComponent\(key\)\}/);
  assert.doesNotMatch(mainSource, /cartoTileUrl\('https:\/\/tile\.openstreetmap\.org/);
  assert.doesNotMatch(mainSource, /cb1_/);
});
