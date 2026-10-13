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
