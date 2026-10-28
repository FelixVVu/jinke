// Offline human-review import. Acquisition and automatic suggestions never authorize offices.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {stable,sha256} from '../common.mjs';
import {ingest,artifactNames,validateArtifacts} from '../ingest.mjs';
import {loadApproved} from '../amap/pilot3-workflow.mjs';
import {mergeReviewedPilots} from '../amap/merge-reviewed.mjs';
import {writeReviewBundle} from '../amap/console.mjs';
import {validateContinuation,prepareContinuation} from './continuation.mjs';
import {finalReview} from './final-review.mjs';
import {prepareTargeted,targetedBundle} from './targeted.mjs';
import {recoverCandidates,recoveryBundle} from './recover.mjs';
import {attachReviewHistory} from '../../../web/src/company-access/review-history.js';
import {appendPending,appendDiscovery} from '../../../web/src/company-access/review-append.js';
import {createSession,validateSession} from '../../../web/src/company-access/review-state.js';
import {validateSecondPass} from '../../../web/src/company-access/review-triage.js';
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const equal=(a,b,message)=>{if(stable(a)!==stable(b))throw Error(message);};

// Called only with source-rebuilt candidates/bundle by the file entry point.
export function importReviewedBatch({baseline,areas,combined,incoming,candidates,session}){
  validateSession(combined,session);
  if(!session.reviewer.trim())throw Error('Human reviewer required');
  const initial=createSession(combined),batch=incoming.batches[0];
  const incomingKeys=new Set(batch.rows.map(i=>i.key));
  for(const [key,decision] of Object.entries(initial.decisions))if(!incomingKeys.has(key))equal(session.decisions[key],decision,'OTHER_BATCH_CHANGED');
  const priorIDs=new Set(baseline.decisions.map(d=>d.amap_poi_id));
  const records=[],decisions=[],events=[];
  equal(candidates.map(c=>c.amap_poi_id),batch.rows.map(i=>i.row.amap_poi_id),'SOURCE_CANDIDATE_MISMATCH');
  for(const c of candidates){
    if(priorIDs.has(c.amap_poi_id))throw Error('EXISTING_DECISION_LOCKED');
    const key=`${batch.id}:${c.amap_poi_id}`,d=session.decisions[key];
    if(d.status==='pending')continue;
    const event=d.history.at(-1);if(!event)throw Error('Missing human decision history');
    decisions.push({amap_poi_id:c.amap_poi_id,decision:d.status,notes:d.notes,reviewer:event.reviewer,reviewed_at:event.at,query_ids:c.query_ids,raw_sha256:sha256(stable(c.raw))});
    events.push({key,amap_poi_id:c.amap_poi_id,decision:structuredClone(d)});
    if(d.status==='accept'){
      if(c.raw.source_evidence.kind!=='map_poi'||c.raw.source_evidence.reviewed!==false)throw Error('UNEXPECTED_SOURCE_EVIDENCE');
      records.push({...c.raw,source_evidence:{...c.raw.source_evidence,reviewed:true,description:`Human-reviewed mapped office. Reviewer: ${event.reviewer}. Notes: ${d.notes}`}});
    }
  }
  const envelope={schema_version:1,dataset_kind:'candidate',dataset_version:`continuation-reviewed-${sha256(stable(session)).slice(0,16)}`,records};
  const artifacts=ingest(envelope,areas);
  if(artifacts.rejected.records.length)throw Error('CANONICAL_VALIDATION_FAILED: '+stable(artifacts.rejected.records));
  if(artifacts.offices.features.some(f=>!f.properties.reach_minutes.includes(30)))throw Error('ACCEPT_OUTSIDE_30_MINUTES');
  const merged=mergeReviewedPilots(baseline,{envelope,artifacts,decisions},areas);validateArtifacts(merged.artifacts,areas);
  if(merged.held.length||merged.artifacts.rejected.records.length)throw Error('MERGED_VALIDATION_FAILED');
  const offices=new Map(merged.artifacts.offices.features.map(f=>[f.id,f]));
  for(const f of baseline.artifacts.offices.features)equal(offices.get(f.id),f,'BASELINE_CHANGED');
  equal(merged.decisions.slice(0,baseline.decisions.length),baseline.decisions,'HISTORICAL_DECISION_CHANGED');
  const dispositions=Object.fromEntries(['accept','reject','needs_review','pending'].map(s=>[s,batch.rows.filter(i=>session.decisions[i.key].status===s).length]));
  return {...merged,decided:decisions,events,report:{human_accepts:records.length,prior_offices:baseline.artifacts.offices.features.length,canonical_offices:offices.size,net_new_offices:offices.size-baseline.artifacts.offices.features.length,review_dispositions:dispositions,new_dispositions:artifacts.metadata.ingestion.dispositions,merged_dispositions:merged.artifacts.metadata.ingestion.dispositions,duplicates_collapsed:merged.artifacts.review.duplicates.length-baseline.artifacts.review.duplicates.length,historical_decisions:merged.decisions.length,session_sha256:sha256(stable(session))}};
}

