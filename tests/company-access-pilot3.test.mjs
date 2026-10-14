import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {planQueries} from '../scripts/company-access/amap/plan.mjs';
import {acquire,validateSnapshot} from '../scripts/company-access/amap/acquire.mjs';
import {makeReviewBundle} from '../scripts/company-access/amap/console.mjs';
import {coverageReport,importPilot3} from '../scripts/company-access/amap/pilot3-workflow.mjs';
import {attachReviewHistory} from '../web/src/company-access/review-history.js';
import {createSession,decide} from '../web/src/company-access/review-state.js';
import {approvedFromReview,reviewRows,toCSV} from '../scripts/company-access/amap/review.mjs';
import {wgs84ToGcj02} from '../web/src/location-search.js';
import {executePilot,assertKeyFree} from '../scripts/company-access/amap/actions-pilot.mjs';
import {previousPilotArtifact} from '../scripts/company-access/amap/resume-pilot3.mjs';
const areas=JSON.parse(await fs.readFile('web/public/data/reach-areas.geojson','utf8'));
const env={JINKE_AMAP_KEY:'SYNTHETIC_PILOT3_TEST_CREDENTIAL'},date='2026-10-13T00:00:00Z';
const poi=(id,name=id,x=121.597836)=>({id,name,address:'合成测试路1号',type:'公司企业;公司',typecode:'170200',location:wgs84ToGcj02(x,31.2064028).join(',')});
const mock=pois=>{let calls=0;return async()=>Response.json({status:'1',pois:calls++===0?pois:[]});};
const run=options=>acquire({env,areas,collectedAt:date,pilotVersion:'amap-pilot-3',sleep:async()=>{},...options});
async function failedCheckpoint(failures=2){
  const {snapshot}=await run({fetchFn:mock([poi('SYNTHETIC-CACHED')])});
  const query=snapshot.plan.queries[24];
  for(let i=0;i<failures;i++)snapshot.attempts.push({query_id:query.id,outcome:'failure',code:'AMAP_NETWORK',retryable:true});
  // Old run metadata is intentionally stale; recovery must derive from the ledger.
  return snapshot;
}
test('26/48 checkpoint skips exhausted query, keeps cache/history and spends only 22 remaining attempts',async()=>{
  const previous=await failedCheckpoint(),before=structuredClone(previous),visited=[];
  const result=await run({previous,fetchFn:async url=>{visited.push(Object.fromEntries(new URL(url).searchParams));return Response.json({status:'1',pois:[]});}});
  assert.equal(result.execution.api_requests_this_execution,22);assert.equal(result.execution.api_requests_total,48);
  assert.equal(result.execution.cached_requests_this_execution,24);assert.equal(result.execution.stop_reason,'REQUEST_BUDGET');
  assert.deepEqual(result.snapshot.responses.slice(0,24),before.responses);assert.deepEqual(result.snapshot.attempts.slice(0,26),before.attempts);assert.deepEqual(previous,before);
  assert.equal(result.candidates.length,1);assert.ok(makeReviewBundle([result.snapshot],areas).batches[0].rows.every(i=>i.row.review_status==='pending'));
  for(const q of before.plan.queries.slice(0,25))assert.ok(!visited.some(p=>p.polygon===q.parameters.polygon&&p.page_num===q.parameters.page_num));
  assert.deepEqual(result.execution.incomplete_queries,[{query_id:before.plan.queries[24].id,cell_id:before.plan.queries[24].cell_id,page:1,reason:'RETRY_EXHAUSTED'}]);
  const coverage=coverageReport(areas,result.snapshot),cell=coverage.features.find(f=>f.properties.cell_id===before.plan.queries[24].cell_id);
  assert.equal(cell.properties.status,'incomplete_acquisition');assert.equal(cell.properties.pages_returned,0);assert.equal(cell.properties.attempts,2);assert.equal(coverage.summary.pilot3_cells_incomplete,1);
});
test('isolated query failure in the current execution skips after one retry and continues other cells',async()=>{
  let calls=0;const result=await run({fetchFn:async()=>{if(++calls<=2)throw Error('synthetic transport failure');return Response.json({status:'1',pois:[]});}});
  assert.equal(calls,24);assert.equal(result.snapshot.responses.length,22);assert.equal(result.execution.incomplete_queries.length,1);assert.equal(result.execution.stop_reason,'EXECUTION_BUDGET');
  assert.equal(result.snapshot.attempts.filter(a=>a.query_id===result.snapshot.plan.queries[0].id).length,2);
});
test('broader network/server outage stops across cells and resumes with zero extra provider requests',async()=>{
  for(const http of [false,true]){
    const previous=await failedCheckpoint();let calls=0;
    const result=await run({previous,fetchFn:async()=>{calls++;if(http)return new Response('',{status:503});throw Error('synthetic network down');}});
    assert.equal(calls,2);assert.equal(result.execution.api_requests_total,28);assert.equal(result.execution.stop_reason,'AMAP_CONNECTIVITY_STOP');
    assert.equal(result.execution.connectivity.consecutive_failures,4);assert.equal(result.execution.connectivity.cell_ids.length,2);assert.equal(result.execution.incomplete_queries.length,2);
    assert.deepEqual(result.snapshot.responses,previous.responses);assert.deepEqual(result.snapshot.attempts.slice(0,26),previous.attempts);
    const resumed=await run({previous:result.snapshot,fetchFn:()=>assert.fail('Open circuit must not call provider')});
    assert.equal(resumed.execution.api_requests_this_execution,0);assert.equal(resumed.execution.stop_reason,'AMAP_CONNECTIVITY_STOP');assert.deepEqual(resumed.snapshot.attempts,result.snapshot.attempts);
  }
});
test('successful response resets outage streak; a partly used retry allowance never resets on resume',async()=>{
  const previous=await failedCheckpoint();let calls=0;
  const result=await run({previous,fetchFn:async()=>{calls++;if(calls===2||calls===3)throw Error('isolated second failure');return Response.json({status:'1',pois:[]});}});
  assert.equal(calls,22);assert.equal(result.execution.stop_reason,'REQUEST_BUDGET');assert.equal(result.execution.connectivity.open,false);assert.equal(result.execution.incomplete_queries.length,2);
  const partial=await failedCheckpoint(1);let retried=0;
  const recovered=await run({previous:partial,fetchFn:async()=>{if(++retried===1)throw Error('second and final attempt');return Response.json({status:'1',pois:[]});}});
  assert.equal(retried,23);assert.equal(recovered.snapshot.attempts.filter(a=>a.query_id===partial.plan.queries[24].id).length,2);assert.equal(recovered.execution.api_requests_total,48);
});
test('non-retryable provider failure remains sticky after skipping an exhausted query',async()=>{
  const previous=await failedCheckpoint();let calls=0;
  const stopped=await run({previous,fetchFn:async()=>{calls++;return new Response('',{status:429});}});
  assert.equal(calls,1);assert.equal(stopped.execution.stop_reason,'AMAP_RATE_LIMIT');
  const resumed=await run({previous:stopped.snapshot,fetchFn:()=>assert.fail('Do not skip a fatal quota failure')});
  assert.equal(resumed.execution.api_requests_this_execution,0);assert.equal(resumed.execution.stop_reason,'PROVIDER_STOP');
});
test('Actions resume finds only the prior Pilot 3 checkpoint and fails closed on missing history',async()=>{
  const context={GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'workflow_dispatch',GITHUB_REPOSITORY:'FelixVVu/jinke',GITHUB_REF:'refs/heads/review/company-access-scaffold',GITHUB_RUN_ATTEMPT:'1',GITHUB_RUN_ID:'30',GITHUB_RUN_NUMBER:'3'};
  const old={id:20,run_number:2,name:'Company Access AMap Pilot 3 (manual review only)',status:'completed'},artifact={id:100,name:'company-access-amap-pilot-3-20',expired:false};
  const lookup=artifacts=>async url=>url.includes('/artifacts?')?{artifacts}:{workflow_runs:[{...old,id:30,run_number:3},old]};
  assert.deepEqual(await previousPilotArtifact(context,lookup([artifact])),artifact);
  await assert.rejects(previousPilotArtifact(context,lookup([])),/checkpoint missing/);
  await assert.rejects(previousPilotArtifact(context,lookup([{...artifact,expired:true}])),/checkpoint missing/);
  assert.equal(await previousPilotArtifact(context,async()=>({workflow_runs:[{...old,name:'Pilot 2'}]})),null);
  await assert.rejects(previousPilotArtifact(context,async()=>({workflow_runs:[{...old,status:'in_progress'}]})),/not complete/);
  await assert.rejects(previousPilotArtifact(context,async()=>{throw Error('history unavailable');}),/history unavailable/);
  await assert.rejects(previousPilotArtifact({...context,GITHUB_REF:'refs/heads/main'},()=>assert.fail('No lookup on main')));
});
test('Pilot 3 exact intersecting cells, sparse-first spread, fixed policy and reproducible geometry',()=>{
  const p=planQueries(areas,'amap-pilot-3');assert.deepEqual(p,planQueries(structuredClone(areas),'amap-pilot-3'));
  assert.equal(p.cells.length,83);assert.equal(p.cells.filter(c=>c.prior_poi_observations===0).length,54);
  assert.ok(p.cells.slice(0,48).every(c=>!c.prior_poi_observations));
  assert.equal(p.policy.max_requests,48);assert.equal(p.policy.max_requests_per_execution,24);assert.equal(p.policy.max_candidates,300);
  assert.ok(p.cells.every(c=>c.geometry.coordinates.length&&c.reach_area_fraction>0));
  assert.ok(p.queries.slice(0,83).every(q=>q.page===1));assert.equal(new Set(p.queries.map(q=>q.id)).size,p.queries.length);
});
test('two manual chunks share lifetime quota and cached requests; exhausted resume makes zero calls',async()=>{
  const first=await run({fetchFn:mock([])});assert.equal(first.execution.api_requests_this_execution,24);assert.equal(first.execution.stop_reason,'EXECUTION_BUDGET');
  const second=await run({previous:first.snapshot,fetchFn:mock([])});assert.equal(second.execution.api_requests_this_execution,24);assert.equal(second.execution.api_requests_total,48);assert.equal(second.execution.cached_requests_this_execution,24);
  const third=await run({previous:second.snapshot,fetchFn:()=>assert.fail('Exhausted')});assert.equal(third.execution.api_requests_this_execution,0);assert.equal(third.execution.stop_reason,'REQUEST_BUDGET');
  assert.equal(coverageReport(areas,second.snapshot).summary.pilot3_cells_remaining,35);
  const bad=structuredClone(second.snapshot);bad.plan.policy.max_requests=96;assert.throws(()=>validateSnapshot(bad,areas));
});
test('request reservations survive interruption and are counted without blind re-request',async()=>{
  let saved;await assert.rejects(run({fetchFn:()=>assert.fail('Checkpoint fails before request'),checkpoint:async s=>{saved=s;throw Error('synthetic crash');}}));
  assert.equal(saved.attempts[0].outcome,'uncertain');
  const result=await run({previous:saved,fetchFn:mock([])});assert.equal(result.execution.api_requests_total,25);assert.equal(result.snapshot.attempts.filter(a=>a.query_id===saved.attempts[0].query_id).length,1);
});
test('acquisition → console bulk decisions → canonical import/dedupe keeps prior decisions locked',async()=>{
  const baselineRun=await acquire({env,areas,collectedAt:date,sleep:async()=>{},fetchFn:mock([poi('SYNTHETIC-OLD'),poi('SYNTHETIC-REJECT','Rejected old',121.599)])});
  const rows=reviewRows(baselineRun.candidates);rows.forEach(r=>r.review_status=r.amap_poi_id==='SYNTHETIC-OLD'?'accept':'reject');
  const baseline=approvedFromReview({snapshot:baselineRun.snapshot,areas,csv:toCSV(rows),reviewer:'Synthetic reviewer',reviewedAt:date});
  const history=makeReviewBundle([baselineRun.snapshot],areas,baseline.decisions,baseline.artifacts.offices.features.map(f=>f.properties));
  const incoming=await run({fetchFn:mock([poi('SYNTHETIC-OLD'),poi('SYNTHETIC-REJECT','Rejected old',121.599),poi('SYNTHETIC-NEW-A','New company',121.600),poi('SYNTHETIC-NEW-B','New company',121.60001),poi('SYNTHETIC-HOLD','Hold',121.601)])});
  const bundle=attachReviewHistory(makeReviewBundle([incoming.snapshot],areas),history),before=structuredClone(baseline);
  let session=createSession(bundle);session.reviewer='Synthetic human';
  const current=bundle.batches[0].rows;
  assert.equal(current.filter(i=>i.locked).length,2);assert.ok(current.filter(i=>!i.locked).every(i=>i.row.review_status==='pending'));
  assert.throws(()=>decide(bundle,session,[current.find(i=>i.locked).key],'accept',''),/locked/);
  session=decide(bundle,session,current.filter(i=>i.row.amap_poi_id.startsWith('SYNTHETIC-NEW')).map(i=>i.key),'accept','Reviewed mapped office',date);
  session=decide(bundle,session,[current.find(i=>i.row.amap_poi_id==='SYNTHETIC-HOLD').key],'needs_review','Unclear',date);
  const merged=importPilot3({snapshot:incoming.snapshot,areas,baseline,historyBundle:history,session,reviewedAt:date});
  assert.equal(merged.artifacts.offices.features.length,2);assert.equal(merged.report.human_new_accepts,2);assert.equal(merged.report.new_canonical_dispositions.duplicates,1);
  assert.deepEqual(baseline,before);assert.deepEqual(merged.decisions.filter(d=>baseline.decisions.some(p=>p.amap_poi_id===d.amap_poi_id)),baseline.decisions);
  const tampered=structuredClone(session);tampered.decisions[current.find(i=>i.locked).key].notes='overwrite';assert.throws(()=>importPilot3({snapshot:incoming.snapshot,areas,baseline,historyBundle:history,session:tampered,reviewedAt:date}),/locked/);
});
test('Pilot 3 Actions artifact contains pending console bundle and key-free coverage',async()=>{
  const root='offline-output/company-access/',folders=['pilot-3-checkpoint','pilot-3','pilot-3-artifact'];
  for(const p of folders)await assert.rejects(fs.stat(root+p),{code:'ENOENT'});
  try{const result=await executePilot({key:env.JINKE_AMAP_KEY,context:{GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'workflow_dispatch',GITHUB_REPOSITORY:'FelixVVu/jinke',GITHUB_REF:'refs/heads/review/company-access-scaffold',GITHUB_RUN_ATTEMPT:'1'},pilotVersion:'amap-pilot-3',collectedAt:date,dependencies:{sleep:async()=>{},fetchFn:mock([poi('SYNTHETIC-A')])}});
    const bytes=await fs.readFile(result.artifact+'/review/review-bundle.json');assertKeyFree(bytes,env.JINKE_AMAP_KEY);const bundle=JSON.parse(bytes);assert.equal(bundle.batches[0].rows[0].row.review_status,'pending');assert.equal(bundle.coverage.summary.pilot3_cells_sampled,24);
  }finally{for(const p of folders)await fs.rm(root+p,{recursive:true,force:true});}
});
