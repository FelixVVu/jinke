// Manual PR #20 Actions adapter. Acquisition policy stays in the existing job.
import { readFile, writeFile, mkdir, rename, lstat, appendFile } from 'node:fs/promises';
import { resolve, dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { runCompanyAccessPilot } from '../../../hosting/server/company-access-job.mjs';
import { prepareFiles } from './files.mjs';
import { stable, fail } from '../common.mjs';
const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../../..');
export const ARTIFACT_FILES=Object.freeze([
  'review/amap-office-review.csv','review/amap-office-review.json',
  'normalized/candidates.json','normalized/raw-input.json',
  'audit/pilot-report.json','audit/pilot-report.md','audit/acquisition-exclusions.json',
  'provider-cache/snapshot.json',
]);
export function requireManualReviewRun(context){
  if(context.GITHUB_ACTIONS!=='true'||context.GITHUB_EVENT_NAME!=='workflow_dispatch'||
    context.GITHUB_REPOSITORY!=='FelixVVu/jinke'||context.GITHUB_REF!=='refs/heads/review/company-access-scaffold'||
    context.GITHUB_RUN_ATTEMPT!=='1')fail('MANUAL_REVIEW_BRANCH_ONLY');
}
export function assertKeyFree(bytes,key){
  const content=Buffer.isBuffer(bytes)?bytes.toString('utf8'):String(bytes);
  const forbidden=[key,encodeURIComponent(key),JSON.stringify(key).slice(1,-1),Buffer.from(key).toString('base64')];
  if(!key||forbidden.some(value=>value&&content.includes(value)))fail('UNSAFE_ARTIFACT');
}
export async function stageArtifact({source,target,key}){
  const safe=[];
  // Validate all files before creating anything in the upload directory.
  for(const path of ARTIFACT_FILES){
    const file=join(source,path);
    if(!(await lstat(file)).isFile()||(await lstat(dirname(file))).isSymbolicLink())fail('UNSAFE_ARTIFACT');
    const bytes=await readFile(file);assertKeyFree(bytes,key);safe.push([path,bytes]);
  }
  const rows=JSON.parse(safe.find(([p])=>p==='review/amap-office-review.json')[1]);
  if(!Array.isArray(rows)||rows.some(r=>r.review_status!=='pending'))fail('REVIEW_MUST_BE_PENDING');
  await mkdir(target); // fresh directory only
  for(const [path,bytes] of safe){await mkdir(dirname(join(target,path)),{recursive:true});await writeFile(join(target,path),bytes,{flag:'wx',mode:0o600});}
}
export async function executePilot({key,context,collectedAt=new Date().toISOString(),dependencies={}}){
  requireManualReviewRun(context);
  if(typeof key!=='string'||!key.trim())fail('AMAP_NOT_CONFIGURED');
  const root=join(repo,'offline-output/company-access');
  await mkdir(root,{recursive:true});
  const checkpointDir=join(root,'pilot-1-checkpoint');await mkdir(checkpointDir);
  const snapshotPath=join(checkpointDir,'snapshot.json');
  const areas=JSON.parse(await readFile(join(repo,'web/public/data/reach-areas.geojson'),'utf8'));
  const result=await runCompanyAccessPilot({JINKE_AMAP_KEY:key},{reachAreas:areas,collectedAt,checkpoint:async snapshot=>{
    const bytes=stable(snapshot)+'\n';assertKeyFree(bytes,key);
    const temporary=join(checkpointDir,'snapshot.next');await writeFile(temporary,bytes,{mode:0o600});await rename(temporary,snapshotPath);
  }},dependencies);
  const output=join(root,'pilot-1');
  await prepareFiles({snapshotPath,output});
  const artifact=join(root,'pilot-1-artifact');await stageArtifact({source:output,target:artifact,key});
  const report=JSON.parse(await readFile(join(output,'audit/pilot-report.json'),'utf8'));
  return {report,artifact,providerStopped:!['PLAN_COMPLETE','CANDIDATE_CAP','REQUEST_BUDGET'].includes(result.execution.stop_reason)};
}
async function main(){
  if(process.argv.length!==2)fail('NO_PILOT_ARGUMENTS_ALLOWED');
  // Pass a narrow binding object; never serialize process.env or log provider data.
  const result=await executePilot({key:process.env.JINKE_AMAP_KEY,context:process.env});
  if(process.env.GITHUB_OUTPUT)await appendFile(process.env.GITHUB_OUTPUT,'artifact_ready=true\n');
  // Numeric summary only. Full key-scanned QA lives inside the downloadable artifact.
  const r=result.report;
  const summary=`Identified office candidates (source-dependent coverage)\n\nAPI attempts: ${r.api_requests_total}\nCached requests: ${r.cached_requests_this_execution}\nRaw POIs: ${r.raw_poi_results}\nUnique provider IDs: ${r.unique_amap_ids}\nPending review candidates: ${r.candidate_review_count}\nStop reason: ${r.stop_reason}\n`;
  assertKeyFree(summary,process.env.JINKE_AMAP_KEY);
  if(process.env.GITHUB_STEP_SUMMARY)await appendFile(process.env.GITHUB_STEP_SUMMARY,summary);
  if(result.providerStopped)process.exitCode=1;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)main().catch(()=>{console.error('PILOT_FAILED: check secret configuration, manual branch context, or safe artifact validation. No credentials or provider error bodies are logged.');process.exitCode=1;});