export async function importContinuationFiles(base,input,output){
  const areas=await read('web/public/data/reach-areas.geojson'),baseline=await loadApproved(base),session=await read(path.join(input,'review-session.json'));
  const manifest=await read(path.join(input,'validation-manifest.json'));
  for(const name of ['review-session.json','source-acquisition.zip'])if(sha256(await fs.readFile(path.join(input,name)))!==manifest.sha256[name])throw Error('HANDOFF_HASH_MISMATCH');
  if(manifest.project!=='FelixVVu/jinke'||manifest.pr!==20||manifest.branch!=='review/company-access-scaffold')throw Error('WRONG_HANDOFF');
  const source=path.join(input,'source'),snapshot=await read(path.join(source,'provider-cache/snapshot.json'));
  validateContinuation(snapshot,areas);const prepared=prepareContinuation(snapshot,areas),final=finalReview(snapshot,areas);
  equal(prepared.candidates,await read(path.join(source,'normalized/candidates.json')),'SOURCE_CANDIDATE_MISMATCH');
  equal(prepared.bundle.batches,(await read(path.join(source,'review/review-bundle.json'))).batches,'SOURCE_REVIEW_MISMATCH');
  if(manifest.batch_id!==prepared.bundle.batches[0].id||manifest.source_review_bundle_id!==prepared.bundle.bundle_id)throw Error('HANDOFF_BATCH_MISMATCH');
  const recoveryRoot=path.join(base,'review-pending'),targetedRoot=path.join(base,'review-targeted');
  const recovery=await read(path.join(recoveryRoot,'pending-review-bundle.json')),targeted=await read(path.join(targetedRoot,'targeted-review-bundle.json'));
  const snapshots=await Promise.all([1,2,3].map(n=>read(path.join(base,`source-imports/pilot-${n}/provider-cache/snapshot.json`))));
  const rebuiltRecovery=recoveryBundle(recoverCandidates({snapshots,areas,priorDecisions:baseline.decisions}),baseline.artifacts.offices.features.map(f=>f.properties));
  equal(recovery.batches,rebuiltRecovery.batches,'RECOVERY_SOURCE_MISMATCH');
  const rebuiltTarget=targetedBundle(snapshot.parent,prepareTargeted(snapshot.parent,areas)),locked=new Set(baseline.decisions.map(d=>d.amap_poi_id));
  for(const b of rebuiltTarget.batches)b.rows=b.rows.filter(i=>!locked.has(i.row.amap_poi_id));
  equal(targeted.batches,rebuiltTarget.batches,'TARGETED_SOURCE_MISMATCH');
  const temp=await fs.mkdtemp(path.join(path.dirname(output),'.continuation-validation-'));
  let result;
  try{
    const history=await writeReviewBundle(base,path.join(temp,'history.json')),old=attachReviewHistory(recovery,history);
    const previous=appendPending(old,targeted,history,createSession(old));
    const combined=appendDiscovery(previous.bundle,final.bundle,history,previous.session).bundle;
    result=importReviewedBatch({baseline,areas,combined,incoming:final.bundle,candidates:prepared.candidates,session});
    const prior=Object.values(previous.session.decisions),counts=Object.fromEntries(['accept','reject','needs_review','pending'].map(s=>[s,prior.filter(d=>d.status===s).length]));
    equal(counts,manifest.counts.prior,'PRIOR_COUNTS_MISMATCH');
    equal(result.report.review_dispositions,{...manifest.counts.new_batch,pending:0},'REVIEW_COUNTS_MISMATCH');
    if(Object.keys(session.decisions).length!==manifest.counts.review_records_total||prepared.candidates.length!==manifest.counts.new_batch_records)throw Error('HANDOFF_COUNTS_MISMATCH');
    result.report.snapshot_sha256=sha256(stable(snapshot));result.report.earlier_pending_preserved=counts.pending;
  }finally{await fs.rm(temp,{recursive:true,force:true});}
  // No release is created until every human/source/canonical/preservation check passes.
  await fs.mkdir(output);for(const dir of ['frontend','audit','approved','source-imports','review-pending','review-targeted'])await fs.mkdir(path.join(output,dir));
  const write=(name,value)=>fs.writeFile(path.join(output,name),stable(value)+'\n',{flag:'wx'});
  for(const [key,name]of Object.entries(artifactNames))await write(path.join(['audit','rejected','review'].includes(key)?'audit':'frontend',name),result.artifacts[key]);
  await write('approved/raw-input.json',result.envelope);await write('audit/human-review.json',{decisions:result.decisions});
  await write('audit/continuation-import-report.json',result.report);await write('audit/continuation-decision-events.json',result.events);
  await write('audit/second-pass-evidence.json',final.pack);await fs.copyFile(path.join(input,'review-session.json'),path.join(output,'audit/human-session.json'));
  await fs.copyFile(path.join(input,'validation-manifest.json'),path.join(output,'audit/handoff-manifest.json'));
  await fs.cp(path.join(base,'source-imports'),path.join(output,'source-imports'),{recursive:true});
  // All 241 decisions, including reject/needs_review, are retained and locked.
  const digest=sha256(stable(session)).slice(0,16),saved=structuredClone(prepared.bundle),folder=`source-imports/coverage-${digest}`;
  for(const b of saved.batches){b.id=`imported-${digest}`;for(const i of b.rows)i.key=`${b.id}:${i.row.amap_poi_id}`;}
  saved.bundle_id=sha256(stable(saved.batches));await fs.mkdir(path.join(output,folder));
  await write(folder+'/recovery-bundle.json',saved);await write(folder+'/snapshot.json',snapshot);
  const history=await writeReviewBundle(output,path.join(output,'audit/review-history.json'));
  await fs.cp(recoveryRoot,path.join(output,'review-pending'),{recursive:true});await fs.cp(targetedRoot,path.join(output,'review-targeted'),{recursive:true});
  const pack=await read(path.join(recoveryRoot,'second-pass.json'));pack.bundle_id=attachReviewHistory(recovery,history).bundle_id;
  validateSecondPass(attachReviewHistory(recovery,history),pack);
  await fs.writeFile(path.join(output,'review-pending/second-pass.json'),stable(pack)+'\n');
  final.report.review_import=result.report;
  await fs.writeFile(path.join(output,'review-targeted/targeted-readiness.json'),stable(final.report)+'\n');
  return result.report;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){
  const [base,input,output]=process.argv.slice(2);
  if(!output||path.dirname(path.resolve(output))!==path.resolve('offline-output/company-access'))throw Error('Fresh offline output required');
  console.log(stable(await importContinuationFiles(base,input,output)));
}
