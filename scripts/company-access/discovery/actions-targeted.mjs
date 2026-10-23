// Review-branch Actions only. No browser endpoint, deployment or arbitrary inputs.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {requireManualReviewRun,assertKeyFree} from '../amap/actions-pilot.mjs';
import {toCSV,reviewRows} from '../amap/review.mjs';
import {stable,fail} from '../common.mjs';
import {targetedPlan,TARGETED_POLICY,CAMPAIGN} from './targeted-plan.mjs';
import {TARGETED_LEADS} from './targeted-leads.mjs';
import {acquireTargeted,validateTargeted,targetedBundle,targetedReport} from './targeted.mjs';
export const SAFE_FILES=Object.freeze(['review/amap-office-review.csv','review/amap-office-review.json','review/review-bundle.json','normalized/candidates.json','audit/acquisition-report.json','audit/query-coverage.geojson','audit/acquisition-exclusions.json','audit/source-leads.json','provider-cache/snapshot.json']);
export async function executeTargeted({key,context,root='offline-output/company-access',collectedAt=new Date().toISOString(),previous=null,dependencies={},signal=async()=>{}}){
  requireManualReviewRun(context);if(typeof key!=='string'||!key.trim())fail('AMAP_NOT_CONFIGURED');
  const areas=JSON.parse(await fs.readFile('web/public/data/reach-areas.geojson','utf8'));
  const initial=previous?validateTargeted(previous,areas):{version:TARGETED_POLICY.version,collected_at:collectedAt,plan:targetedPlan(areas),responses:[],attempts:[]};
  await fs.mkdir(root,{recursive:true});
  const checkpointRoot=path.join(root,`${CAMPAIGN}-checkpoint`),checkpointFile=path.join(checkpointRoot,'provider-cache/snapshot.json');
  await fs.mkdir(checkpointRoot);await fs.mkdir(path.dirname(checkpointFile));
  const checkpoint=async snapshot=>{const bytes=stable(snapshot)+'\n';assertKeyFree(bytes,key);await fs.writeFile(checkpointFile+'.next',bytes,{mode:0o600});await fs.rename(checkpointFile+'.next',checkpointFile);};
  // Upload this reservation-safe checkpoint even if later preparation fails.
  await checkpoint(initial);await signal('checkpoint_ready');
  const result=await acquireTargeted({env:{JINKE_AMAP_KEY:key},areas,collectedAt,previous:initial,...dependencies,checkpoint,assertSafe:payload=>assertKeyFree(stable(payload),key)});
  validateTargeted(result.snapshot,areas);
  const report=targetedReport(result.snapshot,result),bundle={...targetedBundle(result.snapshot,result),coverage:report.coverage,discovery_report:report};
  const rows=reviewRows(result.candidates);
  if(rows.some(r=>r.review_status!=='pending'))fail('REVIEW_MUST_BE_PENDING');
  const values={'review/amap-office-review.csv':toCSV(rows),'review/amap-office-review.json':rows,'review/review-bundle.json':bundle,
    'normalized/candidates.json':result.candidates,'audit/acquisition-report.json':report,'audit/query-coverage.geojson':report.coverage,
    'audit/acquisition-exclusions.json':result.exclusions,'audit/source-leads.json':TARGETED_LEADS,'provider-cache/snapshot.json':result.snapshot};
  const files=SAFE_FILES.map(name=>{const bytes=typeof values[name]==='string'?values[name]:stable(values[name])+'\n';assertKeyFree(bytes,key);return [name,bytes];});
  const artifact=path.join(root,`${CAMPAIGN}-artifact`);await fs.mkdir(artifact);
  for(const [name,bytes]of files){await fs.mkdir(path.dirname(path.join(artifact,name)),{recursive:true});await fs.writeFile(path.join(artifact,name),bytes,{flag:'wx',mode:0o600});}
  await signal('artifact_ready');return {report,artifact};
}
async function main(){
  if(process.argv.length!==2)fail('NO_PILOT_ARGUMENTS_ALLOWED');
  let previous=null;try{previous=JSON.parse(await fs.readFile(`offline-output/company-access/${CAMPAIGN}-resume.json`,'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
  const {report}=await executeTargeted({key:process.env.JINKE_AMAP_KEY,context:process.env,previous,signal:async name=>{
    if(process.env.GITHUB_OUTPUT)await fs.appendFile(process.env.GITHUB_OUTPUT,`${name}=true\n`);
  }});
  const summary=`## Targeted 30-minute discovery — identified office candidates\n\nAttempts this run / lifetime: ${report.api_requests_this_execution} / ${report.api_requests_total} (maximum 24 / 48)\n\nRaw POIs: ${report.raw_poi_results}; unique IDs: ${report.unique_amap_ids}; NEW pending: ${report.candidate_review_count}\n\nKnown IDs preserved: ${report.known_ids_preserved}; known-ID conflicts held: ${report.known_id_conflicts}\n\nStop: ${report.stop_reason}\n\nDownload company-access-${CAMPAIGN}-${process.env.GITHUB_RUN_ID}; review/review-bundle.json opens in the existing Review Console. No approvals or deployments occurred. If EXECUTION_BUDGET, start a fresh manual dispatch on the same branch; never Re-run jobs.\n`;
  assertKeyFree(summary,process.env.JINKE_AMAP_KEY);if(process.env.GITHUB_STEP_SUMMARY)await fs.appendFile(process.env.GITHUB_STEP_SUMMARY,summary);
  if(!['PLAN_COMPLETE','PLAN_COMPLETE_WITH_GAPS','CANDIDATE_CAP','REQUEST_BUDGET','EXECUTION_BUDGET'].includes(report.stop_reason))process.exitCode=1;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)main().catch(()=>{console.error('TARGETED_ACQUISITION_STOPPED: inspect the safe checkpoint/report. No credentials or provider error body logged.');process.exitCode=1;});
