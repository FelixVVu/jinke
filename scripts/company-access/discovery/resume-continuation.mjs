import fs from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {previousTargetedArtifact} from './resume-targeted.mjs';
import {CONTINUATION,CONTINUATION_WORKFLOW,CONTINUATION_STEP,startContinuation,validateContinuation} from './continuation.mjs';
import {stable,fail} from '../common.mjs';
export async function restoreContinuation(context,getJSON,readArtifact,areas){
  // Must establish both histories. Never reuse an older successful child when
  // a later started/uncertain run lost its checkpoint.
  const original=await previousTargetedArtifact(context,getJSON);
  if(!original)fail('ORIGINAL_CHECKPOINT_REQUIRED');
  const parent=await readArtifact(original);
  const initial=startContinuation(parent,areas);
  const child=await previousTargetedArtifact(context,getJSON,{workflowName:CONTINUATION_WORKFLOW,campaign:CONTINUATION,stepName:CONTINUATION_STEP});
  if(!child)return initial;
  const s=validateContinuation(await readArtifact(child),areas);
  if(stable(s.parent)!==stable(parent))fail('ORIGINAL_ADVANCED_AFTER_FORK');
  return s;
}
async function main(){
  if(process.argv.length!==2)fail('NO_RESUME_ARGUMENTS');
  const root='https://api.github.com/repos/FelixVVu/jinke',headers={Authorization:`Bearer ${process.env.GITHUB_TOKEN}`,Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'};
  const get=async url=>{const r=await fetch(url,{headers});if(!r.ok)fail('HISTORY_UNAVAILABLE');return r;};
  const folder='offline-output/company-access';await fs.mkdir(folder,{recursive:true});
  const readArtifact=async artifact=>{
    const bytes=await (await get(`${root}/actions/artifacts/${artifact.id}/zip`)).arrayBuffer();if(bytes.byteLength>20*1024*1024)fail('OVERSIZED_ARTIFACT');
    const file=path.join(folder,`restore-${artifact.id}.zip`);await fs.writeFile(file,Buffer.from(bytes),{flag:'wx',mode:0o600});
    const json=execFileSync('python3',['-c',"import sys,zipfile\nwith zipfile.ZipFile(sys.argv[1]) as z:\n p=z.getinfo('provider-cache/snapshot.json')\n assert p.file_size < 10000000\n sys.stdout.buffer.write(z.read(p))",file],{maxBuffer:10000000});return JSON.parse(json);
  };
  const areas=JSON.parse(await fs.readFile('web/public/data/reach-areas.geojson','utf8'));
  const s=await restoreContinuation(process.env,async url=>(await get(url)).json(),readArtifact,areas);
  await fs.writeFile(path.join(folder,`${CONTINUATION}-resume.json`),stable(s)+'\n',{flag:'wx',mode:0o600});
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)main().catch(()=>{console.error('CONTINUATION_RESTORE_BLOCKED: original or latest continuation checkpoint unavailable/invalid. No fresh budget and no AMap request.');process.exitCode=1;});
