// Fixed Pilot 3 runner. Resume artifact is obtained by the separate GitHub-only step.
import fs from 'node:fs/promises';
import {executePilot,assertKeyFree} from './actions-pilot.mjs';
async function main(){
  const file='offline-output/company-access/pilot-3-resume.json';
  const previous=await fs.readFile(file,'utf8').then(JSON.parse).catch(e=>{if(e.code==='ENOENT')return null;throw e;});
  const result=await executePilot({key:process.env.JINKE_AMAP_KEY,context:process.env,pilotVersion:'amap-pilot-3',previous});
  await fs.appendFile(process.env.GITHUB_OUTPUT,'artifact_ready=true\n');
  const r=result.report,summary=`Pilot 3: identified office candidates, not complete inventory\n\nThis run: ${r.api_requests_this_execution} attempts\nLifetime: ${r.api_requests_total}/48 attempts\nRaw POIs: ${r.raw_poi_results}\nUnique POIs: ${r.unique_amap_ids}\nClipped candidates: ${r.candidate_review_count}\nStop: ${r.stop_reason}\n\nDownload review/review-bundle.json and use Open new batch in the Review Console. Prior decisions are locked there. Export one session JSON after review.\n`;
  const recovery=`\nIncomplete cells: ${new Set((r.incomplete_queries||[]).map(q=>q.cell_id)).size}\nExhausted queries: ${(r.incomplete_queries||[]).filter(q=>q.reason==='RETRY_EXHAUSTED').length}\n${r.stop_reason==='AMAP_CONNECTIVITY_STOP'?'Connectivity cutoff reached across multiple cells. Inspect connectivity before another dispatch; the open circuit will not spend further attempts.':'Incomplete queries remain recorded in the snapshot and coverage artifacts; they are not retried.'}\n`;
  assertKeyFree(summary+recovery,process.env.JINKE_AMAP_KEY);await fs.appendFile(process.env.GITHUB_STEP_SUMMARY,summary+recovery);
  if(result.providerStopped)process.exitCode=1;
}
main().catch(()=>{console.error('PILOT3_FAILED: inspect safe artifacts; no credentials or provider exceptions logged.');process.exitCode=1;});
