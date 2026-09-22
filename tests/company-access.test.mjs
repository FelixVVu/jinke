import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import test from 'node:test';
import { officeSchema, validateOffice, normalizeCompanyName, REACH_MINUTES } from '../web/src/company-access/schema.js';
import { deriveCompanyAccess, selectCompanyOffices, validateCompanyAccessOutput } from '../web/src/company-access/model.js';
import { CompanyAccessLayers, COMPANY_SOURCE, COMPANY_LAYER } from '../web/src/company-access/layers.js';
import { companyPanelState } from '../web/src/company-access/panel.js';
import { StyleSwitchCoordinator, createRasterStyle } from '../web/src/map-utils.js';

// Synthetic geometry and anonymous records are test-only, never shipped as inventory.
const ring = n => [[-n,-n],[n,-n],[n,n],[-n,n],[-n,-n]];
const areas = { type: 'FeatureCollection', features: REACH_MINUTES.map((limit, i) => ({
  type: 'Feature', properties: { limit }, geometry: { type: 'Polygon', coordinates: [ring(i+1)] },
})) };
const provenance = { status: 'ready', dataset_version: 'synthetic-tests-only', reach_sha256: 'a'.repeat(64), inventory_sha256: 'b'.repeat(64) };
function office(overrides = {}) {
  return { id: 'test-office-a', company_name: ' TEST A ', normalized_name: 'test a',
    longitude: 0, latitude: 0, coordinate_system: 'WGS84', district: null,
    address: 'Synthetic test address', building_name: null, hub_id: null, hub_name: null,
    industry_code: null, sector: null, location_confidence: 'approximate',
    source_type: 'other', source_id: 'test-source-a', source_url: 'https://example.invalid/evidence',
    verified_at: null, min_reach_minutes: 10, ...overrides };
}
const output = () => deriveCompanyAccess([office()], areas, provenance);

test('office contract requires every field and rejects unknown employment fields', () => {
  validateOffice(office());
  assert.equal(normalizeCompanyName(' Ａ  B '), 'a b');
  for (const key of officeSchema.required) {
    const value = office(); delete value[key];
    assert.throws(() => validateOffice(value), new RegExp(key));
  }
  assert.throws(() => validateOffice(office({ employment: 100 })), /Unknown/);
  assert.throws(() => validateOffice(office({ toString: 'unexpected' })), /Unknown/);
  for (const overrides of [
    {longitude: NaN}, {latitude: Infinity}, {longitude: 181}, {latitude: -91},
    {longitude: '121'}, {coordinate_system: 'GCJ02'}, {coordinate_system: 'BD09'},
    {min_reach_minutes: 15}, {min_reach_minutes: '10'}, {company_name: ' '},
    {normalized_name: 'wrong'}, {location_confidence: 'high'},
    {source_url: 'javascript:alert(1)'}, {source_url: 'https://u:p@example.invalid'},
    {source_type: 'unknown'}, {verified_at: 'yesterday'},
    {verified_at: '2026-02-30T00:00:00Z'}, {verified_at: '2026-09-20'},
    {location_confidence: 'verified'}, {hub_id: 'x'},
  ]) assert.throws(() => validateOffice(office(overrides)));
  validateOffice(office({location_confidence: 'verified', verified_at: '2026-09-20T00:00:00Z'}));
});

test('minimum reach, all five thresholds, and null outside reach are geometric', () => {
  for (const [x, expected] of [[0,10],[1,10],[1.5,20],[2.5,30],[3.5,40],[4.5,50],[6,null]]) {
    const value = deriveCompanyAccess([office({longitude:x,min_reach_minutes:expected})], areas, provenance);
    assert.equal(value.offices.features[0].properties.min_reach_minutes, expected);
    assert.equal(selectCompanyOffices(value, 'all').features.length, expected === null ? 0 : 1);
  }
  assert.throws(() => deriveCompanyAccess([office({min_reach_minutes:20})], areas, provenance), /Stale/);
  assert.throws(() => selectCompanyOffices(output(), 15), /limit/);
});

