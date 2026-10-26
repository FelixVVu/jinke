import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {sha256,stable} from '../scripts/company-access/common.mjs';
import {targetedPlan,baseline,TARGETED_POLICY} from '../scripts/company-access/discovery/targeted-plan.mjs';
import {CONTINUATION,CONTINUATION_WORKFLOW,CONTINUATION_STEP,startContinuation,validateContinuation,prepareContinuation,acquireContinuation,continuationGuard} from '../scripts/company-access/discovery/continuation.mjs';
import {executeContinuation,CONTINUATION_FILES} from '../scripts/company-access/discovery/actions-continuation.mjs';
import {previousTargetedArtifact} from '../scripts/company-access/discovery/resume-targeted.mjs';
import {sourceEvidence,addressLeadMatches} from '../scripts/company-access/discovery/continuation-sources.mjs';
import {providerDigest,assertionDigest} from '../scripts/company-access/discovery/targeted-baseline.mjs';
import {wgs84ToGcj02} from '../web/src/location-search.js';
import {createSession,decide} from '../web/src/company-access/review-state.js';
import {appendDiscovery} from '../web/src/company-access/review-append.js';
import {assertKeyFree} from '../scripts/company-access/amap/actions-pilot.mjs';
const areas=JSON.parse(await fs.readFile('web/public/data/reach-areas.geojson')),originalGuard=baseline(),date='2026-10-26T00:00:00Z';
const key='SYNTHETIC_CONTINUATION_CREDENTIAL';
const context={GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'workflow_dispatch',GITHUB_REPOSITORY:'FelixVVu/jinke',GITHUB_REF:'refs/heads/review/company-access-scaffold',GITHUB_RUN_ATTEMPT:'1',GITHUB_RUN_ID:'100',GITHUB_RUN_NUMBER:'20'};
const poi=(id,extra={})=>({id,name:`合成 ${id} 科技有限公司`,address:'合成路100号办公大厦12楼',type:'公司企业;公司',typecode:'170200',adcode:'310115',adname:'浦东新区',location:wgs84ToGcj02(121.597836,31.2064028).join(','),...extra});
const cache=(s,q,pois)=>{const payload={status:'1',pois};s.responses.push({query_id:q.id,payload,payload_sha256:sha256(stable(payload))});s.attempts.push({query_id:q.id,outcome:'success'});};
function setup(){
  const parent={version:TARGETED_POLICY.version,collected_at:date,plan:targetedPlan(areas),responses:[],attempts:[]};
  for(const q of parent.plan.queries.filter(q=>q.page===1))cache(parent,q,Array.from({length:25},(_,i)=>poi(`SYNTHETIC-${i}`)));
  const guard={...originalGuard,entries:{},counts:{approved:183,historical:480,pending_recovery:553},parent_snapshot_sha256:sha256(stable(parent)),active_pending:4};
  return {parent,guard};
}
const run=({parent,guard,...opts})=>acquireContinuation({parent,guard,areas,originalGuard,env:{JINKE_AMAP_KEY:key},sleep:async()=>{},fetchFn:async()=>Response.json({status:'1',pois:[]}),...opts});
test('fixed continuation guard preserves 183 offices, 480 history and 553 pending as digests only',()=>{
  const g=continuationGuard();assert.deepEqual(g.counts,{approved:183,historical:480,pending_recovery:553});assert.equal(Object.keys(g.entries).length,1033);assert.equal(g.active_pending,4);
  assert.doesNotMatch(stable(g),/company_name|longitude|JINKE_AMAP_KEY/);
});
test('19 parent + 29 remaining lifetime attempts, separate checkpoint, fair pagination and no replay',async()=>{
  const f=setup(),before=stable(f.parent),seen=[],pauses=[];
  const fetchFn=async url=>{const u=new URL(url);seen.push(u);return Response.json({status:'1',pois:Array.from({length:25},(_,i)=>poi(`SYNTHETIC-${i}`))});};
  const a=await run({...f,fetchFn,sleep:async ms=>pauses.push(ms)});
  assert.equal(a.snapshot.attempts.length,31);assert.equal(a.execution.api_requests_this_execution,12);assert.equal(a.execution.stop_reason,'EXECUTION_BUDGET');assert(pauses.every(p=>p===1500));
  assert(seen.slice(0,6).every(u=>u.pathname.endsWith('/text')&&u.searchParams.get('page_num')==='1'));
  assert(seen.slice(6).every(u=>u.pathname.endsWith('/polygon')&&u.searchParams.get('page_num')==='2'));
  const b=await run({...f,previous:a.snapshot,fetchFn}),c=await run({...f,previous:b.snapshot,fetchFn});
  assert.equal(c.snapshot.attempts.length,48);assert.equal(c.execution.stop_reason,'REQUEST_BUDGET');
  assert.equal(new Set(seen.map(String)).size,29);assert.equal(stable(f.parent),before);
  assert.equal(stable(c.snapshot.attempts.slice(0,19)),stable(f.parent.attempts));
  assert.equal(stable(c.snapshot.responses.slice(0,19)),stable(f.parent.responses));
  const d=await run({...f,previous:c.snapshot,fetchFn:()=>assert.fail('No free quota')});assert.equal(d.execution.api_requests_this_execution,0);
});
test('short pages never reacquired; known POIs do not fill queue, changed assertions held',async()=>{
  const f=setup(),known=poi('SYNTHETIC-0');f.guard.entries[providerDigest(known.id)]={origin:'historical',assertions:[assertionDigest(known)]};
  const a=await run(f),b=await run({...f,previous:a.snapshot});
  assert.equal(b.execution.api_requests_this_execution,12);const done=await run({...f,previous:b.snapshot});assert.equal(done.execution.api_requests_this_execution,1);assert.equal(done.execution.stop_reason,'PLAN_COMPLETE');
  assert(!b.candidates.some(c=>c.amap_poi_id===known.id));assert(b.exclusions.some(e=>e.reason==='KNOWN_ID_PRESERVED'));
  const s=structuredClone(a.snapshot);cache(s,s.plan.queries.find(q=>!s.attempts.some(a=>a.query_id===q.id)&&q.page===2),[poi(known.id,{address:'changed'})]);
  assert(prepareContinuation(s,areas,f.guard).exclusions.some(e=>e.reason==='POI_ID_CONFLICT'));
});
test('no empty reset, parent edits, foreign plan, forged cache or page leap',()=>{
  const f=setup(),s=startContinuation(f.parent,areas,f.guard);validateContinuation(s,areas,f.guard);
  for(const change of [x=>x.attempts.shift(),x=>x.parent.attempts.pop(),x=>x.plan.policy.max_requests++,x=>x.responses[0].payload.pois.pop(),x=>x.plan.queries.reverse(),x=>delete x.parent]){const x=structuredClone(s);change(x);assert.throws(()=>validateContinuation(x,areas,f.guard));}
  const x=structuredClone(s);cache(x,x.plan.queries.find(q=>q.page===3),[]);assert.throws(()=>validateContinuation(x,areas,f.guard),/PAGINATION/);
});
test('retry exhaustion skips one stream, retains failures and circuit breaker stops broader outage',async()=>{
  const f=setup();let calls=0;
  const a=await run({...f,fetchFn:async()=>{if(++calls<=2)throw Error('network');return Response.json({status:'1',pois:[]});}});
  assert.equal(a.snapshot.attempts.filter(a=>a.outcome==='failure').length,2);const exhausted=a.snapshot.attempts[19].query_id;
  const b=await run({...f,previous:a.snapshot});assert.equal(b.snapshot.attempts.filter(a=>a.query_id===exhausted).length,2);
  const outage=await run({...f,fetchFn:async()=>{throw Error('network');}});assert.equal(outage.execution.api_requests_this_execution,4);assert.equal(outage.execution.stop_reason,'AMAP_CONNECTIVITY_STOP');
  const blocked=await run({...f,previous:outage.snapshot,fetchFn:()=>assert.fail('Circuit open')});assert.equal(blocked.execution.api_requests_this_execution,0);
});
test('reservation interruption survives child resume and consumes original lifetime budget',async()=>{
  const f=setup();let saved;
  await assert.rejects(run({...f,checkpoint:async s=>{saved=s;throw Error('interrupted');},fetchFn:()=>assert.fail('Reserve first')}));
  assert.equal(saved.attempts.length,20);assert.equal(saved.attempts[19].outcome,'uncertain');
  const b=await run({...f,previous:saved});assert.equal(b.snapshot.attempts.filter(a=>a.query_id===saved.attempts[19].query_id).length,1);
});
test('precision headroom preserves all pending rows and refuses requests at 276 active slots',async()=>{
  const f=setup();f.guard.active_pending=276;
  const a=await run({...f,fetchFn:()=>assert.fail('Active review capacity full')});assert.equal(a.execution.stop_reason,'CANDIDATE_CAP');assert.equal(a.execution.api_requests_this_execution,0);
  const g=setup(),s=startContinuation(g.parent,areas,g.guard),q=s.plan.queries.find(q=>q.cell_id==='name:amd-en'&&q.page===1);
  cache(s,q,[poi('SYNTHETIC-PARK',{name:'AMD停车场'}),poi('SYNTHETIC-MIXED',{name:'中芯国际',address:'张江路18号',typecode:'170100'}),poi('SYNTHETIC-AM',{name:'AMD公司',address:'博云路2号601室'})]);
  const p=prepareContinuation(s,areas,g.guard);assert(p.items.find(i=>i.row.amap_poi_id==='SYNTHETIC-PARK').triage.group==='exclude');assert(p.items.find(i=>i.row.amap_poi_id==='SYNTHETIC-MIXED').triage.group==='exception');
  assert(p.items.find(i=>i.row.amap_poi_id==='SYNTHETIC-AM').triage.group==='trusted');assert(p.bundle.batches[0].rows.every(i=>i.row.review_status==='pending'));
});
test('official address corroboration keeps different USI sites and factories distinct',()=>{
  const row={amap_poi_id:'SYNTHETIC-USI',company_name:'环旭电子',address:'盛夏路169号'};assert.equal(sourceEvidence(row).assessment,'office_address_match');
  assert.equal(sourceEvidence({...row,address:'张东路1558号'}).assessment,'mixed_site_office_match');
  assert.equal(sourceEvidence({...row,address:'盛夏路1690号'}),null);assert.equal(sourceEvidence({...row,company_name:'不相关公司'}),null);
  assert.equal(addressLeadMatches('博云路20号',{addresses:['博云路2号']}),false);
});
test('single-file append carries checked evidence, preserves human history and blocks forged packs',()=>{
  const f=setup(),s=startContinuation(f.parent,areas,f.guard),p=prepareContinuation(s,areas,f.guard);
  const empty={schema_version:1,bundle_id:'empty',batches:[]},pack={...p.pack,bundle_id:'empty',seeds:[],evidence:[]};
  const incoming={...p.bundle,second_pass:p.pack},first=appendDiscovery(empty,incoming,empty,createSession(empty),pack);
  assert.deepEqual(first.pack.seeds,p.pack.seeds);let session=first.session;session.reviewer='Synthetic human';const k=p.items[0].key;session=decide(first.bundle,session,[k],'needs_review','Keep my note',date);
  const next=appendDiscovery(first.bundle,incoming,empty,session,first.pack);assert.deepEqual(next.session.decisions[k],session.decisions[k]);
  const bad=structuredClone(incoming);bad.second_pass.seeds[0].address='tampered';assert.throws(()=>appendDiscovery(first.bundle,bad,empty,session,first.pack));
});
test('latest failed/missing child blocks fallback; independent continuation namespace',async()=>{
  const config={workflowName:CONTINUATION_WORKFLOW,campaign:CONTINUATION,stepName:CONTINUATION_STEP},run={id:90,name:CONTINUATION_WORKFLOW,run_number:19,status:'completed'};
  const fetch=async url=>url.includes('/artifacts?')?{artifacts:[]}:url.includes('/jobs?')?{jobs:[{steps:[{name:CONTINUATION_STEP,conclusion:'failure'}]}]}:{workflow_runs:[run]};
  await assert.rejects(previousTargetedArtifact(context,fetch,config),/refuse a fresh quota/);
  const artifact={id:1,name:`company-access-${CONTINUATION}-checkpoint-90`,expired:false};
  assert.equal((await previousTargetedArtifact(context,async url=>url.includes('/artifacts?')?{artifacts:[artifact]}:{workflow_runs:[run]},config)).id,1);
});
test('Actions packages pending key-free source + triage; no new key or network during tests',async()=>{
  const f=setup(),previous=startContinuation(f.parent,areas,f.guard),root=await fs.mkdtemp(path.join(os.tmpdir(),'jinke-continuation-'));
  try{const r=await executeContinuation({key,context,previous,root,guard:f.guard,dependencies:{sleep:async()=>{},fetchFn:async()=>Response.json({status:'1',pois:[]})}});
    assert.equal(r.report.api_requests_total,31);assert.equal(r.report.continuation.automatic_accepts,0);
    for(const file of CONTINUATION_FILES)assertKeyFree(await fs.readFile(path.join(r.artifact,file)),key);
    const bundle=JSON.parse(await fs.readFile(path.join(r.artifact,'review/review-bundle.json')));assert(bundle.second_pass);assert(bundle.batches[0].rows.every(i=>i.row.review_status==='pending'));
  }finally{await fs.rm(root,{recursive:true,force:true});}
});

