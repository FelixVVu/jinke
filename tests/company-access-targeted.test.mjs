import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {sha256,stable} from '../scripts/company-access/common.mjs';
import {targetedPlan,baseline,TARGETED_POLICY,CAMPAIGN,WORKFLOW_NAME} from '../scripts/company-access/discovery/targeted-plan.mjs';
import {acquireTargeted,validateTargeted,prepareTargeted,targetedBundle,targetedReport} from '../scripts/company-access/discovery/targeted.mjs';
import {buildBaseline,providerDigest,assertionDigest,officeDigest} from '../scripts/company-access/discovery/targeted-baseline.mjs';
import {executeTargeted,SAFE_FILES} from '../scripts/company-access/discovery/actions-targeted.mjs';
import {previousTargetedArtifact} from '../scripts/company-access/discovery/resume-targeted.mjs';
import {assertKeyFree} from '../scripts/company-access/amap/actions-pilot.mjs';
import {wgs84ToGcj02} from '../web/src/location-search.js';
import {prepareReachAreas} from '../web/src/company-access/model.js';
import {createSession,decide,validateSession} from '../web/src/company-access/review-state.js';
import {appendPending} from '../web/src/company-access/review-append.js';
import {TRIAGE_VERSION,secondPass,triageItems,confirmGroup} from '../web/src/company-access/review-triage.js';
import {scopeItems,resumeAppended} from '../web/src/company-access/review-scope.js';
import {analyzeTargeted,continuationPlan} from '../scripts/company-access/discovery/targeted-review.mjs';
const areas=JSON.parse(await fs.readFile(new URL('../web/public/data/reach-areas.geojson',import.meta.url)));
const guard=baseline(),date='2026-10-23T00:00:00Z',key='TEST_ONLY_TARGETED_KEY_8d739a';
const context={GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'workflow_dispatch',GITHUB_REPOSITORY:'FelixVVu/jinke',GITHUB_REF:'refs/heads/review/company-access-scaffold',GITHUB_RUN_ATTEMPT:'1',GITHUB_RUN_ID:'30',GITHUB_RUN_NUMBER:'3'};
const poi=(id='SYNTHETIC-A',extra={})=>({id,name:'SYNTHETIC 示例科技有限公司',address:'测试路100号科技大厦12楼',adname:'浦东新区',adcode:'310115',type:'公司企业;公司',typecode:'170200',location:wgs84ToGcj02(121.597836,31.2064028).join(','),...extra});
const response=pois=>Response.json({status:'1',count:'1',pois});
const start=(g=guard)=>({version:TARGETED_POLICY.version,collected_at:date,plan:targetedPlan(areas,g),responses:[],attempts:[]});
const cache=(s,q,pois)=>{const payload={status:'1',pois};s.responses.push({query_id:q.id,payload,payload_sha256:sha256(stable(payload))});s.attempts.push({query_id:q.id,outcome:'success'});return s;};
const run=options=>acquireTargeted({env:{JINKE_AMAP_KEY:key},areas,collectedAt:date,sleep:async()=>{},fetchFn:async()=>response([]),...options});
test('screenshot plan: 16 clipped cells, interleaved regions, three source-backed names and immutable bounded policy',()=>{
  const p=targetedPlan(areas);assert.equal(p.cells.length,16);assert.equal(p.streams.length,19);assert.equal(p.queries.length,57);assert.equal(stable(p),stable(targetedPlan(areas)));
  assert.deepEqual(p.cells.slice(0,4).map(c=>c.region_id),['northwest','northcentral','east','south']);
  assert.deepEqual(p.queries.slice(0,3).map(q=>q.parameters.keywords),['中芯国际','华虹','环旭电子']);
  assert.equal(p.policy.max_requests,48);assert.equal(p.policy.max_requests_per_execution,24);assert.equal(p.policy.pacing_ms,1500);assert.equal(p.policy.retry_ms,3000);
  assert(p.cells.every(c=>c.parameters.types==='170000|141100'));assert(p.queries.filter(q=>q.operation==='text').every(q=>!q.parameters.types&&q.parameters.city_limit==='true'));
  const reach=prepareReachAreas(areas);for(const c of p.cells)for(const point of c.geometry.coordinates.flat(2))assert(reach.contains(point,30));
});
test('hashed manifest pins 145 approved, 442 historical, 291 recovered without company rows',()=>{
  assert.deepEqual(guard.counts,{approved:145,historical:442,pending_recovery:291});assert.equal(Object.keys(guard.entries).length,733);
  assert(Object.keys(guard.entries).every(k=>/^[a-f0-9]{64}$/.test(k)));assert.doesNotMatch(stable(guard),/company_name|longitude|review_notes|JINKE_AMAP_KEY/);
});
test('pagination uses full pages not count; correct text/polygon operations, no cache reacquisition',async()=>{
  const full=Array.from({length:25},(_,i)=>poi(`SYNTHETIC-${i}`)),urls=[],pauses=[];
  const a=await run({sleep:async ms=>pauses.push(ms),fetchFn:async url=>{urls.push(new URL(url));return response(new URL(url).searchParams.get('page_num')==='1'?full:[]);}});
  assert.equal(a.snapshot.attempts.length,24);assert.equal(a.execution.stop_reason,'EXECUTION_BUDGET');assert.equal(urls.filter(u=>u.pathname.endsWith('/text')).length,6);assert(pauses.every(ms=>ms===1500));
  const completed=new Set(a.snapshot.responses.map(r=>r.query_id));let calls=0;
  const b=await run({previous:a.snapshot,fetchFn:async()=>{calls++;return response([]);}});
  assert.equal(calls,14);assert.equal(b.execution.stop_reason,'PLAN_COMPLETE');assert.equal(b.snapshot.attempts.length,38);assert(b.snapshot.attempts.slice(24).every(a=>!completed.has(a.query_id)));
  assert.equal((await run({previous:b.snapshot,fetchFn:async()=>assert.fail('No reacquisition')})).execution.api_requests_this_execution,0);
});
test('lifetime 48 includes both manual executions and immutable budget after resume',async()=>{
  const full=Array.from({length:25},(_,i)=>poi(`SYNTHETIC-${i}`));const a=await run({fetchFn:async()=>response(full)}),b=await run({previous:a.snapshot,fetchFn:async()=>response(full)});
  assert.equal(a.snapshot.attempts.length,24);assert.equal(b.snapshot.attempts.length,48);assert.equal(b.execution.stop_reason,'REQUEST_BUDGET');
  const c=await run({previous:b.snapshot,fetchFn:async()=>assert.fail('Budget exhausted')});assert.equal(c.snapshot.attempts.length,48);assert.equal(c.execution.api_requests_this_execution,0);
  const report=targetedReport(c.snapshot,c);assert(report.remaining_gaps.length>0);assert(report.streams.some(s=>s.status==='saturated_incomplete'));assert(report.streams.every(s=>!s.inventory_complete&&!s.verified_empty));
});
test('isolated exhausted query is skipped; cross-cell outage and fatal errors stop safely',async()=>{
  let calls=0;const a=await run({fetchFn:async()=>{calls++;if(calls<=2)throw Error('network');return response([]);}});
  assert.equal(a.snapshot.attempts.length,20);assert.equal(a.execution.stop_reason,'PLAN_COMPLETE_WITH_GAPS');assert.equal(a.execution.incomplete_queries[0].reason,'RETRY_EXHAUSTED');
  assert.equal((await run({previous:a.snapshot,fetchFn:async()=>assert.fail('Exhausted query not retried')})).execution.api_requests_this_execution,0);
  const outage=await run({fetchFn:async()=>{throw Error('network');}});assert.equal(outage.snapshot.attempts.length,4);assert.equal(outage.execution.stop_reason,'AMAP_CONNECTIVITY_STOP');
  assert.equal((await run({previous:outage.snapshot,fetchFn:async()=>assert.fail('Circuit must remain open')})).execution.api_requests_this_execution,0);
  const fatal=await run({fetchFn:async()=>Response.json({status:'0',infocode:'10001'})});assert.equal(fatal.snapshot.attempts.length,1);assert.equal((await run({previous:fatal.snapshot})).execution.api_requests_this_execution,0);
});
test('uncertain request is reserved before I/O and never receives a free retry',async()=>{
  let saved;await assert.rejects(run({checkpoint:async s=>{saved=s;if(s.attempts.length)throw Error('interrupted');},fetchFn:async()=>assert.fail('Reservation before network')}),/interrupted/);
  assert.equal(saved.attempts[0].outcome,'uncertain');const b=await run({previous:saved});assert.equal(b.snapshot.attempts.length,19);assert.equal(b.execution.incomplete_queries[0].reason,'UNCERTAIN_REQUEST');
});
test('wrong campaign/geometry/baseline, forged cache, page lineage and repeated success fail closed',()=>{
  const valid=cache(start(),targetedPlan(areas).queries[0],[]);validateTargeted(valid,areas);
  for(const mutate of [s=>s.version='amap-pilot-3',s=>s.plan.policy.max_requests=49,s=>s.plan.baseline_sha256='wrong',s=>s.responses[0].payload.pois.push(poi()),s=>s.attempts.push({...s.attempts[0]})]){const s=structuredClone(valid);mutate(s);assert.throws(()=>validateTargeted(s,areas));}
  const s=start(),q=s.plan.queries.find(q=>q.page===2);cache(s,q,[]);assert.throws(()=>validateTargeted(s,areas),/INVALID_PAGINATION_LINEAGE/);
});
test('broader corporate/R&D and source-backed names retained; exact outside reach and invalid data excluded',()=>{
  const s=start();cache(s,s.plan.queries[0],[poi('SYNTHETIC-SMIC',{name:'中芯国际(张江)',typecode:'999999'}),poi('SYNTHETIC-OUT',{location:'121.48,31.23'}),poi('SYNTHETIC-BAD',{location:'unknown'})]);
  cache(s,s.plan.queries[3],[poi('SYNTHETIC-FACTORY',{name:'示例制造有限公司',typecode:'170100'}),poi('SYNTHETIC-RD',{typecode:'141100'}),poi('SYNTHETIC-MULTI',{typecode:'060000|170200'}),poi('SYNTHETIC-STORE',{typecode:'060000'})]);
  const r=prepareTargeted(s,areas);assert.equal(r.candidates.length,4);assert(r.exclusions.some(e=>e.reason==='OUTSIDE_30_MINUTES'));assert(r.exclusions.some(e=>e.reason==='INVALID_COORDINATES'));assert(r.exclusions.some(e=>e.reason==='OUT_OF_PROVIDER_SCOPE'));
  const b=targetedBundle(s,r);assert(b.batches[0].rows.every(i=>i.row.review_status==='pending'&&!i.locked));assert.equal(secondPass(b.batches[0].rows.find(i=>i.row.amap_poi_id==='SYNTHETIC-FACTORY').row).group,'exception');
});
test('known IDs/changed assertions stay audit-only; new ID exact office match flagged but not merged',()=>{
  const known=poi('SYNTHETIC-KNOWN'),changed=poi('SYNTHETIC-CHANGED');const g={...guard,entries:{[providerDigest(known.id)]:{origin:'pending_recovery',assertions:[assertionDigest(known)]},[providerDigest(changed.id)]:{origin:'historical',assertions:['different']}},approved_office_keys:[officeDigest(known.name,known.address)]};
  const s=start(g);cache(s,s.plan.queries[3],[known,changed,poi('SYNTHETIC-NEW')]);const r=prepareTargeted(s,areas,g);
  assert.equal(r.candidates.length,1);assert.equal(r.counts.known_ids_preserved,1);assert.equal(r.counts.known_id_conflicts,1);assert(r.candidates[0].possible_duplicate);
});
test('provider conflicts and candidate cap reconcile without inventing identities',()=>{
  const s=start();for(let i=0;i<13;i++)cache(s,s.plan.queries[i],Array.from({length:25},(_,j)=>poi(`SYNTHETIC-${i}-${j}`)));
  const r=prepareTargeted(s,areas);assert.equal(r.candidates.length,300);assert.equal(r.exclusions.filter(e=>e.reason==='PILOT_CANDIDATE_CAP').length,25);
  cache(s,s.plan.queries[13],[poi('SYNTHETIC-0-0',{address:'conflicting'})]);const c=prepareTargeted(s,areas);assert.equal(c.counts.provider_id_conflicts,1);
  assert.equal(c.candidates.length+c.exclusions.length,c.counts.unique_amap_ids);
});
test('source-name hits are unbound leads, never a verified recall/occupancy claim',()=>{
  const s=start();cache(s,s.plan.queries[0],[poi('SYNTHETIC-SMIC',{name:'中芯国际公司'})]);const r=targetedReport(s,prepareTargeted(s,areas));
  assert.equal(r.discovery_name_hit_rate.numerator,1);assert.equal(r.verified_representative_recall,null);assert.equal(r.benchmark[0].identity_confirmed,false);assert.equal(r.coverage.features.filter(f=>f.properties.status==='unsampled').length,16);
});
test('resume ignores Pilot 3 and selects independent checkpoint; expired/missing/started failures block reset',async()=>{
  const old={id:20,name:WORKFLOW_NAME,run_number:2,status:'completed'},a={id:100,name:`company-access-${CAMPAIGN}-checkpoint-20`,expired:false};
  const lookup=artifacts=>async url=>url.includes('/artifacts?')?{artifacts}:url.includes('/jobs?')?{jobs:[{steps:[{name:'Acquire targeted 30m and prepare pending review bundle',conclusion:'failure'}]}]}:{workflow_runs:[old]};
  assert.equal((await previousTargetedArtifact(context,lookup([a]))).id,100);
  await assert.rejects(previousTargetedArtifact(context,lookup([{...a,expired:true}])),/refuse a fresh quota/);
  assert.equal(await previousTargetedArtifact(context,async()=>({workflow_runs:[{...old,name:'Company Access AMap Pilot 3 (manual review only)'}]})),null);
  assert.equal(await previousTargetedArtifact(context,async url=>url.includes('/artifacts?')?{artifacts:[]}:url.includes('/jobs?')?{jobs:[{steps:[{name:'Acquire targeted 30m and prepare pending review bundle',conclusion:'skipped'}]}]}:{workflow_runs:[old]}),null);
});
test('Actions mock end-to-end uses allowlisted safe artifacts, pending bundle and pre-I/O checkpoint',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'jinke-targeted-test-')),signals=[];
  const fresh=path.join(root,'fresh-checkout','offline-output');
  try{const result=await executeTargeted({key,context,root:fresh,collectedAt:date,signal:async s=>signals.push(s),dependencies:{sleep:async()=>{},fetchFn:async()=>response([poi()])}});
    assert.deepEqual(signals,['checkpoint_ready','artifact_ready']);assert.equal(result.report.api_requests_total,19);assert.equal(result.report.candidate_review_count,1);assert.equal(result.report.accepted_count,0);
    for(const file of SAFE_FILES)assertKeyFree(await fs.readFile(path.join(result.artifact,file)),key);
    const snapshot=JSON.parse(await fs.readFile(path.join(fresh,`${CAMPAIGN}-checkpoint/provider-cache/snapshot.json`)));validateTargeted(snapshot,areas);
    const bundle=JSON.parse(await fs.readFile(path.join(result.artifact,'review/review-bundle.json')));assert.equal(createSession(bundle).decisions[bundle.batches[0].rows[0].key].status,'pending');
  }finally{await fs.rm(root,{recursive:true,force:true});}
});
test('provider-echoed encoded secret never enters checkpoint or safe artifacts',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'jinke-targeted-secret-test-'));
  try{const result=await executeTargeted({key,context,root,collectedAt:date,dependencies:{sleep:async()=>{},fetchFn:async()=>response([poi('SYNTHETIC-SECRET',{name:Buffer.from(key).toString('base64')})])}});
    assert.equal(result.report.api_requests_total,1);assert.equal(result.report.candidate_review_count,0);for(const file of SAFE_FILES)assertKeyFree(await fs.readFile(path.join(result.artifact,file)),key);
  }finally{await fs.rm(root,{recursive:true,force:true});}
});
test('append preserves recovery pending, human notes/history, locked history and checked second-pass metadata',()=>{
  const make=(id)=>{const s=start();cache(s,s.plan.queries[0],[poi(id)]);return targetedBundle(s,prepareTargeted(s,areas));};
  const first=make('SYNTHETIC-A'),incoming=make('SYNTHETIC-B');incoming.batches[0].id='next';incoming.batches[0].rows[0].key='next:SYNTHETIC-B';incoming.bundle_id='next';
  const history={schema_version:1,bundle_id:'historical',batches:[]};let session=createSession(first);session.reviewer='TEST';session=decide(first,session,[first.batches[0].rows[0].key],'needs_review','keep note',date);
  const pack={schema_version:1,version:TRIAGE_VERSION,bundle_id:first.bundle_id,evidence:[],seeds:first.batches[0].rows.map(i=>({poi_id:i.row.amap_poi_id,company_name:i.row.company_name,address:i.row.address,decision:'pending',flags:[]}))};
  const combined=appendPending(first,incoming,history,session,pack);assert.equal(combined.bundle.batches.flatMap(b=>b.rows).length,2);assert.equal(combined.session.decisions['next:SYNTHETIC-B'].status,'pending');assert.deepEqual(combined.session.decisions[first.batches[0].rows[0].key],session.decisions[first.batches[0].rows[0].key]);validateSession(combined.bundle,combined.session);
  incoming.batches[0].rows[0].row.review_status='accept';assert.throws(()=>appendPending(first,incoming,history,session),/pending candidates only/);
});
test('baseline builder is deterministic and refuses missing source evidence or overlapping locked identities',()=>{
  const p=poi(),s=start();cache(s,s.plan.queries[0],[p]);const pending=targetedBundle(s,prepareTargeted(s,areas)),input={decisions:[],offices:{features:[]},pending,snapshots:[s]};
  assert.equal(stable(buildBaseline(input)),stable(buildBaseline(input)));assert.throws(()=>buildBaseline({...input,snapshots:[]}),/Missing baseline source/);
  assert.throws(()=>buildBaseline({...input,decisions:[{amap_poi_id:p.id}]}),/Overlapping baseline/);
});
test('targeted precision excludes facilities even with a company brand or misleading company category',()=>{
  const row={company_name:'合成公司',address:'合成路100号大厦5楼',amap_typecode:'170200',longitude_wgs84:121.6,latitude_wgs84:31.2},context={seed_flags:['TARGETED_PRECISION_V1']};
  for(const name of ['合成公司停车场','合成公司食堂','民防工程(合成公司)','合成冒菜公司','合成公司项目部','合成公司充电站'])assert.equal(secondPass({...row,company_name:name},context).group,'exclude',name);
  assert.equal(secondPass({...row,company_name:'民防工程(合成公司)'},{...context,same_name_multiple:true}).group,'exclude');
  assert.equal(secondPass({...row,company_name:'合成制造有限公司',amap_typecode:'170100'},context).group,'exception');
  assert.equal(secondPass({...row,company_name:'合成科技有限公司',amap_typecode:'060000|170200'},context).reason,'MIXED_PROVIDER_CATEGORY');
  assert.equal(secondPass({...row,company_name:'合成公司1栋',amap_typecode:'120100'},context).reason,'BUILDING_NOT_OFFICE');
});
test('targeted evidence never upgrades confidence or merges a related building/office',()=>{
  const row={company_name:'合成研发科技有限公司',address:'测试路123号',amap_typecode:'170200',longitude_wgs84:121.6,latitude_wgs84:31.2};
  const context={seed_flags:['TARGETED_PRECISION_V1'],evidence:{assessment:'office_address_match'}};
  assert.equal(secondPass(row,context).group,'trusted');assert.match(secondPass(row,context).confidence_notice,/仍为 reviewed mapped office/);
  assert.equal(secondPass(row,{...context,evidence:{assessment:'mixed_site_office_match'}}).group,'exception');
  assert.equal(secondPass(row,{...context,seed_flags:['TARGETED_PRECISION_V1','POSSIBLE_SHARED_OFFICE']}).reason,'RELATION_UNRESOLVED');
  assert.equal(secondPass({...row,address:'测试路123号1-2层'}, {seed_flags:['TARGETED_PRECISION_V1']}).reason,'GROUND_OR_BASEMENT');
});
test('offline targeted analysis covers every candidate reproducibly, preserves snapshot and pending decisions',()=>{
  const s=start();cache(s,s.plan.queries[0],[poi('SYNTHETIC-SMIC',{name:'中芯国际合成测试食堂'})]);cache(s,s.plan.queries[3],[poi('SYNTHETIC-OFFICE')]);
  const before=stable(s),a=analyzeTargeted({snapshot:s,areas}),b=analyzeTargeted({snapshot:s,areas});
  assert.equal(stable(a),stable(b));assert.equal(stable(s),before);assert.equal(a.report.triage.analyzed,2);assert.equal(a.report.triage.automatic_accepts,0);
  assert.equal(a.report.triage.groups.exclude,1);assert.equal(a.report.triage.groups.trusted,1);
  assert(Object.values(createSession(a.bundle).decisions).every(d=>d.status==='pending'&&d.history.length===0));
  assert.throws(()=>analyzeTargeted({snapshot:s,areas,relations:[{poi_ids:['not-present','other'],reason:'test'}]}));
});
test('continuation accounts for full lifetime ledger, skips completed queries and holds original cap',()=>{
  const s=start();cache(s,s.plan.queries[0],Array.from({length:25},(_,i)=>poi(`SYNTHETIC-${i}`)));cache(s,s.plan.queries[3],[]);
  s.attempts.push({query_id:s.plan.queries[4].id,outcome:'failure',code:'AMAP_NETWORK',retryable:true});
  const prepared=prepareTargeted(s,areas),plan=continuationPlan(s,prepared,triageItems(targetedBundle(s,prepared).batches[0].rows));
  assert.equal(plan.attempts_spent,3);assert.equal(plan.attempts_remaining,45);assert.equal(plan.failed_attempts_preserved.length,1);
  assert.equal(plan.next_pages.length,1);assert.equal(plan.next_pages[0].next_page,2);assert.equal(plan.execution_enabled,false);assert.equal(plan.original_candidate_cap,300);
  assert(plan.completed_streams_not_requeried.includes(s.plan.queries[3].cell_id));assert(!plan.next_pages.some(q=>s.responses.some(r=>r.query_id===q.query_id)));
  assert.match(plan.capacity_gate,/never delete candidates/);
});
test('batch confirmation only changes scoped pending rows, preserving recovery and locked history',()=>{
  const s=start();cache(s,s.plan.queries[3],[poi()]);const first=targetedBundle(s,prepareTargeted(s,areas)),other=structuredClone(first.batches[0]);other.id='new';other.rows[0].key='new:SYNTHETIC-NEW';other.rows[0].row.amap_poi_id='SYNTHETIC-NEW';other.rows[0].row.company_name='SYNTHETIC 新科技有限公司';
  const b={...first,batches:[...first.batches,other]},session=createSession(b);session.reviewer='Synthetic reviewer';
  const items=triageItems(b.batches.flatMap(b=>b.rows.map(i=>({...i,batch:b.id}))));
  const next=confirmGroup(b,session,scopeItems(items,'new'),'trusted',{confirmed:true,at:date});
  assert.equal(next.decisions[other.rows[0].key].status,'accept');assert.deepEqual(next.decisions[first.batches[0].rows[0].key],session.decisions[first.batches[0].rows[0].key]);
  assert.equal(scopeItems(items,'all').length,2);
});
test('reload/reappend preserves saved composite decisions instead of replacing with pending migration',()=>{
  const s=start();cache(s,s.plan.queries[3],[poi()]);const b=targetedBundle(s,prepareTargeted(s,areas)),migrated=createSession(b);migrated.reviewer='Synthetic';
  const saved=decide(b,migrated,[b.batches[0].rows[0].key],'reject','Do not overwrite',date);
  assert.deepEqual(resumeAppended(b,migrated,JSON.stringify(saved)),saved);assert.deepEqual(resumeAppended(b,migrated,null),migrated);
  assert.throws(()=>resumeAppended(b,migrated,JSON.stringify({...saved,bundle_id:'wrong'})));
});