test('Polygon holes, hole boundaries, MultiPolygon and non-nested reach are explicit', () => {
  const geometry = structuredClone(areas);
  geometry.features[0].geometry = {type:'MultiPolygon', coordinates:[[ring(1), ring(0.25)], [ring(0.1).map(([x,y])=>[x+8,y])]]};
  const middle = deriveCompanyAccess([office({min_reach_minutes:20})], geometry, provenance);
  assert.equal(middle.offices.features[0].properties.min_reach_minutes,20);
  assert.equal(deriveCompanyAccess([office({longitude:0.25})], geometry, provenance).offices.features[0].properties.min_reach_minutes,10);
  const island = deriveCompanyAccess([office({longitude:8})], geometry, provenance);
  assert.equal(selectCompanyOffices(island,10).features.length,1);
  assert.equal(selectCompanyOffices(island,20).features.length,0);
  assert.equal(selectCompanyOffices(island,'all').features.length,0);
  assert.deepEqual(island.metadata.quality.non_nested_memberships,['test-office-a']);
});

test('missing, duplicate and malformed polygons fail closed', () => {
  for (const mutate of [a=>a.features.pop(), a=>a.features[0].properties.limit=20,
    a=>a.features[0].geometry.coordinates[0].pop(), a=>a.features[0].geometry.type='Point']) {
    const bad = structuredClone(areas); mutate(bad);
    assert.throws(() => deriveCompanyAccess([],bad,provenance));
  }
});

test('duplicates fail without merging same-name physical offices; hub counts use members', () => {
  const first = office({hub_id:'hub-test',hub_name:'Synthetic hub'});
  const second = office({id:'test-office-b',longitude:2.5,source_id:'test-source-b',min_reach_minutes:30,hub_id:'hub-test',hub_name:'Synthetic hub'});
  const input = [first,second];
  const snapshot = structuredClone(input);
  const value = deriveCompanyAccess(input,areas,provenance);
  assert.deepEqual(input,snapshot);
  assert.deepEqual(deriveCompanyAccess([...input].reverse(),areas,provenance),value);
  assert.equal(value.hubs.features[0].properties.office_count,2);
  assert.equal(value.hubs.features[0].properties.counts_by_reach[10],1);
  assert.deepEqual(value.summary.records.map(r=>r.office_count),[1,1,2,2,2]);
  assert.deepEqual(value.summary.records.map(r=>r.hub_count),[1,1,1,1,1]);
  assert.deepEqual(value.metadata.quality.repeated_normalized_names,['test a']);
  assert.throws(() => deriveCompanyAccess([first,first],areas,provenance), /Duplicate office/);
  assert.throws(() => deriveCompanyAccess([first,{...first,id:'different'}],areas,provenance), /Duplicate source/);
  assert.throws(() => deriveCompanyAccess([first,{...second,hub_name:'conflict'}],areas,provenance), /Conflicting hub/);
  assert.throws(() => deriveCompanyAccess([],areas,{...provenance,reach_sha256:null}), /provenance/);
});

test('all four derived outputs validate against source inventory and geometry', () => {
  const value = output();
  validateCompanyAccessOutput(value,[office()],areas,provenance);
  for (const key of ['offices','hubs','summary','metadata']) {
    const bad = structuredClone(value); bad[key] = {};
    assert.throws(() => validateCompanyAccessOutput(bad,[office()],areas,provenance), new RegExp(key));
  }
});

