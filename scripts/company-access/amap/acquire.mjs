import { requestAmap } from '../../../hosting/server/amap-client.mjs';
import { prepareReachAreas } from '../../../web/src/company-access/model.js';
import { normalizeCoordinates } from '../coordinates.mjs';
import { validateRawRecord } from '../validate.mjs';
import { normalizeCompanyName } from '../../../web/src/company-access/schema.js';
import { addressKey } from '../normalize.mjs';
import { compare, fail, sha256, stable } from '../common.mjs';
import { planQueries, POLICY } from './plan.mjs';
const text=value=>typeof value==='string'?value.trim():'';
export function candidatesFromCache(snapshot, areas) {
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
    if(!/^1702\d{2}$/.test(text(poi.typecode))){exclusions.push({amap_poi_id:id,reason:'OUT_OF_PROVIDER_SCOPE',occurrences});continue;}
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
      if(!reach.contains(converted.coordinates,30)){exclusions.push({amap_poi_id:id,reason:'OUTSIDE_30_MINUTES',occurrences,coordinate_provenance:converted.audit});continue;}
      validateRawRecord(raw);
      candidates.push({amap_poi_id:id,raw,longitude_wgs84:converted.coordinates[0],latitude_wgs84:converted.coordinates[1],coordinate_provenance:converted.audit,
        provider:poi,query_ids:references,inside_30_minute_reach:true,possible_duplicate:false,duplicate_group:''});
    }catch(error){exclusions.push({amap_poi_id:id,reason:error.code||'INVALID_PROVIDER_RECORD',occurrences});}
  }
  const sameOffice=new Map();
  for(const c of candidates){const key=stable([normalizeCompanyName(c.raw.company_name),addressKey(c.raw.address)]);const group=sameOffice.get(key)||[];group.push(c);sameOffice.set(key,group);}
  for(const [key,group] of sameOffice) if(group.length>1) for(const c of group){c.possible_duplicate=true;c.duplicate_group=sha256(key).slice(0,24);}
  const overflow=candidates.splice(POLICY.max_candidates);
  for(const c of overflow)exclusions.push({amap_poi_id:c.amap_poi_id,reason:'PILOT_CANDIDATE_CAP',candidate:c});
  return {candidates,exclusions,counts:{raw_poi_results:rawCount,unique_amap_ids:groups.size,overlap_duplicates:[...groups.values()].reduce((n,g)=>n+g.length-1,0),
    candidate_review_count:candidates.length,outside_30_minute_rejects:exclusions.filter(e=>e.reason==='OUTSIDE_30_MINUTES').length,
    coordinate_failures:exclusions.filter(e=>['INVALID_COORDINATES','CONVERSION_OUTSIDE_SUPPORTED_REGION'].includes(e.reason)).length,
    provider_id_conflicts:exclusions.filter(e=>e.reason==='POI_ID_CONFLICT').length}};
}
export function validateSnapshot(snapshot, areas) {
  const plan=planQueries(areas);
  if(snapshot?.version!==POLICY.version||stable(snapshot.plan)!==stable(plan)||!Array.isArray(snapshot.responses)||!Array.isArray(snapshot.attempts)||
    !/^\d{4}-\d{2}-\d{2}T.*Z$/.test(snapshot.collected_at)||!Number.isFinite(Date.parse(snapshot.collected_at))) fail('INVALID_SNAPSHOT');
  const queries=new Map(plan.queries.map(q=>[q.id,q])),seen=new Set();
  for(const r of snapshot.responses){
    if(!queries.has(r.query_id)||seen.has(r.query_id)||r.payload_sha256!==sha256(stable(r.payload))||String(r.payload?.status)!=='1'||!Array.isArray(r.payload.pois)||r.payload.pois.length>POLICY.page_size)fail('INVALID_CACHE');
    if(!snapshot.attempts.some(a=>a.query_id===r.query_id&&a.outcome==='success'))fail('CACHE_WITHOUT_REQUEST_LINEAGE');
    seen.add(r.query_id);
  }
  if(snapshot.attempts.length>POLICY.max_requests||snapshot.attempts.some(a=>!queries.has(a.query_id)||!['success','failure'].includes(a.outcome)))fail('INVALID_ATTEMPT_LEDGER');
  return snapshot;
}
/** Private server job; env is the existing Worker binding, never serialized.
 * checkpoint receives only sanitized, key-free state after every request.
 * One serialized job per run; retries count against the lifetime request budget.
 */
