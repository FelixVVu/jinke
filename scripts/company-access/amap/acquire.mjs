import { requestAmap } from '../../../hosting/server/amap-client.mjs';
import { prepareReachAreas } from '../../../web/src/company-access/model.js';
import { normalizeCoordinates } from '../coordinates.mjs';
import { validateRawRecord } from '../validate.mjs';
import { normalizeCompanyName } from '../../../web/src/company-access/schema.js';
import { addressKey } from '../normalize.mjs';
import { compare, fail, sha256, stable } from '../common.mjs';
import { planQueries, POLICY, policyFor, reachLimitFor } from './plan.mjs';
const text=value=>typeof value==='string'?value.trim():'';
export function candidatesFromCache(snapshot, areas) {
  const POLICY=policyFor(snapshot.version),limit=reachLimitFor(snapshot.version);
  // Historical snapshots retain their original scope and hashes. Coverage repair
  // calls the same coordinate/validation path with an explicit discovery policy.
  return prepareCachedCandidates(snapshot,areas,{policy:POLICY,limit,providerScope:code=>/^1702\d{2}$/.test(code)});
}
export function prepareCachedCandidates(snapshot,areas,{policy:POLICY,limit,providerScope}) {
  const reach=prepareReachAreas(areas), groups=new Map(), exclusions=[], candidates=[];
  let rawCount=0;
  for(const entry of snapshot.responses) for(const poi of entry.payload.pois){
    rawCount++;
    if(!poi||typeof poi!=='object'||!text(poi.id)){exclusions.push({reason:'MISSING_POI_ID',query_id:entry.query_id,poi});continue;}
    const entries=groups.get(poi.id)||[];entries.push({poi,query_id:entry.query_id});groups.set(poi.id,entries);
  }
  for(const [id,occurrences] of [...groups].sort((a,b)=>compare(a[0],b[0]))){
    const poi=occurrences[0].poi, references=occurrences.map(p=>p.query_id);
    // Different assertions about one stable ID need review, never first-wins.
    const identity=p=>stable([p.name,p.address,p.location,p.adcode,p.typecode]);
    if(occurrences.some(p=>identity(p.poi)!==identity(poi))){exclusions.push({amap_poi_id:id,reason:'POI_ID_CONFLICT',occurrences});continue;}
    if(!providerScope(text(poi.typecode),poi,occurrences)){exclusions.push({amap_poi_id:id,reason:'OUT_OF_PROVIDER_SCOPE',occurrences});continue;}
    try{
      const parts=text(poi.location).split(',');
      if(parts.length!==2||parts.some(p=>!p.trim()))fail('INVALID_COORDINATES');
      const raw={source_namespace:'amap',source_record_id:id,company_name:text(poi.name),address:text(poi.address),district:text(poi.adname)||null,
        // Indoor parent ID is not a building name. Retain it only in provider metadata.
        building_name:text(poi.building_name)||null,longitude:Number(parts[0]),latitude:Number(parts[1]),coordinate_system:'GCJ02',industry_code:null,sector:null,
        source_type:'licensed_poi',source_url:`https://www.amap.com/place/${encodeURIComponent(id)}`,
        source_evidence:{kind:'map_poi',description:'Unreviewed AMap company POI; physical office requires human review.',reviewed:false},
        collected_at:snapshot.collected_at,verified_at:null};
      const converted=normalizeCoordinates(raw);
      if(!reach.contains(converted.coordinates,limit)){exclusions.push({amap_poi_id:id,reason:`OUTSIDE_${limit}_MINUTES`,occurrences,coordinate_provenance:converted.audit});continue;}
      validateRawRecord(raw);
      candidates.push({amap_poi_id:id,raw,longitude_wgs84:converted.coordinates[0],latitude_wgs84:converted.coordinates[1],coordinate_provenance:converted.audit,
        provider:poi,query_ids:references,inside_30_minute_reach:reach.contains(converted.coordinates,30),inside_10_minute_reach:reach.contains(converted.coordinates,10),possible_duplicate:false,duplicate_group:''});
    }catch(error){exclusions.push({amap_poi_id:id,reason:error.code||'INVALID_PROVIDER_RECORD',occurrences});}
  }
  const sameOffice=new Map();
  for(const c of candidates){const key=stable([normalizeCompanyName(c.raw.company_name),addressKey(c.raw.address)]);const group=sameOffice.get(key)||[];group.push(c);sameOffice.set(key,group);}
  for(const [key,group] of sameOffice) if(group.length>1) for(const c of group){c.possible_duplicate=true;c.duplicate_group=sha256(key).slice(0,24);}
  const overflow=candidates.splice(POLICY.max_candidates);
  for(const c of overflow)exclusions.push({amap_poi_id:c.amap_poi_id,reason:'PILOT_CANDIDATE_CAP',candidate:c});
  return {candidates,exclusions,counts:{raw_poi_results:rawCount,unique_amap_ids:groups.size,overlap_duplicates:[...groups.values()].reduce((n,g)=>n+g.length-1,0),
    candidate_review_count:candidates.length,outside_target_reach_rejects:exclusions.filter(e=>e.reason===`OUTSIDE_${limit}_MINUTES`).length,outside_30_minute_rejects:exclusions.filter(e=>e.reason==='OUTSIDE_30_MINUTES').length,
    coordinate_failures:exclusions.filter(e=>['INVALID_COORDINATES','CONVERSION_OUTSIDE_SUPPORTED_REGION'].includes(e.reason)).length,
    provider_id_conflicts:exclusions.filter(e=>e.reason==='POI_ID_CONFLICT').length}};
}
export function validateSnapshot(snapshot, areas) {
  const POLICY=policyFor(snapshot?.version),plan=planQueries(areas,POLICY.version);
  if(snapshot?.version!==POLICY.version||stable(snapshot.plan)!==stable(plan)||!Array.isArray(snapshot.responses)||!Array.isArray(snapshot.attempts)||
    !/^\d{4}-\d{2}-\d{2}T.*Z$/.test(snapshot.collected_at)||!Number.isFinite(Date.parse(snapshot.collected_at))) fail('INVALID_SNAPSHOT');
  const queries=new Map(plan.queries.map(q=>[q.id,q])),seen=new Set();
  for(const r of snapshot.responses){
    if(!queries.has(r.query_id)||seen.has(r.query_id)||r.payload_sha256!==sha256(stable(r.payload))||String(r.payload?.status)!=='1'||!Array.isArray(r.payload.pois)||r.payload.pois.length>POLICY.page_size)fail('INVALID_CACHE');
    if(!snapshot.attempts.some(a=>a.query_id===r.query_id&&a.outcome==='success'))fail('CACHE_WITHOUT_REQUEST_LINEAGE');
    seen.add(r.query_id);
  }
  if(snapshot.attempts.length>POLICY.max_requests||snapshot.attempts.some(a=>!queries.has(a.query_id)||!['success','failure',...(POLICY.version==='amap-pilot-3'?['uncertain']:[])].includes(a.outcome)))fail('INVALID_ATTEMPT_LEDGER');
  return snapshot;
}
// Derived from the immutable request ledger, including older Pilot 3 checkpoints.
// These recovery rules do not change the fixed plan or allocate a fresh quota.
export function pilot3RecoveryState(snapshot){
  const completed=new Set(snapshot.responses.map(r=>r.query_id)),byQuery=new Map();
  for(const a of snapshot.attempts){const list=byQuery.get(a.query_id)||[];list.push(a);byQuery.set(a.query_id,list);}
  const incomplete_queries=snapshot.plan.queries.flatMap(q=>{
    if(completed.has(q.id))return [];
    const attempts=byQuery.get(q.id)||[];
    const reason=attempts.some(a=>a.outcome==='uncertain')?'UNCERTAIN_REQUEST':
      attempts.filter(a=>a.outcome==='failure'&&a.retryable===true).length>=2?'RETRY_EXHAUSTED':null;
    return reason?[{query_id:q.id,cell_id:q.cell_id,page:q.page,reason}]:[];
  });
  const queryCells=new Map(snapshot.plan.queries.map(q=>[q.id,q.cell_id])),cells=new Set();let failures=0;
  for(const a of [...snapshot.attempts].reverse()){
    if(a.outcome!=='failure'||a.retryable!==true||!/^AMAP_(NETWORK|HTTP_5\d{2})$/.test(a.code||''))break;
    failures++;cells.add(queryCells.get(a.query_id));
  }
  return {incomplete_queries,connectivity:{consecutive_failures:failures,cell_ids:[...cells].sort(),open:failures>=4&&cells.size>=2}};
}
/** Private server job; env is the existing Worker binding, never serialized.
 * checkpoint receives only sanitized, key-free state after every request.
 * One serialized job per run; retries count against the lifetime request budget.
 */
