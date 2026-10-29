import {validateBundle} from './review-state.js';
import {priorityEvidenceFor} from './priority-evidence.js';
import {prepareReachAreas,reachMemberships} from './model.js';
export const reviewStatusLabel={pending:'尚未审核 · 未批准',needs_review:'待核实 · 未批准',reject:'已排除 · 不上图',accept:'已批准办公室'};
// Build-time only join. Neither these records nor their coordinates enter approved sources.
export function candidateSearchRecords(bundle,areas){
  validateBundle(bundle);const index=prepareReachAreas(areas),seen=new Set();
  return bundle.batches.flatMap(b=>b.rows).filter(i=>i.row.review_status!=='accept').map(i=>{
    const r=i.row;if(seen.has(r.amap_poi_id))throw Error('Duplicate candidate identity');seen.add(r.amap_poi_id);
    const longitude=Number(r.longitude_wgs84),latitude=Number(r.latitude_wgs84);
    if(!String(r.longitude_wgs84).trim()||!String(r.latitude_wgs84).trim()||!Number.isFinite(longitude)||!Number.isFinite(latitude)||Math.abs(longitude)>180||Math.abs(latitude)>90)throw Error('Invalid candidate coordinate');
    return {id:`candidate:${r.amap_poi_id}`,kind:'candidate',amap_poi_id:r.amap_poi_id,company_name:r.company_name,address:r.address,district:r.district,longitude,latitude,review_status:r.review_status,locked:i.locked,provider_type:r.amap_type,source_url:r.source_reference,reach_minutes:reachMemberships({longitude,latitude},index),priority_evidence:priorityEvidenceFor(r)};
  }).sort((a,b)=>Number(Boolean(b.priority_evidence))-Number(Boolean(a.priority_evidence))||a.id.localeCompare(b.id));
}
export const reviewCandidateHref=poi=>`company-review.html?poi=${encodeURIComponent(poi)}`;
export function candidateFromLink(items,search){const poi=new URLSearchParams(search).get('poi');return poi?items.find(i=>i.row.amap_poi_id===poi)||null:null;}
export function validateCandidateSearch(value){
  if(!Array.isArray(value)||new Set(value.map(c=>c.id)).size!==value.length||value.some(c=>c.kind!=='candidate'||!['pending','needs_review','reject'].includes(c.review_status)||c.id!==`candidate:${c.amap_poi_id}`||!Number.isFinite(c.longitude)||!Number.isFinite(c.latitude)||Math.abs(c.longitude)>180||Math.abs(c.latitude)>90||!Array.isArray(c.reach_minutes)||c.reach_minutes.some(n=>![10,20,30,40,50].includes(n))))throw Error('Invalid candidate search artifact');return value;
}
