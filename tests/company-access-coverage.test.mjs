import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {planQueries} from '../scripts/company-access/amap/plan.mjs';
import {candidatesFromCache} from '../scripts/company-access/amap/acquire.mjs';
import {reviewRows,toCSV,approvedFromReview} from '../scripts/company-access/amap/review.mjs';
import {makeReviewBundle} from '../scripts/company-access/amap/console.mjs';
import {recoverCandidates,recoveryBundle,importRecovery} from '../scripts/company-access/discovery/recover.mjs';
import {geographicCoverage} from '../scripts/company-access/discovery/coverage.mjs';
import {buildTargetedPlan,validateLeads} from '../scripts/company-access/discovery/plan.mjs';
import {corporateType} from '../web/src/company-access/provider-types.js';
import {secondPass} from '../web/src/company-access/review-triage.js';
import {createSession,decide} from '../web/src/company-access/review-state.js';
import {attachReviewHistory} from '../web/src/company-access/review-history.js';
import {insideCoverageCell} from '../web/src/company-access/coverage-panel.js';
import {wgs84ToGcj02} from '../web/src/location-search.js';
import {sha256,stable} from '../scripts/company-access/common.mjs';
const areas=JSON.parse(await fs.readFile('web/public/data/reach-areas.geojson','utf8'));
const poi=(id,xy=[121.597836,31.2064028],typecode='170200')=>({id,name:`合成测试${id}科技有限公司`,address:`合成测试路${id}号创新大厦12层`,location:wgs84ToGcj02(...xy).join(','),typecode,type:'公司企业;公司',adname:'浦东新区',adcode:'310115'});
function snapshot(pois,version='amap-pilot-2'){
  const plan=planQueries(areas,version),query_id=plan.queries[0].id,payload={status:'1',pois};
  return {version,collected_at:'2026-10-23T00:00:00Z',plan,responses:[{query_id,payload,payload_sha256:sha256(stable(payload))}],attempts:[{query_id,outcome:'success'}]};
}
const point20=[121.58021407410764,31.207886420019406];
test('recovery accepts pipe-separated discovery categories in either order without altering historical policy',()=>{
  for(const code of ['170200|070000','060306|170204','170100|170200','141100'])assert.equal(corporateType(code),true);
  assert.equal(corporateType('050100'),false);assert.equal(corporateType('junk170200'),false);
  const s=snapshot([poi('A',undefined,'170200|070000'),poi('B',undefined,'070000|170200')]),before=stable(s);
  assert.equal(candidatesFromCache(s,areas).candidates.length,0);
  assert.equal(recoverCandidates({snapshots:[s],areas}).candidates.length,2);assert.equal(stable(s),before);
});
test('reuse Pilot 2 observations inside exact 20/30 reach; keep actual out-of-reach points excluded',()=>{
  const s=snapshot([poi('A',point20),poi('OUT',[120,30])]);
  assert.equal(candidatesFromCache(s,areas).candidates.length,0);
  const result=recoverCandidates({snapshots:[s],areas});assert.equal(result.candidates.length,1);
  assert.deepEqual(result.candidates[0].recovery.original_exclusions,['OUTSIDE_10_MINUTES']);
  assert.equal(result.candidates[0].inside_10_minute_reach,false);assert.equal(result.candidates[0].inside_30_minute_reach,true);
});
test('cross-snapshot conflicts and invalid coordinates do not become candidates',()=>{
  const one=snapshot([poi('A',point20)]),two=snapshot([{...poi('A',point20),address:'Different location'}, {...poi('BAD'),location:'unknown'}],'amap-pilot-1');
  const r=recoverCandidates({snapshots:[one,two],areas});assert.equal(r.candidates.length,0);
  assert.ok(r.excluded.some(e=>e.reason==='CROSS_SNAPSHOT_ID_CONFLICT'));
});
test('recovery locks all existing dispositions and reproduces across input ordering',()=>{
  const a=snapshot([poi('A'),poi('B'),poi('NEW',point20)]),b=snapshot([poi('C'),poi('D'),poi('NEW',point20)],'amap-pilot-1');
  const priorDecisions=['accept','reject','needs_review','pending'].map((decision,i)=>({amap_poi_id:'ABCD'[i],decision,notes:'unaltered'}));
  const before=stable(priorDecisions),first=recoverCandidates({snapshots:[a,b],areas,priorDecisions}),second=recoverCandidates({snapshots:[b,a],areas,priorDecisions});
  assert.deepEqual(first,second);assert.equal(first.candidates.length,1);assert.equal(stable(priorDecisions),before);
  const bundle=recoveryBundle(first);assert.ok(bundle.batches[0].rows.every(i=>!i.locked&&i.row.review_status==='pending'));
});
test('discovery eligibility never implies acceptance of mixed sites, store POIs or reviewed physical confidence',()=>{
  const base={company_name:'合成测试制造有限公司',address:'测试路1号总部大厦12层',amap_typecode:'170200',longitude_wgs84:121.6,latitude_wgs84:31.2};
  assert.equal(secondPass(base).group,'trusted');
  assert.equal(secondPass({...base,company_name:'合成电子公司(张江厂)',amap_typecode:'170100|170200'}).reason,'MIXED_SITE_LOCATION');
  assert.equal(secondPass({...base,amap_typecode:'170200|060000'}).reason,'MIXED_PROVIDER_CATEGORY');
  assert.equal(secondPass({...base,company_name:'合成便利店'}).group,'exclude');
  assert.equal(secondPass(base,{evidence:{assessment:'mixed_site_office_match'}}).group,'exception');
  assert.equal(secondPass(base,{evidence:{assessment:'manufacturing_only'}}).group,'exclude');
  assert.equal(secondPass(base,{evidence:{assessment:'office_address_match'}}).group,'trusted');
  assert.equal(secondPass(base,{locked:true}).group,'history');
});
test('pending recovery session imports zero offices; explicit human accept passes unchanged pipeline and preserves baseline',()=>{
  const s=snapshot([poi('BASE'),poi('NEW',point20)]);
  const csv=toCSV(reviewRows(candidatesFromCache(s,areas).candidates).map(r=>({...r,review_status:'accept'})));
  const baseline=approvedFromReview({snapshot:s,areas,csv,reviewer:'Synthetic human',reviewedAt:'2026-10-23T00:00:00Z'});
  const historyBundle=makeReviewBundle([s],areas,baseline.decisions,baseline.artifacts.offices.features.map(f=>f.properties));
  const recovered=recoverCandidates({snapshots:[s],areas,priorDecisions:baseline.decisions}),incoming=recoveryBundle(recovered,baseline.artifacts.offices.features.map(f=>f.properties)),bundle=attachReviewHistory(incoming,historyBundle);
  const session=createSession(bundle);session.reviewer='Synthetic human';
  const args={snapshots:[s],areas,baseline,historyBundle,reviewedAt:'2026-10-23T01:00:00Z'};
  const pending=importRecovery({...args,session});assert.equal(pending.report.human_accepts,0);assert.equal(pending.artifacts.offices.features.length,1);
  const accepted=decide(bundle,session,[incoming.batches[0].rows[0].key],'accept','Synthetic explicit decision');
  const imported=importRecovery({...args,session:accepted});assert.equal(imported.artifacts.offices.features.length,2);
  assert.deepEqual(imported.artifacts.offices.features.find(f=>f.id===baseline.artifacts.offices.features[0].id),baseline.artifacts.offices.features[0]);
  assert.deepEqual(imported.decisions[0],baseline.decisions[0]);assert.ok(imported.artifacts.offices.features.every(f=>f.properties.location_confidence==='building'));
  const forged=structuredClone(session);forged.decisions[incoming.batches[0].rows[0].key].status='accept';assert.throws(()=>importRecovery({...args,session:forged}),/explicit review history/);
});
test('reviewed rejects and held rows stay out of canonical recovery output',()=>{
  const s=snapshot([poi('BASE'),poi('NEW',point20)]),baseline=approvedFromReview({snapshot:s,areas,csv:toCSV(reviewRows(candidatesFromCache(s,areas).candidates).map(r=>({...r,review_status:'accept'}))),reviewer:'Synthetic human',reviewedAt:'2026-10-23T00:00:00Z'});
  const historyBundle=makeReviewBundle([s],areas,baseline.decisions),incoming=recoveryBundle(recoverCandidates({snapshots:[s],areas,priorDecisions:baseline.decisions}),baseline.artifacts.offices.features.map(f=>f.properties)),bundle=attachReviewHistory(incoming,historyBundle);
  for(const status of ['reject','needs_review']){const session=createSession(bundle);session.reviewer='Synthetic human';const edited=decide(bundle,session,[incoming.batches[0].rows[0].key],status,'hold');
    const imported=importRecovery({snapshots:[s],areas,baseline,historyBundle,session:edited,reviewedAt:'2026-10-23T01:00:00Z'});assert.equal(imported.artifacts.offices.features.length,1);assert.equal(imported.decisions.at(-1).decision,status);}
});
test('diagnostics separate first-page saturation, failures, coarse-only coverage and unknown benchmark locations',()=>{
  const s=snapshot(Array.from({length:25},(_,i)=>poi(String(i))),'amap-pilot-3');
  s.attempts.push({query_id:s.plan.queries[1].id,outcome:'failure',code:'AMAP_NETWORK',retryable:true});
  const recovered=recoverCandidates({snapshots:[s],areas});
  const r=geographicCoverage({snapshots:[s],areas,offices:{features:[]},decisions:[],recovered,benchmarks:[{company_name:'not observed',poi_ids:[],discovery_terms:['not observed']}]});
  assert.equal(r.summary.fine_sampled,1);assert.equal(r.summary.fine_failed,1);assert.equal(r.summary.saturated,1);
  assert.equal(r.summary.fine_unqueried,81);assert.equal(r.summary.verified_empty,0);assert.equal(r.benchmark[0].stage,'not_returned_in_cached_queries');assert.equal(r.summary.benchmark_located,0);
  assert.ok(r.coverage.features.every(f=>f.properties.verified_empty===false));
});
const leads=[{id:'synthetic',company_name:'合成公司',source_kind:'official_corporate',scope:'corporate_office',limitations:'Synthetic only',target_name_search:true,sources:[{url:'https://example.com/synthetic',title:'Synthetic',checked_at:'2026-10-23'}]}];
test('targeted plan is bounded, deterministic, finer than the old cells and retains exact 30-minute scope',()=>{
  const args={areas,priorityCellIds:['r10c7','r10c9','r11c8','r11c9'],leads};
  const plan=buildTargetedPlan(args);assert.deepEqual(plan,buildTargetedPlan(args));assert.equal(plan.policy.max_attempts,48);assert.equal(plan.execution_enabled,false);
  assert.equal(plan.policy.scope_minutes,30);assert.ok(plan.streams.length<=17);assert.equal(plan.queries[0].operation,'text');
  assert.ok(plan.queries.filter(q=>q.operation==='text').every(q=>!('types'in q.parameters)&&q.parameters.city_limit==='true'));
  assert.ok(plan.queries.every(q=>q.page<=3&&q.parameters.page_size==='25'));assert.ok(plan.streams.filter(s=>s.operation==='polygon').every(s=>s.geometry.coordinates.length));
  assert.throws(()=>buildTargetedPlan({...args,priorityCellIds:['outside-scope']}));assert.throws(()=>buildTargetedPlan({...args,priorityCellIds:['r10c7','r10c7']}));
});
test('source leads cannot infer current occupancy from historical references or unknown coordinates',()=>{
  assert.equal(validateLeads(leads),leads);
  for(const patch of [{source_kind:'historical_reference',current_occupancy:true},{coordinates:[121,31]},{sources:[{url:'javascript:alert(1)',title:'bad',checked_at:'2026-10-23'}]}])assert.throws(()=>validateLeads([{...leads[0],...patch}]));
});
test('coverage cell filtering does not mutate candidate coordinates or decisions',()=>{
  const item={row:{longitude_wgs84:121.6,latitude_wgs84:31.2,review_status:'pending'}},before=structuredClone(item),feature={properties:{bbox_wgs84:[121.59,31.19,121.61,31.21]}};
  assert.equal(insideCoverageCell(item,feature),true);assert.equal(insideCoverageCell(item,null),true);assert.equal(insideCoverageCell({...item,row:{...item.row,longitude_wgs84:120}},feature),false);assert.deepEqual(item,before);
});
