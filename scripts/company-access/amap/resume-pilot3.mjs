// Uses only the ephemeral Actions GitHub token, never the AMap credential.
// Do not restart a prior pilot whose checkpoint is missing or expired.
import fs from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {requireManualReviewRun} from './actions-pilot.mjs';
const root='https://api.github.com/repos/FelixVVu/jinke';
export async function previousPilotArtifact(context,getJSON){
  requireManualReviewRun(context);
  let previous=null;
  for(let page=1;page<=10;page++){
    const data=await getJSON(`${root}/actions/workflows/company-access-amap-pilot.yml/runs?branch=review%2Fcompany-access-scaffold&event=workflow_dispatch&per_page=100&page=${page}`);
    previous=data.workflow_runs.find(r=>r.name==='Company Access AMap Pilot 3 (manual review only)'&&String(r.id)!==context.GITHUB_RUN_ID&&r.run_number<Number(context.GITHUB_RUN_NUMBER));
    if(previous||data.workflow_runs.length<100)break;if(page===10)throw Error('Cannot establish full pilot history');
  }
  if(!previous)return null;
  if(previous.status!=='completed')throw Error('Previous pilot is not complete');
  const data=await getJSON(`${root}/actions/runs/${previous.id}/artifacts?per_page=100`);
  const artifact=data.artifacts.find(a=>a.name===`company-access-amap-pilot-3-${previous.id}`&&!a.expired);
  if(!artifact)throw Error('Prior checkpoint missing: refuse fresh quota or duplicate acquisition');
  return artifact;
}
async function main(){
  const headers={Authorization:`Bearer ${process.env.GITHUB_TOKEN}`,Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'};
  const get=async url=>{const r=await fetch(url,{headers});if(!r.ok)throw Error('GitHub resume lookup failed');return r;};
  const artifact=await previousPilotArtifact(process.env,async url=>(await get(url)).json());
  if(!artifact)return;
  const bytes=await (await get(`${root}/actions/artifacts/${artifact.id}/zip`)).arrayBuffer();
  if(bytes.byteLength>20*1024*1024)throw Error('Artifact too large');
  await fs.mkdir('offline-output/company-access',{recursive:true});await fs.writeFile('offline-output/company-access/resume.zip',Buffer.from(bytes));
  // Extract only the fixed checkpoint member; no artifact-controlled filesystem paths.
  execFileSync('python3',['-c',"import zipfile\nz=zipfile.ZipFile('offline-output/company-access/resume.zip')\np=z.getinfo('provider-cache/snapshot.json')\nassert p.file_size < 10000000\nopen('offline-output/company-access/pilot-3-resume.json','wb').write(z.read(p))"]);
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)main().catch(()=>{console.error('PILOT3_RESUME_BLOCKED: previous checkpoint unavailable or GitHub history could not be verified. No AMap requests made.');process.exitCode=1;});
