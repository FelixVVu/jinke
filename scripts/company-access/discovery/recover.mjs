// Offline reprocessing only: original provider snapshots and decisions are immutable.
import {validateSnapshot,candidatesFromCache,prepareCachedCandidates} from '../amap/acquire.mjs';
import {reviewRows,COLUMNS} from '../amap/review.mjs';
import {corporateType} from '../../../web/src/company-access/provider-types.js';
import {suggest,validateSession,exportRows} from '../../../web/src/company-access/review-state.js';
import {attachReviewHistory} from '../../../web/src/company-access/review-history.js';
import {ingest} from '../ingest.mjs';
import {mergeReviewedPilots} from '../amap/merge-reviewed.mjs';
import {sha256,stable} from '../common.mjs';
export const RECOVERY_VERSION='company-coverage-cache-v1';
const identity=p=>stable([p.name,p.address,p.location,p.adcode,p.typecode]);
export function recoverCandidates({snapshots,areas,priorDecisions=[]}){
  const locked=new Set(priorDecisions.map(d=>d.amap_poi_id));
  if(locked.size!==priorDecisions.length)throw Error('Duplicate historical decision');
  const groups=new Map(),legacy=new Map(),prepared=new Map();
  const sourceHashes=snapshots.map(snapshot=>{
    validateSnapshot(snapshot,areas);const hash=sha256(stable(snapshot));
    const old=candidatesFromCache(snapshot,areas);
    const next=prepareCachedCandidates(snapshot,areas,{policy:{max_candidates:100000},limit:30,providerScope:corporateType});
    prepared.set(hash,new Map(next.candidates.map(c=>[c.amap_poi_id,c])));
    legacy.set(hash,new Map(old.exclusions.filter(e=>e.amap_poi_id).map(e=>[e.amap_poi_id,e.reason])));
    for(const response of snapshot.responses)for(const poi of response.payload.pois){
      if(!poi?.id)continue;const rows=groups.get(poi.id)||[];
      rows.push({poi,snapshot_sha256:hash,pilot:snapshot.version,query_id:response.query_id});groups.set(poi.id,rows);
    }return hash;
  }).sort();
  if(new Set(sourceHashes).size!==sourceHashes.length)throw Error('Duplicate source snapshot');
  const candidates=[],excluded=[];
  for(const [id,occurrences] of [...groups].sort(([a],[b])=>a.localeCompare(b))){
    occurrences.sort((a,b)=>a.snapshot_sha256.localeCompare(b.snapshot_sha256)||a.query_id.localeCompare(b.query_id)||identity(a.poi).localeCompare(identity(b.poi)));
    if(locked.has(id)){excluded.push({amap_poi_id:id,reason:'HISTORICAL_DECISION_LOCKED'});continue;}
    if(occurrences.some(o=>identity(o.poi)!==identity(occurrences[0].poi))){excluded.push({amap_poi_id:id,reason:'CROSS_SNAPSHOT_ID_CONFLICT',occurrences});continue;}
    // Deterministic source choice, not an overwrite of any historical assertion.
    const ordered=[...new Set(occurrences.map(o=>o.snapshot_sha256))].sort();
    const candidate=ordered.map(h=>prepared.get(h).get(id)).find(Boolean);
    if(!candidate){excluded.push({amap_poi_id:id,reason:'OUTSIDE_30_OR_INVALID_OR_NON_CORPORATE'});continue;}
    candidates.push({...candidate,recovery:{source_snapshot_hashes:ordered,
      occurrences:occurrences.map(({poi,...o})=>o),original_exclusions:[...new Set(ordered.map(h=>legacy.get(h).get(id)).filter(Boolean))].sort()}});
  }
  const exact=new Map();
  for(const c of candidates){const k=stable([c.raw.company_name.normalize('NFKC').trim().toLowerCase(),c.raw.address.normalize('NFKC').trim()]);const g=exact.get(k)||[];g.push(c);exact.set(k,g);}
  for(const [k,group]of exact)if(group.length>1)for(const c of group){c.possible_duplicate=true;c.duplicate_group=sha256(k).slice(0,24);}
  return {version:RECOVERY_VERSION,sourceHashes,candidates,excluded};
}
export function recoveryBundle(recovered,priorOffices=[]){
  const id=sha256(stable({version:RECOVERY_VERSION,sources:recovered.sourceHashes,candidates:recovered.candidates}));
  const officeKey=r=>stable([r.company_name.normalize('NFKC').trim().toLowerCase(),r.address.normalize('NFKC').trim()]);
  const keys=new Set(priorOffices.map(officeKey));
  const rows=reviewRows(recovered.candidates).map((row,index)=>({key:`${id}:${row.amap_poi_id}`,row,locked:false,prior_review:null,
    suggestion:keys.has(officeKey(row))?{disposition:'needs_review',reason:'PRIOR_INVENTORY_MATCH'}:suggest(row),
    evidence:{source:'Original AMap cache, exact 30-minute reclip; no new acquisition',reference:row.source_reference,recovery:recovered.candidates[index].recovery}}));
  const batches=[{id,label:RECOVERY_VERSION,columns:COLUMNS,rows}];
  return {schema_version:1,bundle_id:sha256(stable(batches)),batches};
}
export function importRecovery({snapshots,areas,baseline,historyBundle,session,reviewedAt}){
  if(!Number.isFinite(Date.parse(reviewedAt)))throw Error('Invalid review time');
  const recovered=recoverCandidates({snapshots,areas,priorDecisions:baseline.decisions});
  const incoming=recoveryBundle(recovered,baseline.artifacts.offices.features.map(f=>f.properties));
  const bundle=attachReviewHistory(incoming,historyBundle);validateSession(bundle,session);
  if(!session.reviewer.trim())throw Error('Human reviewer required');
  const rows=exportRows(bundle,session,incoming.batches[0].id),byId=new Map(recovered.candidates.map(c=>[c.amap_poi_id,c]));
  const records=[],decisions=[];
  for(const row of rows){const c=byId.get(row.amap_poi_id);
    decisions.push({amap_poi_id:c.amap_poi_id,decision:row.review_status,notes:row.review_notes,reviewer:session.reviewer,reviewed_at:reviewedAt,query_ids:c.query_ids,raw_sha256:sha256(stable(c.raw)),discovery_lineage:c.recovery});
    if(row.review_status==='accept')records.push({...c.raw,source_evidence:{...c.raw.source_evidence,reviewed:true,description:`Human-reviewed mapped office. Reviewer: ${session.reviewer}. Notes: ${row.review_notes}`}});
  }
  const envelope={schema_version:1,dataset_kind:'candidate',dataset_version:`coverage-${incoming.bundle_id.slice(0,16)}`,records};
  const approved={envelope,decisions,artifacts:ingest(envelope,areas)};
  const merged=mergeReviewedPilots(baseline,approved,areas);
  const features=new Map(merged.artifacts.offices.features.map(f=>[f.id,f]));
  if(baseline.artifacts.offices.features.some(f=>stable(features.get(f.id))!==stable(f)))throw Error('BASELINE_OFFICE_CHANGED_REQUIRES_REVIEW');
  return {...merged,incoming,recovered,report:{human_accepts:records.length,prior_offices:baseline.artifacts.offices.features.length,canonical_offices:merged.artifacts.offices.features.length,new_dispositions:approved.artifacts.metadata.ingestion.dispositions}};
}
