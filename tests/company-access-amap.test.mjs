import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, rm } from 'node:fs/promises';
import { requestAmap } from '../hosting/server/amap-client.mjs';
import { searchPlaces } from '../hosting/server/map-runtime.mjs';
import { runCompanyAccessPilot } from '../hosting/server/company-access-job.mjs';
import { planQueries, POLICY } from '../scripts/company-access/amap/plan.mjs';
import { acquire, candidatesFromCache, validateSnapshot } from '../scripts/company-access/amap/acquire.mjs';
import { reviewRows, toCSV, parseCSV, approvedFromReview, qaReport } from '../scripts/company-access/amap/review.mjs';
import { prepareFiles, importFiles } from '../scripts/company-access/amap/files.mjs';
import { ingest } from '../scripts/company-access/ingest.mjs';
import { stable,sha256 } from '../scripts/company-access/common.mjs';
import { wgs84ToGcj02 } from '../web/src/location-search.js';
const areas=JSON.parse(await readFile(new URL('../web/public/data/reach-areas.geojson',import.meta.url)));
const env={JINKE_AMAP_KEY:'SYNTHETIC_TEST_CREDENTIAL_ONLY'}, collectedAt='2026-09-22T00:00:00Z';
const poi=(id,point=[121.59,31.155],extra={})=>({id,name:`SYNTHETIC company ${id}`,type:'公司企业;公司',typecode:'170200',address:`SYNTHETIC address ${id}`,adname:'浦东新区',adcode:'310115',location:wgs84ToGcj02(...point).join(','),...extra});
const response=pois=>Response.json({status:'1',count:String(pois.length),pois});
async function fixture(){let count=0;return acquire({env,areas,collectedAt,sleep:async()=>{},fetchFn:async()=>response(count++===0?[poi('a'),poi('b',[121.585,31.205]),poi('c',[121.585,31.195])]:[])});}
const review=(bundle,states)=>toCSV(reviewRows(bundle.candidates).map((r,i)=>({...r,review_status:states[i]||'pending',review_notes:'Synthetic reviewer note, with "quotes"\nand newline'})));
const approve=(bundle,csv)=>approvedFromReview({snapshot:bundle.snapshot,areas,csv,reviewer:'Synthetic tester',reviewedAt:collectedAt});
test('production-derived search and job share the sole secret and request client',async()=>{
  let url;const r=await searchPlaces(new Request('https://example.test/api/location-search?q=test'),env,async u=>{url=new URL(u);return response([poi('a')]);});
  assert.equal(r.status,200);assert.equal(url.pathname,'/v5/place/text');assert.equal(url.searchParams.get('key'),env.JINKE_AMAP_KEY);
  assert.equal(url.searchParams.get('region'),'310000');assert.ok(!(await r.text()).includes(env.JINKE_AMAP_KEY));
  for(const file of ['amap-client.mjs','map-runtime.mjs','company-access-job.mjs']){const source=await readFile(new URL(`../hosting/server/${file}`,import.meta.url),'utf8');assert.doesNotMatch(source,/AMAP_WEB_SERVICE_KEY/);}
});
test('missing configuration makes zero requests and produces a resumable report',async()=>{
  let calls=0;const result=await runCompanyAccessPilot({}, {reachAreas:areas,collectedAt}, {fetchFn:async()=>{calls++;throw Error();}});
  assert.equal(calls,0);assert.equal(result.execution.stop_reason,'AMAP_NOT_CONFIGURED');
  await assert.rejects(requestAmap({},'polygon',{}),{code:'AMAP_NOT_CONFIGURED'});
  await assert.rejects(runCompanyAccessPilot(env,{reachAreas:areas,collectedAt}),{code:'PRIVATE_CHECKPOINT_REQUIRED'});
  await assert.rejects(runCompanyAccessPilot(env,{reachAreas:{},collectedAt}),{code:'PILOT_REACH_CHANGED'});
});
test('16 deterministic cells use GCJ rectangles; pages are round-robin and bounded',()=>{
  const plan=planQueries(areas);assert.deepEqual(plan,planQueries(structuredClone(areas)));assert.equal(plan.cells.length,16);assert.equal(plan.queries.length,48);
  assert.equal(plan.queries[16].page,2);assert.equal(plan.queries[0].parameters.types,'170200');assert.ok(plan.queries.every(q=>!Object.hasOwn(q.parameters,'key')));
  assert.notEqual(plan.cells[0].polygon_gcj02.split(',')[0],plan.cells[0].bbox_wgs84[0].toFixed(6));
});
test('pagination does not interpret v5 count as a total; pauses each call; cached replay zero calls',async()=>{
  const waits=[],pages=[];let calls=0;
  const first=await acquire({env,areas,collectedAt,sleep:async ms=>waits.push(ms),fetchFn:async u=>{calls++;const url=new URL(u);pages.push(url.searchParams.get('page_num'));return response(calls===1?Array.from({length:25},(_,i)=>poi(`p${i}`)):[]);}});
  assert.equal(calls,17);assert.equal(pages.at(-1),'2');assert.ok(waits.every(ms=>ms===1100));
  const second=await acquire({env:{},areas,previous:first.snapshot,sleep:async()=>assert.fail('cached sleep'),fetchFn:async()=>assert.fail('cached network')});
  assert.equal(second.execution.api_requests_this_execution,0);assert.equal(second.execution.cached_requests_this_execution,17);assert.deepEqual(first.candidates,second.candidates);
});
test('provider failures retry only transient errors and are sanitized',async()=>{
  let n=0;const waits=[];
  const retry=await acquire({env,areas,collectedAt,sleep:async ms=>waits.push(ms),fetchFn:async()=>++n===1?new Response('',{status:503}):response([])});
  assert.equal(retry.execution.api_requests_total,17);assert.equal(waits[1],2200);
  for(const mock of [async()=>new Response('',{status:429}),async()=>Response.json({status:'0',info:env.JINKE_AMAP_KEY}),async()=>Response.json({status:'1',pois:[],echo:env.JINKE_AMAP_KEY})]){
    const result=await acquire({env,areas,collectedAt,sleep:async()=>{},fetchFn:mock});assert.equal(result.execution.api_requests_this_execution,1);assert.ok(!stable(result).includes(env.JINKE_AMAP_KEY));
    const resume=await acquire({env,areas,previous:result.snapshot,sleep:async()=>{},fetchFn:async()=>assert.fail('fatal resume')});assert.equal(resume.execution.api_requests_this_execution,0);
  }
  await assert.rejects(requestAmap(env,'polygon',{},async()=>{throw Error(env.JINKE_AMAP_KEY);}),{code:'AMAP_NETWORK'});
  await assert.rejects(requestAmap(env,'polygon',{},async()=>new Response('not json')),{code:'AMAP_INVALID_JSON'});
});
test('lifetime request and candidate limits cannot grow by resuming',async()=>{
  const result=await acquire({env,areas,collectedAt,sleep:async()=>{},fetchFn:async()=>response(Array.from({length:25},(_,i)=>poi(`p${i}`)))});
  assert.equal(result.execution.api_requests_total,24);const again=await acquire({env,areas,previous:result.snapshot,sleep:async()=>{},fetchFn:async()=>assert.fail('budget')});assert.equal(again.execution.api_requests_this_execution,0);
  let n=0;const capped=await acquire({env,areas,collectedAt,sleep:async()=>{},fetchFn:async()=>response(Array.from({length:25},()=>poi(`n${n++}`)))});
  assert.equal(capped.candidates.length,200);assert.equal(capped.execution.api_requests_this_execution,8);assert.equal(capped.execution.stop_reason,'CANDIDATE_CAP');
});
test('stable IDs, conflicts, invalid coordinates, scope and exact WGS clipping are audited',async()=>{
  let n=0;const p=[poi('a'),poi('a'),poi('outside',[121,30.8]),poi('invalid',undefined,{location:'unknown'}),poi('conflict'),poi('conflict',undefined,{address:'different'}),poi('retail',undefined,{typecode:'060000'}),poi('b',undefined,{name:'SYNTHETIC company a',address:'SYNTHETIC address a'})];
  const result=await acquire({env,areas,collectedAt,sleep:async()=>{},fetchFn:async()=>response(n++===0?p:[])});
  assert.equal(result.candidates.length,2);assert.equal(result.counts.overlap_duplicates,2);assert.equal(result.counts.outside_30_minute_rejects,1);assert.equal(result.counts.coordinate_failures,1);assert.equal(result.counts.provider_id_conflicts,1);
  const c=result.candidates[0];assert.equal(c.raw.source_type,'licensed_poi');assert.equal(c.raw.coordinate_system,'GCJ02');assert.equal(c.raw.source_evidence.reviewed,false);assert.equal(c.raw.industry_code,null);assert.equal(c.raw.sector,null);assert.equal(c.possible_duplicate,true);
  assert.ok(Math.abs(c.longitude_wgs84-121.59)<1e-7);assert.equal(c.coordinate_provenance.raw_coordinate_system,'GCJ02');assert.ok(c.query_ids.length===2);
  const out=ingest({schema_version:1,dataset_kind:'candidate',dataset_version:'synthetic-test',records:result.candidates.map(c=>c.raw)},areas);assert.equal(out.offices.features.length,0);assert.equal(out.metadata.ingestion.dispositions.quarantined,2);
});
test('CSV Unicode/quotes/newlines and formula defense round-trip; immutable fields cannot change',async()=>{
  const bundle=await fixture(),rows=reviewRows(bundle.candidates);rows[0].company_name='=SYNTHETIC_FORMULA';rows[0].review_notes='甲,"乙"\n丙';
  const parsed=parseCSV(toCSV(rows));assert.equal(parsed[0].company_name,"'=SYNTHETIC_FORMULA");assert.equal(parsed[0].review_notes,rows[0].review_notes);
  assert.throws(()=>approve(bundle,toCSV(rows)),{code:'IMMUTABLE_REVIEW_FIELD'});
  assert.throws(()=>parseCSV('"unclosed'),{code:'INVALID_CSV'});
});
test('accept/reject/pending decisions rebuild via unchanged Phase 2; industry/hubs remain unknown',async()=>{
  const bundle=await fixture(),csv=review(bundle,['accept','reject','pending']),result=approve(bundle,csv);
  assert.equal(result.envelope.records.length,1);assert.equal(result.artifacts.offices.features.length,1);const p=result.artifacts.offices.features[0].properties;
  assert.equal(p.location_confidence,'building');assert.equal(p.industry_code,null);assert.equal(p.hub_id,null);assert.equal(p.verified_at,null);assert.equal(p.min_reach_minutes,30);
  assert.deepEqual(approve(bundle,csv),result);assert.ok(result.decisions[0].notes.includes('newline'));assert.equal(result.decisions.length,3);
  const report=qaReport(bundle,result);assert.equal(report.accepted_count,1);assert.equal(report.rejected_count,1);assert.equal(report.pending_count,1);assert.equal(report.final_exact_reach_membership_counts[30],1);
});
test('missing, duplicated, unknown and invalid decisions fail closed',async()=>{
  const b=await fixture(),rows=reviewRows(b.candidates);
  for(const bad of [rows.slice(1),[...rows,rows[0]],rows.map((r,i)=>i? r:{...r,review_status:'approved'}),rows.map((r,i)=>i?r:{...r,amap_poi_id:'unknown'})])assert.throws(()=>approve(b,toCSV(bad)));
  const mutated=structuredClone(b.snapshot);mutated.responses[0].payload.pois[0].address='changed';assert.throws(()=>validateSnapshot(mutated,areas),{code:'INVALID_CACHE'});
});
test('checkpoint receives key-free durable state and preserves successful pages after failure',async()=>{
  const saved=[];let n=0;const b=await acquire({env,areas,collectedAt,sleep:async()=>{},checkpoint:async s=>saved.push(s),fetchFn:async()=>++n===2?new Response('',{status:429}):response([poi('a')])});
  assert.equal(saved.at(-1).responses.length,1);assert.equal(b.snapshot.responses.length,1);assert.ok(!stable(saved).includes(env.JINKE_AMAP_KEY));
});
test('offline files separate private evidence from compact artifacts; no tracked output overwrite',async()=>{
  const b=await fixture(),root=new URL('../offline-output/company-access/',import.meta.url),run=new URL('synthetic-amap-test/',root),approved=new URL('synthetic-amap-approved/',root);
  const {mkdir,writeFile}=await import('node:fs/promises');await mkdir(root,{recursive:true});const input=new URL('synthetic-snapshot.json',root);await writeFile(input,stable(b.snapshot));
  try{
    await prepareFiles({snapshotPath:input,output:run.pathname});const csvPath=new URL('review/amap-office-review.csv',run);await writeFile(csvPath,review(b,['accept']));
    await importFiles({snapshotPath:input,csvPath,output:approved.pathname,reviewer:'Synthetic tester',reviewedAt:collectedAt});
    const frontend=JSON.parse(await readFile(new URL('frontend/company-offices.geojson',approved)));assert.equal(frontend.features.length,1);assert.ok(!stable(frontend).includes('query_ids'));
    assert.equal(JSON.parse(await readFile(new URL('audit/human-review.json',approved))).decisions.length,3);
    await assert.rejects(prepareFiles({snapshotPath:input,output:run.pathname}));await assert.rejects(prepareFiles({snapshotPath:input,output:new URL('../web/public/data',import.meta.url).pathname}),{code:'UNSAFE_OUTPUT_DIRECTORY'});
  }finally{await rm(run,{recursive:true,force:true});await rm(approved,{recursive:true,force:true});await rm(input,{force:true});}
});
test('exact clipping excludes points inside the bbox but outside the 30-minute polygon',async()=>{
  const {prepareReachAreas}=await import('../web/src/company-access/model.js');const reach=prepareReachAreas(areas);
  const [w,s,e,n]=planQueries(areas).bbox_wgs84;let point;
  for(let y=1;y<20&&!point;y++)for(let x=1;x<20&&!point;x++){const p=[w+(e-w)*x/20,s+(n-s)*y/20];if(!reach.contains(p,30))point=p;}
  assert.ok(point);let calls=0;const result=await acquire({env,areas,collectedAt,sleep:async()=>{},fetchFn:async()=>response(calls++===0?[poi('bbox-only',point)]:[])});
  assert.equal(result.candidates.length,0);assert.equal(result.counts.outside_30_minute_rejects,1);
});
test('different accepted provider IDs still undergo conservative Phase 2 deduplication',async()=>{
  let n=0;const result=await acquire({env,areas,collectedAt,sleep:async()=>{},fetchFn:async()=>response(n++===0?[poi('a'),poi('b',undefined,{name:'SYNTHETIC company a',address:'SYNTHETIC address a'})]:[])});
  const csv=review(result,['accept','accept']),approved=approve(result,csv);assert.equal(approved.envelope.records.length,2);assert.equal(approved.artifacts.offices.features.length,1);assert.equal(approved.artifacts.metadata.ingestion.dispositions.duplicates,1);
  const reversed=toCSV(reviewRows(result.candidates).map(r=>({...r,review_status:'accept',review_notes:'Synthetic reviewer note, with "quotes"\nand newline'})).reverse());assert.deepEqual(approved.artifacts,approve(result,reversed).artifacts);
});
test('runtime routes retain existing environment binding; static browser build excludes acquisition',async()=>{
  const route=await readFile(new URL('../hosting/app/api/amap-place-search/route.ts',import.meta.url),'utf8');assert.match(route,/from 'cloudflare:workers'/);assert.match(route,/searchPlaces\(request, env\)/);
  const alias=await readFile(new URL('../hosting/app/api/location-search/route.ts',import.meta.url),'utf8');assert.match(alias,/amap-place-search\/route/);
  const {readdir}=await import('node:fs/promises');for(const name of await readdir(new URL('../web/src/',import.meta.url))){if(!name.endsWith('.js'))continue;const code=await readFile(new URL(`../web/src/${name}`,import.meta.url),'utf8');assert.doesNotMatch(code,/JINKE_AMAP_KEY|company-access-job|amap-client|amap\/acquire/);}
});