test('unloaded differs from genuine zero; counts never represent employment or citywide coverage', () => {
  const unloaded = deriveCompanyAccess([],areas,{...provenance,status:'not_loaded'});
  assert.equal(unloaded.summary.records[0].office_count,null);
  assert.equal(companyPanelState(unloaded,50).enabled,false);
  assert.equal(companyPanelState(null,50).enabled,false);
  const empty = deriveCompanyAccess([],areas,provenance);
  assert.equal(empty.summary.records[0].office_count,0);
  assert.match(companyPanelState(empty,'all').message,/0 identified offices/);
  assert.equal(empty.metadata.employment_estimation_permitted,false);
  assert.equal(empty.metadata.coverage,'source_inventory_only');
  assert.throws(() => deriveCompanyAccess([office()],areas,{...provenance,status:'not_loaded'}));
});

function fakeMap() {
  return {
    sources:new Map(), layers:new Map([['station-circle',{}]]), events:[], canvas:{style:{}}, style:createRasterStyle('a','base',[],'test'),
    getStyle(){return this.style;}, getSource(id){return this.sources.get(id);}, getLayer(id){return this.layers.get(id);},
    addSource(id,source){assert.equal(this.sources.has(id),false);this.sources.set(id,{...source,setData(data){this.data=data;}});},
    addLayer(layer,before){assert.equal(this.layers.has(layer.id),false);assert.equal(before,'station-circle');this.layers.set(layer.id,layer);},
    setLayoutProperty(id,key,value){this.layers.get(id)[key]=value;},
    on(...args){this.events.push(args);}, off(...args){this.events=this.events.filter(e=>e.some((v,i)=>v!==args[i]));},
    getCanvas(){return this.canvas;}, removeLayer(id){this.layers.delete(id);}, removeSource(id){this.sources.delete(id);},
    getCenter(){return {toArray:()=>[121,31]};},getZoom(){return 10;},getPitch(){return 0;},getBearing(){return 0;},jumpTo(){},
    setStyle(style){this.style=style;this.sources.clear();this.layers.clear();},
  };
}

test('MapLibre restore preserves state, layer ordering and handlers over repeated and rapid switches', () => {
  const map=fakeMap(); const selected=[];
  const controller=new CompanyAccessLayers(map,office=>selected.push(office.id));
  controller.setState({output:output(),limit:20,visible:true});
  const coordinator=new StyleSwitchCoordinator(map,'a',()=>{
    map.layers.set('station-circle',{});return controller.restore();
  });
  for (let i=0;i<5;i++) {
    coordinator.switchTo(`map-${i}`,createRasterStyle(`map-${i}`,'base',[],'test'));
    assert.equal(coordinator.handleStyleLoad(),true);
    controller.restore();
    assert.equal(map.getSource(COMPANY_SOURCE).data.features.length,1);
    assert.equal(map.getLayer(COMPANY_LAYER).visibility,'visible');
  }
  coordinator.switchTo('stale',createRasterStyle('stale','base',[],'test'));
  coordinator.switchTo('latest',createRasterStyle('latest','base',[],'test'));
  map.style.metadata.jinkeBasemap='stale';
  assert.equal(coordinator.handleStyleLoad(),false);
  map.style.metadata.jinkeBasemap='latest';
  assert.equal(coordinator.handleStyleLoad(),true);
  assert.equal(map.events.filter(e=>e[1]===COMPANY_LAYER).length,3);
  map.events.find(e=>e[0]==='click' && e[1]===COMPANY_LAYER)[2]({features:[{id:'test-office-a'}]});
  assert.deepEqual(selected,['test-office-a']);
  controller.setState({visible:false});
  assert.equal(map.getLayer(COMPANY_LAYER).visibility,'none');
  controller.destroy();
  assert.equal(map.getSource(COMPANY_SOURCE),undefined);
  assert.equal(map.events.filter(e=>e[1]===COMPANY_LAYER).length,0);
});

