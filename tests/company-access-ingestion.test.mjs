import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { mkdtemp, readFile, writeFile, readdir, symlink, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { ingest, validateArtifacts, artifactNames } from '../scripts/company-access/ingest.mjs';
import { validateRawRecord, rawSchema } from '../scripts/company-access/validate.mjs';
import { normalizeRecord, addressKey } from '../scripts/company-access/normalize.mjs';
import { normalizeCoordinates, bd09ToGcj02 } from '../scripts/company-access/coordinates.mjs';
import { classifyIndustry, classifyLocation, CORE_PLUS_CODES } from '../scripts/company-access/classify.mjs';
import { stable, sha256, distance, validateSettings } from '../scripts/company-access/common.mjs';
import { buildFiles, main } from '../scripts/company-access/build.mjs';
import { prepareReachAreas, validateReachAreas, reachMemberships } from '../web/src/company-access/model.js';
import { validateOffice } from '../web/src/company-access/schema.js';
import { gcj02ToWgs84 } from '../web/src/location-search.js';
const read=path=>JSON.parse(readFileSync(new URL(path,import.meta.url),'utf8'));
const pilot=read('./fixtures/company-access/pilot.json');
const realAreas=read('../web/public/data/reach-areas.geojson');
const coordinates=read('./fixtures/company-access/coordinates.json').vectors;
const pilotPath=resolve('tests/fixtures/company-access/pilot.json');
const base=pilot.records[0];
const raw=(id,extra={})=>({...structuredClone(base),source_record_id:id,company_name:`SYNTHETIC ${id}`,address:`SYNTHETIC ADDRESS ${id}`,
  company_identity:undefined,name_variants:undefined,hub_candidates:undefined,industry_code:null,sector:null,classification_evidence:undefined,...extra});
// Match JSON file semantics: optional keys are absent, never undefined.
const row=(id,extra={})=>JSON.parse(JSON.stringify(raw(id,extra)));
const input=records=>({schema_version:1,dataset_kind:'synthetic',dataset_version:'unit-fixture-v1',records});
const run=(records,settings={})=>ingest(input(records),realAreas,{settings});
const reasons=result=>result.rejected.records.flatMap(r=>r.reason_codes);

test('known coordinate fixtures and shared AMap inverse remain consistent',()=>{
  for(const vector of coordinates){
    if(vector.expected_gcj02){
      const converted=bd09ToGcj02(...vector.raw);
      converted.forEach((n,i)=>assert.ok(Math.abs(n-vector.expected_gcj02[i])<=vector.tolerance_degrees));
      const output=normalizeCoordinates({longitude:vector.raw[0],latitude:vector.raw[1],coordinate_system:vector.crs});
      assert.deepEqual(output.coordinates,gcj02ToWgs84(...converted));
    }else{
      const output=normalizeCoordinates({longitude:vector.raw[0],latitude:vector.raw[1],coordinate_system:vector.crs});
      output.coordinates.forEach((n,i)=>assert.ok(Math.abs(n-vector.expected[i])<=vector.tolerance_degrees));
      assert.equal(output.audit.raw_coordinate_system,vector.crs);
    }
  }
  for(const point of [[null,31],[NaN,31],[121,91],['121',31]])assert.throws(()=>normalizeCoordinates({longitude:point[0],latitude:point[1],coordinate_system:'WGS84'}));
  assert.throws(()=>normalizeCoordinates({longitude:121,latitude:31,coordinate_system:'unknown'}),{code:'UNKNOWN_COORDINATE_SYSTEM'});
  assert.throws(()=>normalizeCoordinates({longitude:0,latitude:0,coordinate_system:'BD09'}),{code:'CONVERSION_OUTSIDE_SUPPORTED_REGION'});
});

test('raw schema is independent, rejects ambiguous input and requires provenance',()=>{
  validateRawRecord(base);
  for(const key of rawSchema.required){const bad=structuredClone(base);delete bad[key];assert.throws(()=>validateRawRecord(bad),{code:'RAW_MISSING_FIELD'});}
  for(const extra of [{collected_at:'2026-02-30T00:00:00Z'},{source_url:'file:///secret'},{longitude:'121'},
    {source_evidence:'trust me'},{office_identity:{id:'x',reviewed:false,source_url:'https://example.invalid'}},{employment:100},
    {toString:'unexpected'}])assert.throws(()=>validateRawRecord({...base,...extra}));
  const result=run([row('unknown',{coordinate_system:'unknown'}),row('missing-coordinate',{latitude:null})]);
  assert.deepEqual(result.metadata.ingestion.dispositions,{accepted:0,duplicates:0,conflicts:0,quarantined:1,rejected:1});
  assert.ok(reasons(result).includes('UNKNOWN_COORDINATE_SYSTEM'));
  assert.throws(()=>ingest({...input([]),dataset_kind:'production'},realAreas),{code:'INVALID_RAW_ENVELOPE'});
  assert.throws(()=>validateSettings({duplicate_metres:-1}),{code:'INVALID_SETTINGS'});
});

test('normalization retains legal suffixes and unit numbers; aliases need explicit identity',()=>{
  const normalized=normalizeRecord(row('name',{company_name:'  ＡＢＣ   有限公司 ',address:' Ｒｏａｄ ，  1 号 ( 201 ) ',district:'Pudong New Area',building_name:'  合成　大楼 ',name_variants:[' ABC 有限公司 ','ＡＢＣ 有限公司']}));
  assert.equal(normalized.company_name,'ABC 有限公司');
  assert.equal(normalized.normalized_name,'abc 有限公司');
  assert.equal(normalized.district,'浦东新区');
  assert.equal(normalized.building_name,'合成 大楼');
  assert.equal(normalized.name_variants.length,1);
  assert.equal(addressKey('Road ， 1 ( 201 )'),'road,1(201)');
  assert.notEqual(addressKey('Road 1 (201)'),addressKey('Road 1 (202)'));
  assert.equal(run([row('a',{company_name:'ABC Ltd'}),row('b',{company_name:'ABC',address:'SYNTHETIC ADDRESS a'})]).offices.features.length,2);
});

test('physical-office confidence uses evidence, not address completeness or arbitrary scores',()=>{
  assert.equal(classifyLocation(base).location_confidence,'verified');
  assert.equal(classifyLocation({...base,verified_at:null}).location_confidence,'approximate');
  assert.equal(classifyLocation({...base,source_evidence:{...base.source_evidence,reviewed:false}}).location_confidence,'approximate');
  assert.equal(classifyLocation({...base,source_type:'licensed_poi'}).location_confidence,'approximate');
  const mapped=row('mapped',{source_type:'osm',source_evidence:{kind:'map_poi',description:'SYNTHETIC mapped office',reviewed:true}});
  assert.equal(run([mapped]).offices.features[0].properties.location_confidence,'building');
  const registered=row('registered',{source_evidence:{kind:'registered_address',description:'SYNTHETIC registered address only',reviewed:true}});
  assert.ok(reasons(run([registered])).includes('REGISTERED_ADDRESS_ONLY'));
  assert.equal(run([registered],{include_approximate:true}).metadata.ingestion.approximate_office_count,1);
});

test('industry classification is explicit, leaves unknowns unknown and excludes 726',()=>{
  const evidence=base.classification_evidence;
  assert.deepEqual(CORE_PLUS_CODES,read('../web/public/data/office-employment-methodology.json').definitions.core_plus_base.industry_codes);
  for(const code of ['I','J','M','721','723','724','725','7210']){
    const classified=classifyIndustry({...base,industry_code:code,classification_evidence:evidence});
    assert.equal(classified.core_plus_code,code==='7210'?'721':code);
  }
  assert.equal(classifyIndustry({...base,industry_code:'726',classification_evidence:evidence}).core_plus_code,null);
  assert.equal(classifyIndustry({...base,company_name:'SYNTHETIC Finance Technology Bank',classification_evidence:undefined}).industry_code,null);
  assert.equal(classifyIndustry({...base,classification_evidence:{...evidence,reviewed:false}}).industry_code,null);
  assert.equal(classifyIndustry({...base,classification_evidence:{...evidence,scheme:'unrecognized'}}).industry_code,null);
  assert.equal(classifyIndustry({...base,classification_evidence:{...evidence,kind:'reviewed_mapping'}}).classification_confidence,'reviewed_mapping');
});

test('source duplicates and cross-source exact office matches retain complete audit evidence',()=>{
  const a=row('a'),b={...a,source_record_id:'b',source_namespace:'synthetic-other-feed'};
  const result=run([a,{...a},b]);
  assert.equal(result.offices.features.length,1);
  assert.equal(result.review.duplicates.length,2);
  assert.equal(result.audit.accepted[0].sources.length,3);
  assert.equal(new Set(result.audit.accepted[0].record_refs).size,3);
  assert.ok(result.review.duplicates.every(d=>d.accepted_office_id===result.offices.features[0].id));
});

test('reviewed bilingual identity can merge aliases; an entity may have multiple offices',()=>{
  const identity={id:'synthetic-entity',reviewed:true,source_url:'https://example.invalid/identity'};
  const a=row('a',{company_name:'合成测试有限公司',company_identity:identity}),
    b=row('b',{company_name:'SYNTHETIC TEST LTD',company_identity:identity,address:a.address});
  assert.equal(run([a,b]).offices.features.length,1);
  assert.equal(run([a,{...b,address:'SYNTHETIC SECOND OFFICE'}]).offices.features.length,2);
  const {company_identity:unused,...plainB}=b;
  assert.equal(run([a,plainB]).offices.features.length,2);
});

test('same source ID disagreements and uncertain coordinates quarantine every affected record',()=>{
  const a=row('a'),b={...a,longitude:a.longitude+0.01};
  const location=run([a,b]);
  assert.equal(location.offices.features.length,0);assert.ok(reasons(location).includes('LOCATION_CONFLICT'));
  assert.equal(location.metadata.ingestion.dispositions.conflicts,2);
  assert.ok(reasons(run([a,{...a,company_name:'SYNTHETIC ANOTHER ENTITY'}])).includes('SOURCE_ID_CONFLICT'));
  const classified={...a,industry_code:'I',classification_evidence:base.classification_evidence};
  assert.ok(reasons(run([classified,{...classified,source_record_id:'b',industry_code:'J'}])).includes('INDUSTRY_CONFLICT'));
});

test('duplicates use a fixed representative radius, never transitive proximity chaining',()=>{
  const a=row('a'),step=0.00012;
  const result=run([a,{...a,source_record_id:'b',longitude:a.longitude+step},
    {...a,source_record_id:'c',longitude:a.longitude+2*step,verified_at:'2026-09-18T00:00:00Z'}],{duplicate_metres:15});
  // Pin the preferred representative to the western endpoint.
  const anchored=run([ {...a,verified_at:'2026-09-20T00:00:00Z'},
    {...a,source_record_id:'b',longitude:a.longitude+step},
    {...a,source_record_id:'c',longitude:a.longitude+2*step}],{duplicate_metres:15});
  assert.equal(anchored.offices.features.length,0);
  assert.ok(reasons(anchored).includes('LOCATION_CONFLICT'));
  assert.ok(result.metadata.ingestion.dispositions.accepted<=1);
});

test('explicit office identity is distinct from legal-entity identity',()=>{
  const identity=id=>({id,reviewed:true,source_url:'https://example.invalid/office-identity'});
  const a=row('a',{office_identity:identity('office-a')});
  const b={...a,source_record_id:'b',address:'SYNTHETIC alternative address spelling'};
  assert.equal(run([a,b]).offices.features.length,1);
  const c={...a,source_record_id:'c',office_identity:identity('office-c')};
  assert.equal(run([a,c]).offices.features.length,2);
  assert.ok(reasons(run([a,{...c,source_record_id:a.source_record_id}])).includes('CONFLICTING_OFFICE_IDENTITIES'));
});

test('building assignment prefers reviewed physical buildings to campus, with typed hubs',()=>{
  const building=base.hub_candidates[0];
  const campus={...building,id:'synthetic-campus',kind:'reviewed_campus',name:'SYNTHETIC CAMPUS'};
  const mapped={...building,kind:'mapped_building'};
  const result=run([row('a',{hub_candidates:[campus,mapped,building]}),row('b',{hub_candidates:[building]})]);
  assert.equal(result.hubs.features.length,1);
  assert.equal(result.hubs.features[0].properties.office_count,2);
  assert.equal(result.hubs.features[0].properties.hub_kind,'physical_building');
  assert.equal(result.offices.features[0].properties.building_name,building.name);
  assert.equal(result.audit.accepted[0].hub.assignment_reason,'verified_building');
  const campusOnly=run([row('c',{hub_candidates:[campus]})]);
  assert.equal(campusOnly.hubs.features[0].properties.hub_kind,'named_campus');
  assert.equal(run([row('unknown',{building_name:'Unreviewed name'})]).offices.features[0].properties.hub_id,null);
});

test('contradictory hub definitions and ambiguous assignments enter conflict review',()=>{
  const building=base.hub_candidates[0];
  const result=run([row('a',{hub_candidates:[building]}),row('b',{hub_candidates:[{...building,name:'Conflicting name'}]})]);
  assert.equal(result.offices.features.length,0);assert.ok(reasons(result).includes('HUB_DEFINITION_CONFLICT'));
  assert.ok(reasons(run([row('a',{hub_candidates:[building,{...building,id:'another-id'}]})])).includes('AMBIGUOUS_HUB_ASSIGNMENT'));
});

test('algorithmic clusters are opt-in, deterministic seed-radius groups, never buildings',()=>{
  const records=[row('a'),row('b',{longitude:base.longitude+0.0001}),row('c',{longitude:base.longitude+0.01})];
  assert.equal(run(records).hubs.features.length,0);
  const value=run(records,{cluster_metres:40});
  assert.equal(value.hubs.features.length,1);
  assert.equal(value.hubs.features[0].properties.hub_kind,'spatial_cluster');
  assert.match(value.hubs.features[0].properties.hub_name,/^Unnamed office cluster/);
  assert.ok(value.offices.features.every(f=>f.properties.building_name===null));
  assert.equal(stable(value),stable(run([...records].reverse(),{cluster_metres:40})));
  assert.equal(value.offices.features.filter(f=>f.properties.hub_id===null).length,1);
});

test('pilot covers real cumulative thresholds and all raw dispositions without production loading',()=>{
  const result=ingest(pilot,realAreas);
  assert.deepEqual(result.metadata.ingestion.dispositions,{accepted:8,duplicates:2,conflicts:2,quarantined:2,rejected:1});
  assert.deepEqual([...new Set(result.offices.features.map(f=>f.properties.min_reach_minutes))].sort((a,b)=>(a??100)-(b??100)),[10,20,30,40,50,null]);
  for(const feature of result.offices.features){const {reach_minutes,...office}=feature.properties;validateOffice(office);}
  assert.equal(result.metadata.dataset_kind,'synthetic');
  assert.equal(result.metadata.employment_estimation_permitted,false);
  assert.equal(result.metadata.ingestion.publication_status,'offline_candidate_not_published');
  const browser=stable([result.offices,result.hubs,result.summary,result.metadata]);
  assert.ok(!browser.includes('raw_record'));assert.ok(!browser.includes('source_evidence'));assert.ok(!browser.includes('raw_coordinate_system'));
});

test('prepared exact reach agrees with unindexed implementation at vertices and dispersed points',()=>{
  const prepared=prepareReachAreas(realAreas),plain=validateReachAreas(realAreas);
  const points=[];
  for(const f of realAreas.features)for(const polygon of f.geometry.coordinates)points.push(...polygon[0].filter((_,i)=>i%7===0));
  for(let i=0;i<200;i++)points.push([121.1+(i%40)*0.022,30.9+Math.floor(i/40)*0.12]);
  for(const [longitude,latitude] of points)assert.deepEqual(reachMemberships({longitude,latitude},prepared),reachMemberships({longitude,latitude},plain));
});

test('artifacts reconcile and tampering with geometry, counts, provenance or duplicates fails',()=>{
  const output=ingest(pilot,realAreas);validateArtifacts(output,realAreas);
  for(const tamper of [o=>o.offices.features[0].geometry.coordinates[0]+=0.01,
    o=>o.summary.records[0].office_count++,o=>o.metadata.inventory_sha256='a'.repeat(64),
    o=>o.review.duplicates.pop(),o=>o.audit.accepted[0].record_refs.pop(),
    o=>o.hubs.features[0].properties.hub_kind='spatial_cluster',
    o=>o.audit.accepted[0].sources[0].coordinate_provenance.conversion_version='tampered',
    o=>o.audit.accepted[0].sources[0].raw_record.company_name='tampered',
    o=>o.review.conflicts=[],o=>o.metadata.ingestion.core_plus_office_count++]){
    const bad=structuredClone(output);tamper(bad);assert.throws(()=>validateArtifacts(bad,realAreas));
  }
});

test('reproducibility ignores input order and does not mutate raw inputs or reach polygons',()=>{
  const snapshot=stable(pilot),areasSnapshot=stable(realAreas);
  const first=ingest(pilot,realAreas),second=ingest({...pilot,records:[...pilot.records].reverse()},realAreas);
  assert.equal(stable(first),stable(second));assert.equal(stable(pilot),snapshot);assert.equal(stable(realAreas),areasSnapshot);
  assert.equal(first.metadata.ingestion.input_records_sha256,second.metadata.ingestion.input_records_sha256);
});

test('offline builder separates seven files, hashes exact bytes and is byte reproducible',async()=>{
  const tmp=await mkdtemp(join(tmpdir(),'jinke-ingest-'));
  try{
    for(const runName of ['first','second'])await buildFiles({inputs:[pilotPath],output:join(tmp,runName)});
    assert.equal((await readdir(join(tmp,'first/frontend'))).length,4);
    assert.equal((await readdir(join(tmp,'first/audit'))).length,3);
    for(const [key,name] of Object.entries(artifactNames)){
      const folder=['audit','rejected','review'].includes(key)?'audit':'frontend';
      assert.equal(await readFile(join(tmp,'first',folder,name),'utf8'),await readFile(join(tmp,'second',folder,name),'utf8'));
    }
    const metadata=JSON.parse(await readFile(join(tmp,'first/frontend/company-access-metadata.json'),'utf8'));
    assert.equal(metadata.reach_sha256,sha256(readFileSync('web/public/data/reach-areas.geojson')));
    await assert.rejects(()=>buildFiles({inputs:[pilotPath],output:join(tmp,'first')}),{code:'OUTPUT_ALREADY_EXISTS'});
    await assert.rejects(()=>buildFiles({inputs:[pilotPath],output:resolve('web/public/data/company-access-test')}),{code:'UNSAFE_OUTPUT_DIRECTORY'});
    await symlink(resolve('web/public/data'),join(tmp,'linked-web'));
    await assert.rejects(()=>buildFiles({inputs:[pilotPath],output:join(tmp,'linked-web/forbidden')}),{code:'UNSAFE_OUTPUT_DIRECTORY'});
    await assert.rejects(()=>main(['--input',pilotPath,'--paid-api','anything']),{code:'UNKNOWN_ARGUMENT'});
  }finally{await rm(tmp,{recursive:true,force:true});}
});


test('multi-source files combine deterministically and reject mixed envelopes or repeated input',async()=>{
  const tmp=await mkdtemp(join(tmpdir(),'jinke-multi-'));
  try{
    const a=join(tmp,'a.json'),b=join(tmp,'b.json');
    await writeFile(a,JSON.stringify({...pilot,records:pilot.records.slice(0,7)}));
    await writeFile(b,JSON.stringify({...pilot,records:pilot.records.slice(7)}));
    await buildFiles({inputs:[a,b],output:join(tmp,'ab')});
    await buildFiles({inputs:[b,a],output:join(tmp,'ba')});
    for(const [key,name] of Object.entries(artifactNames)){
      const folder=['audit','rejected','review'].includes(key)?'audit':'frontend';
      assert.equal(await readFile(join(tmp,'ab',folder,name),'utf8'),await readFile(join(tmp,'ba',folder,name),'utf8'));
    }
    await assert.rejects(()=>buildFiles({inputs:[a,a],output:join(tmp,'duplicate')}),{code:'DUPLICATE_INPUT_FILE'});
    await writeFile(b,JSON.stringify({...pilot,dataset_kind:'candidate',records:[]}));
    await assert.rejects(()=>buildFiles({inputs:[a,b],output:join(tmp,'mixed')}),{code:'MIXED_DATASET_ENVELOPES'});
  }finally{await rm(tmp,{recursive:true,force:true});}
});
