import fs from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {requireManualReviewRun} from '../amap/actions-pilot.mjs';
import {CAMPAIGN,WORKFLOW_NAME} from './targeted-plan.mjs';
import {validateTargeted} from './targeted.mjs';
const root='https://api.github.com/repos/FelixVVu/jinke';
export async function previousTargetedArtifact(context,getJSON,{workflowName=WORKFLOW_NAME,campaign=CAMPAIGN,stepName='Acquire targeted 30m and prepare pending review bundle'}={}){
  requireManualReviewRun(context);
  if(!/^\d+$/.test(context.GITHUB_RUN_ID||'')||!/^\d+$/.test(context.GITHUB_RUN_NUMBER||''))throw Error('Missing run identity');
  for(let page=1;page<=10;page++){
    const data=await getJSON(`${root}/actions/workflows/company-access-amap-pilot.yml/runs?branch=review%2Fcompany-access-scaffold&event=workflow_dispatch&per_page=100&page=${page}`);
    const runs=data.workflow_runs.filter(r=>r.name===workflowName&&String(r.id)!==context.GITHUB_RUN_ID&&r.run_number<Number(context.GITHUB_RUN_NUMBER)).sort((a,b)=>b.run_number-a.run_number);
    for(const run of runs){
      if(run.status!=='completed')throw Error('Previous targeted run not complete');
      const {artifacts}=await getJSON(`${root}/actions/runs/${run.id}/artifacts?per_page=100`);
      const names=[`company-access-${campaign}-${run.id}`,`company-access-${campaign}-checkpoint-${run.id}`];
      for(const name of names){const artifact=artifacts.find(a=>a.name===name&&!a.expired);if(artifact)return artifact;}
      // Only an authoritative skipped/not-started acquisition step may be ignored.
      // A failed/cancelled started step with no checkpoint must fail closed.
      const {jobs}=await getJSON(`${root}/actions/runs/${run.id}/jobs?per_page=100`);
      const step=jobs.flatMap(j=>j.steps||[]).find(s=>s.name===stepName);
      if(!step||step.conclusion!=='skipped')throw Error('Prior targeted checkpoint missing: refuse a fresh quota');
    }
    if(data.workflow_runs.length<100)return null;
  }
  throw Error('Cannot establish full targeted history');
}
async function main(){
  if(process.argv.length!==2)throw Error('No resume inputs allowed');
  const headers={Authorization:`Bearer ${process.env.GITHUB_TOKEN}`,Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'};
  const get=async url=>{const r=await fetch(url,{headers});if(!r.ok)throw Error('GitHub history unavailable');return r;};
  const artifact=await previousTargetedArtifact(process.env,async url=>(await get(url)).json());if(!artifact)return;
  const bytes=await (await get(`${root}/actions/artifacts/${artifact.id}/zip`)).arrayBuffer();if(bytes.byteLength>20*1024*1024)throw Error('Oversized artifact');
  const folder='offline-output/company-access';await fs.mkdir(folder,{recursive:true});const archive=path.join(folder,`${CAMPAIGN}-resume.zip`),output=path.join(folder,`${CAMPAIGN}-resume.json`);
  await fs.writeFile(archive,Buffer.from(bytes),{flag:'wx',mode:0o600});
  // Fixed member only; no archive-controlled extraction paths or shell interpolation.
  const json=execFileSync('python3',['-c',"import sys,zipfile\nwith zipfile.ZipFile(sys.argv[1]) as z:\n p=z.getinfo('provider-cache/snapshot.json')\n assert p.file_size < 10000000\n sys.stdout.buffer.write(z.read(p))",archive],{maxBuffer:10000000});
  const areas=JSON.parse(await fs.readFile('web/public/data/reach-areas.geojson','utf8'));validateTargeted(JSON.parse(json),areas);
  await fs.writeFile(output,json,{flag:'wx',mode:0o600});
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)main().catch(()=>{console.error('TARGETED_RESUME_BLOCKED: previous targeted checkpoint or run history unavailable/invalid. No AMap requests made.');process.exitCode=1;});