test('company scaffold never modifies approved data or economic/reach model code', () => {
  const baseline=JSON.parse(readFileSync(new URL('./fixtures/company-access-economic-baseline.json',import.meta.url)));
  for (const [path,expected] of Object.entries(baseline)) {
    assert.equal(createHash('sha256').update(readFileSync(new URL(`../${path}`,import.meta.url))).digest('hex'),expected,path);
  }
  const reach=JSON.parse(readFileSync(new URL('../web/public/data/reach-office-employment.json',import.meta.url)));
  const fifty=reach.benchmarks.core_plus_base.records.find(r=>r.limit_minutes===50);
  assert.equal(fifty.employment_inside_reach,1212066.7132367718);
  assert.equal(fifty.employment_inside_reach.toFixed(6),'1212066.713237');
  assert.equal(fifty.percentage_of_shanghai.toFixed(7),'37.6335253');
  const actualAreas=JSON.parse(readFileSync(new URL('../web/public/data/reach-areas.geojson',import.meta.url)));
  deriveCompanyAccess([],actualAreas,{...provenance,status:'not_loaded'});
});

test('cluster sources contain only exact selected reach members; stale leaf requests are ignored', async()=>{
  const {CLUSTER_LAYER,COUNT_LAYER}=await import('../web/src/company-access/layers.js');
  const data=deriveCompanyAccess([office(),office({id:'b',source_id:'b',longitude:2.5,min_reach_minutes:30})],areas,provenance);
  const map=fakeMap(),selected=[],controller=new CompanyAccessLayers(map,x=>selected.push(x));
  controller.setState({output:data,limit:20,visible:true});
  assert.equal(map.getSource(COMPANY_SOURCE).cluster,true);assert.equal(map.getSource(COMPANY_SOURCE).data.features.length,1);
  assert.deepEqual(map.getLayer(COUNT_LAYER).layout['text-field'],['to-string',['get','point_count']]);
  controller.setState({limit:30});assert.equal(map.getSource(COMPANY_SOURCE).data.features.length,2);
  let resolve;map.getSource(COMPANY_SOURCE).getClusterLeaves=()=>new Promise(r=>{resolve=r;});
  const click=map.events.find(e=>e[0]==='click'&&e[1]===CLUSTER_LAYER)[2];
  const pending=click({features:[{properties:{cluster_id:1}}]});controller.setState({limit:10});resolve(data.offices.features);await pending;assert.equal(selected.length,0);
  map.getSource(COMPANY_SOURCE).getClusterLeaves=async()=>data.offices.features;
  await click({features:[{properties:{cluster_id:2}}]});assert.equal(selected[0].office_count,1);
  controller.setState({limit:'all'});assert.equal(map.getSource(COMPANY_SOURCE).data.features.length,2);
  controller.destroy();assert.equal(map.events.length,0);
});
test('review loader is inactive in normal builds and analytics use exact membership differences',async()=>{
  const {loadCompanyReview}=await import('../web/src/company-access/review-loader.js');
  const {companyAnalytics}=await import('../web/src/company-access/panel.js');
  assert.equal(await loadCompanyReview({enabled:false,fetchJson:()=>assert.fail('Production must not fetch pilot data')}),null);
  const data=deriveCompanyAccess([office(),office({id:'b',source_id:'b',longitude:2.5,min_reach_minutes:30})],areas,provenance);
  assert.equal(companyAnalytics(data,30).incremental,1);assert.equal(companyAnalytics(data,40).incremental,0);
  data.metadata.dataset_kind='candidate';data.metadata.ingestion={publication_status:'offline_candidate_not_published'};
  const files={'company-offices.geojson':data.offices,'company-hubs.geojson':data.hubs,'company-reach-summary.json':data.summary,'company-access-metadata.json':data.metadata};
  assert.equal((await loadCompanyReview({enabled:true,areas,fetchJson:async n=>files[n]})).offices.features.length,2);
  const bad=structuredClone(files);bad['company-offices.geojson'].features[0].properties.reach_minutes=[50];
  await assert.rejects(loadCompanyReview({enabled:true,areas,fetchJson:async n=>bad[n]}),/reconcile/);
});