export async function acquire({env,areas,collectedAt,previous=null,fetchFn=fetch,sleep=ms=>new Promise(r=>setTimeout(r,ms)),checkpoint=async()=>{},pilotVersion=POLICY.version}){
  const POLICY=policyFor(pilotVersion);
  return acquirePlan({env,collectedAt,previous,fetchFn,sleep,checkpoint,policy:POLICY,plan:planQueries(areas,POLICY.version),
    validate:s=>validateSnapshot(s,areas),prepare:s=>candidatesFromCache(s,areas),resumable:POLICY.version==='amap-pilot-3'});
}
// Shared bounded executor. Callers supply a fixed, validated server-side plan;
// this is not exposed as a browser route or an arbitrary provider proxy.
export async function acquirePlan({env,collectedAt,previous=null,fetchFn=fetch,sleep=ms=>new Promise(r=>setTimeout(r,ms)),checkpoint=async()=>{},policy:POLICY,plan,validate,prepare,resumable=true,assertSafe=()=>{}}){
  const snapshot=previous?structuredClone(validate(previous)):{version:POLICY.version,collected_at:collectedAt,plan,responses:[],attempts:[]};
  if(snapshot.version!==POLICY.version)fail('PILOT_VERSION_MISMATCH');
  validate(snapshot);
  const cached=new Map(snapshot.responses.map(r=>[r.query_id,r]));
  const pilot3=resumable;
  const retryExhausted=q=>snapshot.attempts.filter(a=>a.query_id===q.id&&a.outcome==='failure'&&a.retryable===true).length>=2;
  let calls=0,hits=0,stop='PLAN_COMPLETE';
  const checkpointSafe=async()=>{await checkpoint(structuredClone(snapshot));};
  for(const q of snapshot.plan.queries){
    if(q.page>1){const prev=snapshot.plan.queries.find(p=>p.cell_id===q.cell_id&&p.page===q.page-1);const page=cached.get(prev.id);if(!page||page.payload.pois.length<POLICY.page_size)continue;}
    if(cached.has(q.id)){hits++;continue;}
    if(prepare(snapshot).candidates.length>=POLICY.max_candidates){stop='CANDIDATE_CAP';break;}
    if(snapshot.attempts.length>=POLICY.max_requests){stop='REQUEST_BUDGET';break;}
    if(calls>=(POLICY.max_requests_per_execution??Infinity)){stop='EXECUTION_BUDGET';break;}
    if(pilot3&&pilot3RecoveryState(snapshot).connectivity.open){stop='AMAP_CONNECTIVITY_STOP';break;}
    if(snapshot.attempts.some(a=>a.query_id===q.id&&a.outcome==='uncertain'))continue;
    if(!env?.JINKE_AMAP_KEY){stop='AMAP_NOT_CONFIGURED';break;}
    // Fatal failures are sticky across resume; no retrying quota/auth rejections.
    if(snapshot.attempts.some(a=>a.query_id===q.id&&a.outcome==='failure'&&!a.retryable)){stop='PROVIDER_STOP';break;}
    if(pilot3&&retryExhausted(q))continue;
    let success=false;
    for(let attempt=0;attempt<2;attempt++){
      const priorFailures=snapshot.attempts.filter(a=>a.query_id===q.id&&a.outcome==='failure').length;
      if(calls>=(POLICY.max_requests_per_execution??Infinity)){stop='EXECUTION_BUDGET';break;}
      if(pilot3&&pilot3RecoveryState(snapshot).connectivity.open){stop='AMAP_CONNECTIVITY_STOP';break;}
      if(priorFailures>=2||snapshot.attempts.length>=POLICY.max_requests){stop='REQUEST_BUDGET_OR_RETRY_CAP';break;}
      await sleep(priorFailures?POLICY.retry_ms:POLICY.pacing_ms);
      calls++;
      // Pilot 3 reserves before network I/O. An interrupted request is never free
      // or retried blindly after restoring a checkpoint.
      const reservation=resumable?{query_id:q.id,outcome:'uncertain'}:null;
      if(reservation){snapshot.attempts.push(reservation);await checkpointSafe();}
      try{
        const payload=await requestAmap(env,q.operation||'polygon',q.parameters,fetchFn);
        if(payload.pois.length>POLICY.page_size)fail('INVALID_PAGE_SIZE');
        assertSafe(payload);
        const entry={query_id:q.id,payload,payload_sha256:sha256(stable(payload))};
        snapshot.responses.push(entry);cached.set(q.id,entry);if(reservation)reservation.outcome='success';else snapshot.attempts.push({query_id:q.id,outcome:'success'});success=true;stop='PLAN_COMPLETE';
      }catch(error){
        // Fixed local codes only; never stringify provider exceptions.
        const code=/^(AMAP_|INVALID_PAGE_SIZE)/.test(error.code||'')?error.code:'AMAP_REQUEST_FAILED';
        const failure={query_id:q.id,outcome:'failure',code,retryable:error.retryable===true};if(reservation)Object.assign(reservation,failure);else snapshot.attempts.push(failure);
        stop=code;
        await checkpointSafe();
        if(!error.retryable)break;
        continue;
      }
      await checkpointSafe();break;
    }
    if(!success){
      if(pilot3&&pilot3RecoveryState(snapshot).connectivity.open){stop='AMAP_CONNECTIVITY_STOP';break;}
      if(pilot3&&retryExhausted(q)){
        // Isolated failures leave this cell incomplete; other cells can proceed.
        stop='PLAN_COMPLETE';continue;
      }
      break;
    }
  }
  const prepared=prepare(snapshot);
  const recovery=pilot3?pilot3RecoveryState(snapshot):null;
  if(stop==='PLAN_COMPLETE'&&recovery?.incomplete_queries.length)stop='PLAN_COMPLETE_WITH_GAPS';
  snapshot.execution={api_requests_this_execution:calls,cached_requests_this_execution:hits,api_requests_total:snapshot.attempts.length,
    provider_failures:snapshot.attempts.filter(a=>a.outcome==='failure'),query_cell_count:snapshot.plan.cells.length,stop_reason:stop,...(recovery||{})};
  await checkpointSafe();
  return {snapshot,...prepared,execution:snapshot.execution};
}
