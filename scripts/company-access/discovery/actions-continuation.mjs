// Offline Actions runner. Reuses the shared transport and bounded executor.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {requireManualReviewRun,assertKeyFree} from '../amap/actions-pilot.mjs';
import {reviewRows,toCSV} from '../amap/review.mjs';
import {baseline} from './targeted-plan.mjs';
import {stable,fail} from '../common.mjs';
import {CONTINUATION,validateContinuation,acquireContinuation,continuationReport,continuationGuard} from './continuation.mjs';
export const CONTINUATION_FILES=['review/review-bundle.json','review/second-pass.json','review/amap-office-review.json','review/amap-office-review.csv','normalized/candidates.json','audit/acquisition-report.json','audit/query-coverage.geojson','audit/exclusions.json','audit/triage.json','provider-cache/snapshot.json'];
export async function executeContinuation({key,context,previous,root='offline-output/company-access',dependencies={},signal=async()=>{},guard=continuationGuard(),originalGuard=baseline()}){
  requireManualReviewRun(context);if(typeof key!=='string'||!key.trim())fail('AMAP_NOT_CONFIGURED');
  const areas=JSON.parse(await fs.readFile('web/public/data/reach-areas.geojson','utf8'));
  validateContinuation(previous,areas,guard,originalGuard); // Never start from empty or a user-supplied plan.
  const dir=path.join(root,`${CONTINUATION}-checkpoint`),file=path.join(dir,'provider-cache/snapshot.json');
  await fs.mkdir(root,{recursive:true});await fs.mkdir(dir);await fs.mkdir(path.dirname(file));
  const checkpoint=async snapshot=>{const bytes=stable(snapshot)+'\n';assertKeyFree(bytes,key);await fs.writeFile(file+'.next',bytes,{mode:0o600});await fs.rename(file+'.next',file);};
  await checkpoint(previous);await signal('checkpoint_ready');
  const result=await acquireContinuation({env:{JINKE_AMAP_KEY:key},areas,previous,guard,originalGuard,...dependencies,checkpoint,assertSafe:p=>assertKeyFree(stable(p),key)});
  const report=continuationReport(result.snapshot,result,guard),bundle={...result.bundle,coverage:report.coverage,discovery_report:report,second_pass:result.pack};
  const rows=reviewRows(result.candidates);if(rows.some(r=>r.review_status!=='pending'))fail('PENDING_ONLY');
  const values={'review/review-bundle.json':bundle,'review/second-pass.json':result.pack,'review/amap-office-review.json':rows,'review/amap-office-review.csv':toCSV(rows),
    'normalized/candidates.json':result.candidates,'audit/acquisition-report.json':report,'audit/query-coverage.geojson':report.coverage,'audit/exclusions.json':result.exclusions,
    'audit/triage.json':result.items.map(i=>({poi_id:i.row.amap_poi_id,triage:i.triage,decision:'pending'})),'provider-cache/snapshot.json':result.snapshot};
  const files=CONTINUATION_FILES.map(name=>{const bytes=typeof values[name]==='string'?values[name]:stable(values[name])+'\n';assertKeyFree(bytes,key);return [name,bytes];});
  const artifact=path.join(root,`${CONTINUATION}-artifact`);await fs.mkdir(artifact);
  for(const [name,bytes]of files){await fs.mkdir(path.dirname(path.join(artifact,name)),{recursive:true});await fs.writeFile(path.join(artifact,name),bytes,{flag:'wx',mode:0o600});}
  await signal('artifact_ready');return {report,artifact};
}
async function main(){
  if(process.argv.length!==2)fail('NO_PILOT_ARGUMENTS_ALLOWED');
  const previous=JSON.parse(await fs.readFile(`offline-output/company-access/${CONTINUATION}-resume.json`,'utf8'));
  const {report:r}=await executeContinuation({key:process.env.JINKE_AMAP_KEY,context:process.env,previous,signal:async name=>{if(process.env.GITHUB_OUTPUT)await fs.appendFile(process.env.GITHUB_OUTPUT,`${name}=true\n`);}});
  const summary=`## Targeted continuation — identified office candidates\n\nRequests this execution: ${r.api_requests_this_execution}/12; lifetime: ${r.api_requests_total}/48 (includes original 19).\n\nNew pending including cached overflow: ${r.continuation.new_pending}; credible: ${r.continuation.groups.trusted}; exceptions: ${r.continuation.groups.exception}; suggested exclusion: ${r.continuation.groups.exclude}. No automatic decisions.\n\nStop: ${r.stop_reason}. Remaining lifetime attempts: ${r.continuation.attempts_remaining}.\n\nDownload company-access-${CONTINUATION}-${process.env.GITHUB_RUN_ID}. In the existing Review Console open review/review-bundle.json using Append pending candidates; second-pass metadata is included. No CSV required. Preserve the artifact for validated import.\n\nIf EXECUTION_BUDGET, a fresh manual dispatch on the same branch resumes safely. Never Re-run jobs or rerun Pilot 3.\n`;
  assertKeyFree(summary,process.env.JINKE_AMAP_KEY);if(process.env.GITHUB_STEP_SUMMARY)await fs.appendFile(process.env.GITHUB_STEP_SUMMARY,summary);
  if(!['PLAN_COMPLETE','PLAN_COMPLETE_WITH_GAPS','CANDIDATE_CAP','REQUEST_BUDGET','EXECUTION_BUDGET'].includes(r.stop_reason))process.exitCode=1;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)main().catch(()=>{console.error('CONTINUATION_STOPPED: inspect key-free checkpoint/report. Credentials and provider error bodies are not logged.');process.exitCode=1;});