export async function acquire({env,areas,collectedAt,previous=null,fetchFn=fetch,sleep=ms=>new Promise(r=>setTimeout(r,ms)),checkpoint=async()=>{}}){
  const snapshot=previous?structuredClone(validateSnapshot(previous,areas)):{version:POLICY.version,collected_at:collectedAt,plan:planQueries(areas),responses:[],attempts:[]};
  validateSnapshot(snapshot,areas);
  const cached=new Map(snapshot.responses.map(r=>[r.query_id,r]));
  let calls=0,hits=0,stop='PLAN_COMPLETE';
  const checkpointSafe=async()=>{await checkpoint(structuredClone(snapshot));};
  for(const q of snapshot.plan.queries){
    if(q.page>1){const prev=snapshot.plan.queries.find(p=>p.cell_id===q.cell_id&&p.page===q.page-1);const page=cached.get(prev.id);if(!page||page.payload.pois.length<POLICY.page_size)continue;}
    if(cached.has(q.id)){hits++;continue;}
    if(candidatesFromCache(snapshot,areas).candidates.length>=POLICY.max_candidates){stop='CANDIDATE_CAP';break;}
    if(snapshot.attempts.length>=POLICY.max_requests){stop='REQUEST_BUDGET';break;}
    if(!env?.JINKE_AMAP_KEY){stop='AMAP_NOT_CONFIGURED';break;}
    // Fatal failures are sticky across resume; no retrying quota/auth rejections.
    if(snapshot.attempts.some(a=>a.query_id===q.id&&a.outcome==='failure'&&!a.retryable)){stop='PROVIDER_STOP';break;}
    let success=false;
    for(let attempt=0;attempt<2;attempt++){
      const priorFailures=snapshot.attempts.filter(a=>a.query_id===q.id&&a.outcome==='failure').length;
      if(priorFailures>=2||snapshot.attempts.length>=POLICY.max_requests){stop='REQUEST_BUDGET_OR_RETRY_CAP';break;}
      await sleep(priorFailures?POLICY.retry_ms:POLICY.pacing_ms);
      calls++;
      try{
        const payload=await requestAmap(env,'polygon',q.parameters,fetchFn);
        if(payload.pois.length>POLICY.page_size)fail('INVALID_PAGE_SIZE');
        const entry={query_id:q.id,payload,payload_sha256:sha256(stable(payload))};
        snapshot.responses.push(entry);cached.set(q.id,entry);snapshot.attempts.push({query_id:q.id,outcome:'success'});success=true;stop='PLAN_COMPLETE';
      }catch(error){
        // Fixed local codes only; never stringify provider exceptions.
        const code=/^(AMAP_|INVALID_PAGE_SIZE)/.test(error.code||'')?error.code:'AMAP_REQUEST_FAILED';
        snapshot.attempts.push({query_id:q.id,outcome:'failure',code,retryable:error.retryable===true});
        stop=code;
        await checkpointSafe();
        if(!error.retryable)break;
        continue;
      }
      await checkpointSafe();break;
    }
    if(!success)break;
  }
  const prepared=candidatesFromCache(snapshot,areas);
  snapshot.execution={api_requests_this_execution:calls,cached_requests_this_execution:hits,api_requests_total:snapshot.attempts.length,
    provider_failures:snapshot.attempts.filter(a=>a.outcome==='failure'),query_cell_count:snapshot.plan.cells.length,stop_reason:stop};
  await checkpointSafe();
  return {snapshot,...prepared,execution:snapshot.execution};
}
