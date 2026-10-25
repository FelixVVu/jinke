// Trusted offline import: rebuild source rows; suggestions never authorize records.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {stable,sha256} from '../common.mjs';
import {loadApproved} from '../amap/pilot3-workflow.mjs';
import {writeReviewBundle} from '../amap/console.mjs';
import {mergeReviewedPilots} from '../amap/merge-reviewed.mjs';
import {ingest,artifactNames,validateArtifacts} from '../ingest.mjs';
import {validateTargeted,prepareTargeted,targetedBundle} from './targeted.mjs';
import {recoverCandidates,recoveryBundle} from './recover.mjs';
import {attachReviewHistory} from '../../../web/src/company-access/review-history.js';
import {appendPending} from '../../../web/src/company-access/review-append.js';
import {createSession,validateSession} from '../../../web/src/company-access/review-state.js';
import {validateSecondPass} from '../../../web/src/company-access/review-triage.js';
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
export function importTargeted({snapshot,areas,baseline,history,recovery,session}){
  validateTargeted(snapshot,areas);
  const prepared=prepareTargeted(snapshot,areas),incoming=targetedBundle(snapshot,prepared),current=attachReviewHistory(recovery,history);
  const combined=appendPending(current,incoming,history,createSession(current)).bundle;validateSession(combined,session);
  if(!session.reviewer.trim())throw Error('Human reviewer required');
  // This importer owns only the targeted batch; never silently discard edits elsewhere.
  for(const b of combined.batches)if(b.id!==incoming.batches[0].id)for(const i of b.rows)if(session.decisions[i.key].history.length)throw Error('OTHER_BATCH_CHANGED: use a separately validated import');
  const records=[],decisions=[];
  for(const c of prepared.candidates){const d=session.decisions[`${incoming.batches[0].id}:${c.amap_poi_id}`];
    if(d.status==='pending')continue;
    const event=d.history.at(-1);if(!event)throw Error('Missing human decision history');
    decisions.push({amap_poi_id:c.amap_poi_id,decision:d.status,notes:d.notes,reviewer:event.reviewer,reviewed_at:event.at,query_ids:c.query_ids,raw_sha256:sha256(stable(c.raw))});
    if(d.status==='accept')records.push({...c.raw,source_evidence:{...c.raw.source_evidence,reviewed:true,description:`Human-reviewed mapped office. Reviewer: ${event.reviewer}. Notes: ${d.notes}`}});
  }
  const envelope={schema_version:1,dataset_kind:'candidate',dataset_version:`targeted-reviewed-${sha256(stable(session)).slice(0,16)}`,records},artifacts=ingest(envelope,areas);
  if(artifacts.rejected.records.length)throw Error('CANONICAL_VALIDATION_FAILED: '+stable(artifacts.rejected.records));
  const merged=mergeReviewedPilots(baseline,{envelope,artifacts,decisions},areas);validateArtifacts(merged.artifacts,areas);
  const index=new Map(merged.artifacts.offices.features.map(f=>[f.id,f]));
  if(baseline.artifacts.offices.features.some(f=>stable(index.get(f.id))!==stable(f)))throw Error('BASELINE_CHANGED');
  if(merged.artifacts.rejected.records.length)throw Error('MERGED_VALIDATION_FAILED');
  return {...merged,incoming,decided:decisions,report:{human_accepts:records.length,canonical_offices:merged.artifacts.offices.features.length,dispositions:merged.artifacts.metadata.ingestion.dispositions,session_sha256:sha256(stable(session)),snapshot_sha256:sha256(stable(snapshot))}};
}
export async function importFiles(base,artifact,recoveryRoot,sessionFile,output,triageRoot){
  const areas=await read('web/public/data/reach-areas.geojson'),baseline=await loadApproved(base),session=await read(sessionFile),snapshot=await read(path.join(artifact,'provider-cache/snapshot.json'));
  const snapshots=await Promise.all([1,2,3].map(n=>read(path.join(base,`source-imports/pilot-${n}/provider-cache/snapshot.json`))));
  const recovery=recoveryBundle(recoverCandidates({snapshots,areas,priorDecisions:baseline.decisions}),baseline.artifacts.offices.features.map(f=>f.properties));
  const temp=await fs.mkdtemp(path.join(path.dirname(output),'.targeted-validation-'));
  let result,history;try{history=await writeReviewBundle(base,path.join(temp,'history.json'));result=importTargeted({snapshot,areas,baseline,history,recovery,session});}finally{await fs.rm(temp,{recursive:true,force:true});}
  // All validation precedes creation of the release directory.
  await fs.mkdir(output);for(const folder of ['frontend','audit','approved','source-imports','review-pending','review-targeted'])await fs.mkdir(path.join(output,folder));
  const write=(name,value)=>fs.writeFile(path.join(output,name),stable(value)+'\n',{flag:'wx'});
  for(const [key,name]of Object.entries(artifactNames))await write(path.join(['audit','rejected','review'].includes(key)?'audit':'frontend',name),result.artifacts[key]);
  await write('approved/raw-input.json',result.envelope);await write('audit/human-review.json',{decisions:result.decisions});await write('audit/targeted-import-report.json',result.report);await fs.copyFile(sessionFile,path.join(output,'audit/human-session.json'));
  await fs.cp(path.join(base,'source-imports'),path.join(output,'source-imports'),{recursive:true});
  const digest=sha256(stable(session)).slice(0,16),historyBatch=structuredClone(result.incoming),decidedIDs=new Set(result.decided.map(d=>d.amap_poi_id));
  historyBatch.batches=historyBatch.batches.map(b=>({...b,id:`imported-${digest}`,rows:b.rows.filter(i=>decidedIDs.has(i.row.amap_poi_id)).map(i=>({...i,key:`imported-${digest}:${i.row.amap_poi_id}`}))}));
  const folder=`source-imports/coverage-${digest}`;await fs.mkdir(path.join(output,folder));await write(folder+'/recovery-bundle.json',historyBatch);await write(folder+'/snapshot.json',snapshot);
  const newHistory=await writeReviewBundle(output,path.join(output,'audit/review-history.json'));
  await fs.cp(recoveryRoot,path.join(output,'review-pending'),{recursive:true});
  const oldPack=await read(path.join(recoveryRoot,'second-pass.json'));oldPack.bundle_id=attachReviewHistory(recovery,newHistory).bundle_id;await fs.writeFile(path.join(output,'review-pending/second-pass.json'),stable(oldPack)+'\n');
  const pending=structuredClone(result.incoming);for(const b of pending.batches)b.rows=b.rows.filter(i=>!decidedIDs.has(i.row.amap_poi_id));pending.bundle_id=sha256(stable(pending.batches));
  await write('review-targeted/targeted-review-bundle.json',pending);
  const pack=await read(path.join(triageRoot,'targeted-second-pass.json'));validateSecondPass(result.incoming,pack);
  pack.bundle_id=pending.bundle_id;pack.seeds=pack.seeds.filter(s=>!decidedIDs.has(s.poi_id));pack.evidence=pack.evidence.filter(e=>!decidedIDs.has(e.poi_id));validateSecondPass(pending,pack);
  await write('review-targeted/targeted-second-pass.json',pack);
  const report=await read(path.join(triageRoot,'targeted-readiness.json'));report.review_import=result.report;
  await write('review-targeted/targeted-readiness.json',report);
  return result.report;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){const [base,artifact,recovery,session,output,triageRoot]=process.argv.slice(2);if(!triageRoot||!output||path.dirname(path.resolve(output))!==path.resolve('offline-output/company-access'))throw Error('Fresh offline output and triage root required');console.log(stable(await importFiles(base,artifact,recovery,session,output,triageRoot)));}
