import fs from 'node:fs';
import {sha256,stable,fail} from '../common.mjs';
import {acquirePlan} from '../amap/acquire.mjs';
import {TARGETED_POLICY,baseline} from './targeted-plan.mjs';
import {validateTargeted,validateRequestLedger,prepareTargeted,targetedBundle,targetedReport} from './targeted.mjs';
import {TARGETED_LEADS} from './targeted-leads.mjs';
import {CONTINUATION_SOURCES,FACILITY_LEADS,matchingSources,sourceEvidence} from './continuation-sources.mjs';
import {TRIAGE_VERSION,triageItems,validateSecondPass,isPriority} from '../../../web/src/company-access/review-triage.js';
export const CONTINUATION='targeted-30-continuation-v1';
export const CONTINUATION_WORKFLOW='Company Access targeted 30m continuation (manual review only)';
export const CONTINUATION_STEP='Continue targeted 30m within original lifetime budget';
export const continuationGuard=()=>JSON.parse(fs.readFileSync(new URL('./continuation-baseline.json',import.meta.url)));
export const CONTINUATION_POLICY=Object.freeze({...TARGETED_POLICY,version:CONTINUATION,max_requests_per_execution:12});
// Same 48 lifetime attempts, 300 active review slots. No fresh request allocation.
export function continuedPlan(parent,guard){
  const streams=CONTINUATION_SOURCES.map(l=>({id:`name:${l.id}`,lead_id:l.id,operation:'text',parameters:{keywords:l.company_name,region:'上海市',city_limit:'true',show_fields:'indoor'}}));
  const added=streams.flatMap(s=>[1,2,3].map(page=>{const parameters={...s.parameters,page_size:'25',page_num:String(page)};return {id:sha256(stable({operation:s.operation,parameters})),cell_id:s.id,page,operation:s.operation,parameters};}));
  // First finish page 2 in all saturated geographic cells, interleaving original
  // region order, with six source-backed names first. Page 3 is strictly later.
  const original=parent.plan.queries;
  const queries=[...original.filter(q=>q.page===1),...added.filter(q=>q.page===1),
    ...original.filter(q=>q.page===2&&q.operation==='polygon'),...original.filter(q=>q.page===2&&q.operation==='text'),
    ...original.filter(q=>q.page===3&&q.operation==='polygon'),...added.filter(q=>q.page===2),
    ...original.filter(q=>q.page===3&&q.operation==='text'),...added.filter(q=>q.page===3)];
  const p={...parent.plan,campaign:CONTINUATION,policy:CONTINUATION_POLICY,parent_snapshot_sha256:sha256(stable(parent)),
    continuation_baseline_sha256:sha256(stable(guard)),supplement_sources_sha256:sha256(stable({sources:CONTINUATION_SOURCES,facilities:FACILITY_LEADS,triage_version:TRIAGE_VERSION})),streams:[...parent.plan.streams,...streams],queries};
  delete p.plan_sha256;return {...p,plan_sha256:sha256(stable(p))};
}
export function validateContinuation(s,areas,guard=continuationGuard(),originalGuard=baseline()){
  if(!s?.parent)fail('MISSING_PARENT_CHECKPOINT');validateTargeted(s.parent,areas,originalGuard);
  if(sha256(stable(s.parent))!==guard.parent_snapshot_sha256)fail('PARENT_CHECKPOINT_CHANGED');
  if(s.version!==CONTINUATION||stable(s.plan)!==stable(continuedPlan(s.parent,guard))||s.collected_at!==s.parent.collected_at||!Array.isArray(s.attempts)||!Array.isArray(s.responses))fail('INVALID_CONTINUATION');
  if(stable(s.attempts.slice(0,s.parent.attempts.length))!==stable(s.parent.attempts)||stable(s.responses.slice(0,s.parent.responses.length))!==stable(s.parent.responses))fail('PARENT_LEDGER_CHANGED');
  validateRequestLedger(s);return s;
}
export function startContinuation(parent,areas,guard=continuationGuard(),originalGuard=baseline()){
  const s={version:CONTINUATION,collected_at:parent.collected_at,parent:structuredClone(parent),plan:continuedPlan(parent,guard),responses:structuredClone(parent.responses),attempts:structuredClone(parent.attempts)};
  return validateContinuation(s,areas,guard,originalGuard);
}
export function prepareContinuation(snapshot,areas,guard=continuationGuard()){
  // At most 48 x 25 observations. Nothing is discarded to manufacture capacity.
  // Prior decisions/queues are immutable by hashed provider ID/assertion guards.
  const prepared=prepareTargeted(snapshot,areas,guard,{maxCandidates:1200,leads:[...TARGETED_LEADS,...CONTINUATION_SOURCES]});
  for(const c of prepared.candidates)c.discovery.campaign=CONTINUATION;
  const bundle=targetedBundle(snapshot,prepared);bundle.campaign=CONTINUATION;bundle.batches[0].label=CONTINUATION;
  for(const i of bundle.batches[0].rows)i.evidence.sources=matchingSources(i.row).flatMap(l=>l.sources);
  const pack={schema_version:1,version:TRIAGE_VERSION,bundle_id:bundle.bundle_id,
    evidence:bundle.batches[0].rows.map(i=>sourceEvidence(i.row)).filter(Boolean),
    seeds:bundle.batches[0].rows.map(i=>({poi_id:i.row.amap_poi_id,company_name:i.row.company_name,address:i.row.address,decision:'pending',flags:['TARGETED_PRECISION_V1']}))};
  validateSecondPass(bundle,pack);
  const items=triageItems(bundle.batches[0].rows,pack.evidence,pack.seeds);
  // The gate limits a useful review worklist, not the evidence store. Every
  // ambiguous / excluded suggestion remains pending in the full bundle + cache.
  const active=items.filter(i=>i.triage.group==='trusted'||isPriority(i));
  const count=key=>items.filter(i=>i.triage.group===key).length;
  return {...prepared,bundle,pack,items,active_count:active.length,
    groups:{trusted:count('trusted'),exception:count('exception'),exclude:count('exclude')},
    capacity_used:(guard.active_pending||0)+active.length,
    counts:{...prepared.counts,candidate_review_count:prepared.candidates.length}};
}
export function continuationReport(snapshot,prepared,guard=continuationGuard()){
  const report=targetedReport(snapshot,prepared);
  return {...report,campaign:CONTINUATION,approved_preserved:guard.counts.approved,historical_preserved:guard.counts.historical,
    continuation:{execution_enabled:true,parent_attempts:snapshot.parent.attempts.length,attempts_spent:snapshot.attempts.length,attempts_remaining:48-snapshot.attempts.length,
      lifetime_attempt_limit:48,per_execution_attempt_limit:12,active_review_limit:300,active_review_used:prepared.capacity_used,
      parent_snapshot_sha256:sha256(stable(snapshot.parent)),preserved_pending:guard.counts.pending_recovery,
      new_pending:prepared.candidates.length,groups:prepared.groups,automatic_accepts:0,
      policy:'300 active credible/priority review slots, with page-size headroom; all other observations retained pending in full review bundle and audit. Suggestions never erase records or decisions.'},
    source_leads:CONTINUATION_SOURCES.map(l=>({...l,matched_pending:prepared.items.filter(i=>matchingSources(i.row).some(m=>m.id===l.id)).map(i=>i.row.amap_poi_id),confirmed_offices:0})),
    limitations:[...report.limitations,'Parent and child together may use only 48 attempts. All 183 offices and 480 locked decisions remain outside acquisition mutation.','Six supplemental source searches do not establish tenant completeness or current office occupancy.']};
}
export async function acquireContinuation({parent,previous=null,areas,guard=continuationGuard(),originalGuard=baseline(),...options}){
  const initial=previous?validateContinuation(previous,areas,guard,originalGuard):startContinuation(parent,areas,guard,originalGuard);
  const result=await acquirePlan({...options,previous:initial,policy:CONTINUATION_POLICY,plan:initial.plan,
    validate:s=>validateContinuation(s,areas,guard,originalGuard),
    // Reserve an entire page of headroom: even 25 new credible records cannot
    // overrun the 300-slot active review bound. No per-run capacity reset.
    prepare:s=>{const p=prepareContinuation(s,areas,guard);return {candidates:Array(p.capacity_used>275?300:p.capacity_used)};},resumable:true});
  validateContinuation(result.snapshot,areas,guard,originalGuard);
  return {snapshot:result.snapshot,...prepareContinuation(result.snapshot,areas,guard),execution:result.execution};
}
