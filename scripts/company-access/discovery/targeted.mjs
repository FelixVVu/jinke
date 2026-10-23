import {acquirePlan,prepareCachedCandidates,pilot3RecoveryState} from '../amap/acquire.mjs';
import {reviewRows,COLUMNS,qaReport} from '../amap/review.mjs';
import {corporateType} from '../../../web/src/company-access/provider-types.js';
import {suggest} from '../../../web/src/company-access/review-state.js';
import {sha256,stable,fail} from '../common.mjs';
import {targetedPlan,baseline,TARGETED_POLICY,CAMPAIGN} from './targeted-plan.mjs';
import {TARGETED_LEADS} from './targeted-leads.mjs';
import {providerDigest,assertionDigest,officeDigest} from './targeted-baseline.mjs';
export function validateTargeted(snapshot,areas,guard=baseline()){
  const plan=targetedPlan(areas,guard),queries=new Map(plan.queries.map(q=>[q.id,q]));
  if(snapshot?.version!==TARGETED_POLICY.version||stable(snapshot.plan)!==stable(plan)||!Array.isArray(snapshot.responses)||!Array.isArray(snapshot.attempts)||!/^\d{4}-\d{2}-\d{2}T.*Z$/.test(snapshot.collected_at)||!Number.isFinite(Date.parse(snapshot.collected_at)))fail('INVALID_TARGETED_SNAPSHOT');
  if(snapshot.attempts.length>48)fail('INVALID_ATTEMPT_LEDGER');
  const responses=new Map();
  for(const r of snapshot.responses){
    if(!queries.has(r.query_id)||responses.has(r.query_id)||r.payload_sha256!==sha256(stable(r.payload))||String(r.payload?.status)!=='1'||!Array.isArray(r.payload.pois)||r.payload.pois.length>25)fail('INVALID_CACHE');
    responses.set(r.query_id,r);
  }
  const seen=new Map(),successes=new Set();
  for(const a of snapshot.attempts){
    const q=queries.get(a.query_id),previous=seen.get(a.query_id)||[];
    if(!q||!['success','failure','uncertain'].includes(a.outcome)||previous.length>=2||previous.some(p=>p.outcome!=='failure'||p.retryable!==true))fail('INVALID_ATTEMPT_LEDGER');
    if(a.outcome==='failure'&&(!/^AMAP_[A-Z0-9_]+$|^INVALID_PAGE_SIZE$/.test(a.code||'')||typeof a.retryable!=='boolean'))fail('INVALID_ATTEMPT_LEDGER');
    if(q.page>1){const predecessor=plan.queries.find(p=>p.cell_id===q.cell_id&&p.page===q.page-1);if(!successes.has(predecessor.id)||responses.get(predecessor.id)?.payload.pois.length!==25)fail('INVALID_PAGINATION_LINEAGE');}
    if(a.outcome==='success'){if(!responses.has(a.query_id))fail('MISSING_SUCCESS_RESPONSE');successes.add(a.query_id);}
    previous.push(a);seen.set(a.query_id,previous);
  }
  if([...responses.keys()].some(id=>!successes.has(id)))fail('CACHE_WITHOUT_REQUEST_LINEAGE');
  return snapshot;
}
const normalize=s=>String(s||'').normalize('NFKC').toLowerCase().replace(/[\s\p{P}\p{S}]/gu,'');
export const leadNameHits=(name,lead)=>lead.terms.some(t=>normalize(t)&&normalize(name).includes(normalize(t)));
export function prepareTargeted(snapshot,areas,guard=baseline()){
  // Classification is a discovery filter, never an office or identity approval.
  const queries=new Map(snapshot.plan.queries.map(q=>[q.id,q]));
  const prepared=prepareCachedCandidates(snapshot,areas,{policy:{max_candidates:100000},limit:30,providerScope:(code,poi,occurrences)=>corporateType(code)||occurrences.some(o=>{
    const stream=queries.get(o.query_id)?.cell_id,lead=TARGETED_LEADS.find(l=>stream===`name:${l.id}`);return lead&&leadNameHits(poi.name,lead);
  })});
  const candidates=[],exclusions=[...prepared.exclusions];
  for(const c of prepared.candidates){const prior=guard.entries[providerDigest(c.amap_poi_id)];
    if(prior){exclusions.push({amap_poi_id:c.amap_poi_id,reason:prior.assertions.includes(assertionDigest(c.provider))?'KNOWN_ID_PRESERVED':'KNOWN_ID_CHANGED_REQUIRES_SEPARATE_REVIEW',origin:prior.origin});continue;}
    if(guard.approved_office_keys.includes(officeDigest(c.raw.company_name,c.raw.address))){c.possible_duplicate=true;c.duplicate_group='PRIOR_INVENTORY_MATCH';}
    c.discovery={campaign:CAMPAIGN,name_leads:TARGETED_LEADS.filter(l=>leadNameHits(c.raw.company_name,l)).map(l=>l.id),identity_binding:'unconfirmed_name_hit_only'};
    candidates.push(c);
  }
  for(const c of candidates.splice(TARGETED_POLICY.max_candidates))exclusions.push({amap_poi_id:c.amap_poi_id,reason:'PILOT_CANDIDATE_CAP',candidate:c});
  return {candidates,exclusions,counts:{...prepared.counts,candidate_review_count:candidates.length,known_ids_preserved:exclusions.filter(e=>e.reason==='KNOWN_ID_PRESERVED').length,known_id_conflicts:exclusions.filter(e=>e.reason==='KNOWN_ID_CHANGED_REQUIRES_SEPARATE_REVIEW').length}};
}
export function targetedBundle(snapshot,prepared){
  const id=snapshot.plan.plan_sha256;
  const rows=reviewRows(prepared.candidates).map((row,i)=>({key:`${id}:${row.amap_poi_id}`,row,locked:false,prior_review:null,
    suggestion:row.possible_duplicate?{disposition:'needs_review',reason:'PRIOR_INVENTORY_MATCH'}:suggest(row),
    evidence:{source:'Bounded targeted AMap discovery; mapped candidate only',reference:row.source_reference,discovery:prepared.candidates[i].discovery,
      sources:TARGETED_LEADS.filter(l=>prepared.candidates[i].discovery.name_leads.includes(l.id)).flatMap(l=>l.sources),limitations:'Name match does not establish entity identity, current occupancy or verified physical office confidence.'}}));
  const batches=[{id,label:CAMPAIGN,columns:COLUMNS,rows}];
  return {schema_version:1,bundle_id:sha256(stable(batches)),batches,campaign:CAMPAIGN,baseline_sha256:snapshot.plan.baseline_sha256};
}
const count=values=>values.reduce((a,k)=>(a[k]=(a[k]||0)+1,a),{});
export function targetedReport(snapshot,prepared){
  const cached=new Map(snapshot.responses.map(r=>[r.query_id,r])),recovery=pilot3RecoveryState(snapshot);
  const streams=snapshot.plan.streams.map(s=>{
    const queries=snapshot.plan.queries.filter(q=>q.cell_id===s.id),pages=queries.flatMap(q=>cached.has(q.id)?[{page:q.page,count:cached.get(q.id).payload.pois.length}]:[]),attempts=snapshot.attempts.filter(a=>queries.some(q=>q.id===a.query_id));
    const terminal=pages.some(p=>p.count<25),last=pages.at(-1);
    const status=!pages.length?(attempts.length?'failed_incomplete':'unsampled'):terminal?'sampled_partial':last.page===3?'saturated_incomplete':'pagination_incomplete';
    return {id:s.id,region_id:s.region_id||null,status,pages,attempts:attempts.length,provider_pagination_exhausted:terminal,inventory_complete:false,verified_empty:false};
  });
  const coverage={type:'FeatureCollection',features:snapshot.plan.cells.map(cell=>({type:'Feature',geometry:cell.geometry,properties:{cell_id:cell.id,bbox_wgs84:cell.bbox_wgs84,...streams.find(s=>s.id===cell.id)}}))};
  const benchmark=TARGETED_LEADS.filter(l=>l.source_kind!=='park_directory').map(lead=>{
    const raw=new Map(snapshot.responses.flatMap(r=>r.payload.pois.filter(p=>leadNameHits(p.name,lead)).map(p=>[p.id,p])));
    const pending=prepared.candidates.filter(c=>raw.has(c.amap_poi_id));
    return {...lead,raw_name_hit_ids:[...raw.keys()].sort(),pending_name_hit_ids:pending.map(c=>c.amap_poi_id),exclusions:prepared.exclusions.filter(e=>raw.has(e.amap_poi_id)).map(e=>({amap_poi_id:e.amap_poi_id,reason:e.reason})),identity_confirmed:false,
      recall_status:pending.length?'unconfirmed_in_scope_name_hit':raw.size?'returned_but_held_or_excluded':'not_returned_yet'};
  });
  return {...qaReport({snapshot,...prepared}),campaign:CAMPAIGN,baseline_sha256:snapshot.plan.baseline_sha256,streams,coverage,benchmark,
    discovery_name_hit_rate:{numerator:benchmark.filter(b=>b.raw_name_hit_ids.length).length,denominator:benchmark.length,not_identity_recall:true},
    verified_representative_recall:null,recall_limit:'New name hits are unbound leads. Verified spatial recall requires reviewed source POI identity and exact in-scope coordinates; unlocated benchmarks are not a false zero.',
    geographic_status:count(streams.filter(s=>s.region_id).map(s=>s.status)),remaining_gaps:streams.filter(s=>!s.provider_pagination_exhausted).map(s=>s.id),...recovery,
    limitations:['Sampling is incomplete even after provider pagination ends. Zero returns never proves an empty office area.','The 16 cells cover the four screenshot priority regions, not the entire 30-minute reach.','Corporate/industrial categories are discovery-only. Manufacturing-only sites require exclusion evidence; corporate offices and R&D remain eligible for human review.']};
}
export async function acquireTargeted({areas,guard=baseline(),...options}){
  return acquirePlan({...options,policy:TARGETED_POLICY,plan:targetedPlan(areas,guard),validate:s=>validateTargeted(s,areas,guard),prepare:s=>prepareTargeted(s,areas,guard),resumable:true});
}
