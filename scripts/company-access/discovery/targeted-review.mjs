// Offline, key-free analysis. Does not acquire, accept, or mutate a checkpoint.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {stable,sha256} from '../common.mjs';
import {validateTargeted,prepareTargeted,targetedBundle,targetedReport} from './targeted.mjs';
import {TRIAGE_VERSION,triageItems,validateSecondPass} from '../../../web/src/company-access/review-triage.js';
import {attachReviewHistory} from '../../../web/src/company-access/review-history.js';
import {appendPending} from '../../../web/src/company-access/review-append.js';
import {createSession} from '../../../web/src/company-access/review-state.js';
const count=values=>values.reduce((a,k)=>(a[k]=(a[k]||0)+1,a),{});
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
export function continuationPlan(snapshot,prepared,items){
  const report=targetedReport(snapshot,prepared),byID=new Map(items.map(i=>[i.row.amap_poi_id,i])),cached=new Set(snapshot.responses.map(r=>r.query_id));
  const incomplete=report.streams.filter(s=>s.status==='pagination_incomplete').map(s=>{
    const q=snapshot.plan.queries.find(q=>q.cell_id===s.id&&q.page===Math.max(...s.pages.map(p=>p.page))+1);
    const seen=new Set(snapshot.responses.filter(r=>snapshot.plan.queries.find(q=>q.id===r.query_id)?.cell_id===s.id).flatMap(r=>r.payload.pois.map(p=>p.id)));
    return {stream:s.id,kind:s.region_id?'geographic':'name',query_id:q.id,next_page:q.page,
      observed_unique:seen.size,observed_group_counts:count([...seen].map(id=>byID.get(id)?.triage.group||'held_or_known')),
      condition:'Fetch only after predecessor is full, capacity is resolved, and the parent checkpoint is validated.'};
  }).sort((a,b)=>(a.kind==='geographic'?0:1)-(b.kind==='geographic'?0:1)||a.stream.localeCompare(b.stream));
  if(incomplete.some(q=>cached.has(q.query_id)))throw Error('Continuation would reacquire a cached query');
  return {schema_version:1,planning_only:true,execution_enabled:false,parent_plan_sha256:snapshot.plan.plan_sha256,parent_snapshot_sha256:sha256(stable(snapshot)),
    lifetime_attempt_limit:48,attempts_spent:snapshot.attempts.length,attempts_remaining:48-snapshot.attempts.length,
    original_candidate_cap:300,capacity_gate:'CANDIDATE_CAP: original runner cannot safely resume. Do not reset or rerun. A separately validated capacity policy is required; triage suggestions never delete candidates or release capacity.',
    cached_response_count:snapshot.responses.length,failed_attempts_preserved:snapshot.attempts.filter(a=>a.outcome!=='success'),
    cached_overflow_ids:prepared.exclusions.filter(e=>e.reason==='PILOT_CANDIDATE_CAP').map(e=>e.amap_poi_id),
    next_pages:incomplete,completed_streams_not_requeried:report.streams.filter(s=>s.provider_pagination_exhausted).map(s=>s.id),
    proposed_missing_name_searches:[{name:'AMD',terms:['超威半导体','AMD'],source_url:'https://www.amd.com/en/corporate/locations.html'},{name:'豪威',terms:['豪威科技','豪威半导体'],source_url:'https://www.ovt.com/company/contact-us'}],
    name_search_gate:'Not part of the immutable original plan. Needs a versioned child plan with parent ledger accounting within the same remaining 29 attempts; no independent quota.',
    stop_rules:['Original pacing and retry limits unchanged','Never retry an exhausted query','Stop on broader connectivity loss','No request until capacity and lineage gates pass'],
    coverage_limit:'A short provider page means that query ended, not that the area has no more offices.'};
}
export function analyzeTargeted({snapshot,areas,evidence=[],relations=[],benchmarkFindings=[]}){
  validateTargeted(snapshot,areas);
  const prepared=prepareTargeted(snapshot,areas),bundle=targetedBundle(snapshot,prepared),rows=bundle.batches.flatMap(b=>b.rows);
  const related=new Set(relations.flatMap(r=>r.poi_ids));
  for(const r of relations)if(!r.reason||r.poi_ids.length<2||r.poi_ids.some(id=>!rows.some(i=>i.row.amap_poi_id===id)))throw Error('Invalid relationship review annotation');
  const pack={schema_version:1,version:TRIAGE_VERSION,bundle_id:bundle.bundle_id,evidence,seeds:rows.map(i=>({poi_id:i.row.amap_poi_id,company_name:i.row.company_name,address:i.row.address,decision:'pending',flags:['TARGETED_PRECISION_V1',...(related.has(i.row.amap_poi_id)?['POSSIBLE_SHARED_OFFICE']:[])]}))};
  validateSecondPass(bundle,pack);const items=triageItems(rows,pack.evidence,pack.seeds),report=targetedReport(snapshot,prepared);
  report.triage={groups:count(items.map(i=>i.triage.group)),reasons:count(items.map(i=>i.triage.reason)),public_evidence_count:evidence.length,analyzed:rows.length,automatic_accepts:0,confidence_upgrade_count:0};
  report.benchmark_findings=benchmarkFindings;report.continuation=continuationPlan(snapshot,prepared,items);
  report.candidate_analysis=items.map(i=>({poi_id:i.row.amap_poi_id,name:i.row.company_name,address:i.row.address,typecode:i.row.amap_typecode,group:i.triage.group,reason:i.triage.reason,tier:i.triage.tier,decision:'pending',evidence:i.triage.public_evidence}));
  report.relationship_reviews=relations;
  return {bundle:{...bundle,coverage:report.coverage,discovery_report:report},pack,report};
}
export async function buildTargetedReview(input,recoveryRoot,annotations,readinessPath,output){
  const snapshot=await read(path.join(input,'provider-cache/snapshot.json')),areas=await read('web/public/data/reach-areas.geojson');
  const result=analyzeTargeted({snapshot,areas,...await read(annotations)});
  const artifact=await read(path.join(input,'review/review-bundle.json'));
  if(stable(artifact.batches)!==stable(result.bundle.batches)||artifact.bundle_id!==result.bundle.bundle_id)throw Error('Artifact review assertions differ from validated snapshot');
  if(stable(await read(path.join(input,'normalized/candidates.json')))!==stable(prepareTargeted(snapshot,areas).candidates))throw Error('Artifact normalized candidates differ');
  const history=await read(path.join(recoveryRoot,'history-bundle.json')),old=attachReviewHistory(await read(path.join(recoveryRoot,'pending-review-bundle.json')),history),oldPack=await read(path.join(recoveryRoot,'second-pass.json'));
  const appended=appendPending(old,result.bundle,history,createSession(old),oldPack);
  const ids=new Set(result.pack.seeds.map(s=>s.poi_id));
  const combinedPack={...appended.pack,evidence:[...appended.pack.evidence,...result.pack.evidence],seeds:[...appended.pack.seeds.filter(s=>!ids.has(s.poi_id)),...result.pack.seeds]};
  validateSecondPass(appended.bundle,combinedPack);
  const readiness=await read(readinessPath);
  for(const key of ['baseline_regions','previous_benchmark','previous_summary','priority_footprint','inputs'])result.report[key]=readiness[key];
  result.bundle.discovery_report=result.report;
  const manifests={snapshot_sha256:sha256(stable(snapshot)),recovery_sha256:sha256(stable(old)),historical_sha256:sha256(stable(history)),combined_bundle_id:appended.bundle.bundle_id,
    counts:{new_pending:result.pack.seeds.length,preserved_pending:oldPack.seeds.length,historical:history.batches.flatMap(b=>b.rows).length},new_decisions:'pending',automatic_accepts:0};
  await fs.mkdir(output);
  for(const [name,value]of Object.entries({'targeted-review-bundle.json':result.bundle,'targeted-second-pass.json':result.pack,'targeted-readiness.json':result.report,'continuation-plan.json':result.report.continuation,'combined-review-bundle.json':appended.bundle,'combined-second-pass.json':combinedPack,'verification.json':manifests}))await fs.writeFile(path.join(output,name),stable(value)+'\n',{flag:'wx'});
  return {counts:manifests.counts,triage:result.report.triage,remaining_attempts:result.report.continuation.attempts_remaining};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){
  const [input,recovery,annotations,readiness,output]=process.argv.slice(2);
  if(!output||path.dirname(path.resolve(output))!==path.resolve('offline-output/company-access'))throw Error('Usage: targeted-review.mjs ARTIFACT_DIR RECOVERY_DIR ANNOTATIONS_JSON READINESS_JSON FRESH_OFFLINE_DIR');
  console.log(stable(await buildTargetedReview(input,recovery,annotations,readiness,output)));
}