test('final review precision is scoped: closed office held, facilities excluded without erasing duplicate flags',async()=>{
  const {secondPass}=await import('../web/src/company-access/review-triage.js');
  const row={company_name:'合成科技有限公司(暂停营业)',address:'合成路100号办公大厦12楼',amap_typecode:'170200',longitude_wgs84:121.6,latitude_wgs84:31.2};
  const old={seed_flags:['TARGETED_PRECISION_V1']},next={seed_flags:['TARGETED_PRECISION_V1','CONTINUATION_FINAL_REVIEW_V1']};
  assert.equal(secondPass(row,old).group,'trusted');assert.equal(secondPass(row,next).reason,'STALE_OR_UNCERTAIN');
  for(const name of ['合成公司停车场(入口)','合成快递柜','合成迷你仓']){
    const r={...row,company_name:name,possible_duplicate:true};const before=stable(r);
    assert.equal(secondPass(r,next).group,'exclude');assert.equal(stable(r),before);
  }
  assert.equal(secondPass({...row,company_name:'合成制造有限公司',amap_typecode:'170100'},next).group,'exception');
  assert.equal(secondPass(row,{...next,locked:true}).group,'history');
});
test('deployed continuation append preserves prior pending and locked decisions byte-for-byte',()=>{
  const f=setup(),p=prepareContinuation(startContinuation(f.parent,areas,f.guard),areas,f.guard);
  const history={schema_version:1,bundle_id:'empty',batches:[]},first=p.bundle,session=createSession(first);session.reviewer='Synthetic reviewer';
  const noted=decide(first,session,[first.batches[0].rows[0].key],'needs_review','Keep original note',date);
  const incoming=structuredClone(first);incoming.batches[0].id='final-new';incoming.batches[0].rows=incoming.batches[0].rows.slice(0,1);const i=incoming.batches[0].rows[0];i.key='final-new:SYNTHETIC-NEW';i.row.amap_poi_id='SYNTHETIC-NEW';incoming.bundle_id='new';
  const before=stable(first),after=appendDiscovery(first,incoming,history,noted,p.pack);
  assert.equal(stable(first),before);assert.deepEqual(after.session.decisions[first.batches[0].rows[0].key],noted.decisions[first.batches[0].rows[0].key]);
  assert.equal(after.session.decisions[i.key].status,'pending');assert.equal(after.session.decisions[i.key].history.length,0);
});
