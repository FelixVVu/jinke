// Offline file operations only. This CLI never reads credentials or calls AMap.
import { readFile, writeFile, mkdir, realpath } from 'node:fs/promises';
import { resolve, dirname, join, relative } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { stable, fail } from '../common.mjs';
import { artifactNames } from '../ingest.mjs';
import { validateSnapshot, candidatesFromCache } from './acquire.mjs';
import { approvedFromReview, reviewRows, toCSV, qaReport, reportMarkdown } from './review.mjs';
const repo=resolve(dirname(fileURLToPath(import.meta.url)),'../../..');
const defaultReach=join(repo,'web/public/data/reach-areas.geojson');
async function freshDirectory(output){
  const root=join(repo,'offline-output/company-access');await mkdir(root,{recursive:true});
  const actualRoot=await realpath(root);
  if(actualRoot!==root)fail('UNSAFE_OUTPUT_DIRECTORY');
  const target=resolve(output),rel=relative(root,target);
  // Single run directory, no traversal, no symlinks, no tracked/browser outputs.
  if(!rel||rel.includes('/')||rel.startsWith('..'))fail('UNSAFE_OUTPUT_DIRECTORY');
  await mkdir(target);return target;
}
const json=async(path,value)=>writeFile(path,stable(value)+'\n',{flag:'wx'});
export async function prepareFiles({snapshotPath,output,reach=defaultReach}){
  const areas=JSON.parse(await readFile(reach,'utf8')),snapshot=validateSnapshot(JSON.parse(await readFile(snapshotPath,'utf8')),areas);
  const prepared=candidatesFromCache(snapshot,areas),bundle={snapshot,...prepared};
  const target=await freshDirectory(output);
  for(const folder of ['provider-cache','normalized','review','audit'])await mkdir(join(target,folder));
  await json(join(target,'provider-cache/snapshot.json'),snapshot);
  for(const response of snapshot.responses)await json(join(target,`provider-cache/${response.query_id}.json`),response);
  await json(join(target,'normalized/candidates.json'),prepared.candidates);
  await json(join(target,'normalized/raw-input.json'),{schema_version:1,dataset_kind:'candidate',dataset_version:'amap-pilot-unreviewed',records:prepared.candidates.map(c=>c.raw)});
  await json(join(target,'review/amap-office-review.json'),reviewRows(prepared.candidates));
  await writeFile(join(target,'review/amap-office-review.csv'),toCSV(reviewRows(prepared.candidates)),{flag:'wx'});
  await json(join(target,'audit/acquisition-exclusions.json'),prepared.exclusions);
  await json(join(target,'audit/pilot-report.json'),qaReport(bundle));
  await writeFile(join(target,'audit/pilot-report.md'),reportMarkdown(qaReport(bundle)),{flag:'wx'});
  return {output:target,...prepared.counts};
}
export async function importFiles({snapshotPath,csvPath,output,reviewer,reviewedAt,reach=defaultReach}){
  const areas=JSON.parse(await readFile(reach,'utf8')),snapshot=JSON.parse(await readFile(snapshotPath,'utf8')),csv=await readFile(csvPath,'utf8');
  const approved=approvedFromReview({snapshot,areas,csv,reviewer,reviewedAt});
  const target=await freshDirectory(output);
  for(const folder of ['approved','frontend','audit','review','provider-cache'])await mkdir(join(target,folder));
  await json(join(target,'provider-cache/snapshot.json'),snapshot);
  await writeFile(join(target,'review/amap-office-review.csv'),csv,{flag:'wx'});
  await json(join(target,'approved/raw-input.json'),approved.envelope);
  await json(join(target,'audit/human-review.json'),{decisions:approved.decisions,snapshot_sha256:approved.snapshot_sha256,review_csv_sha256:approved.review_csv_sha256});
  for(const [key,name] of Object.entries(artifactNames))await json(join(target,['audit','rejected','review'].includes(key)?'audit':'frontend',name),approved.artifacts[key]);
  const report=qaReport({snapshot,...candidatesFromCache(snapshot,areas)},approved);
  await json(join(target,'audit/pilot-report.json'),report);
  await writeFile(join(target,'audit/pilot-report.md'),reportMarkdown(report),{flag:'wx'});
  return {output:target,accepted:report.accepted_count,canonical:report.reviewed_office_locations,pending:report.pending_count,rejected:report.rejected_count};
}
export async function main(args){
  const command=args.shift(),options={},names={'--snapshot':'snapshotPath','--csv':'csvPath','--output':'output','--reviewer':'reviewer','--reviewed-at':'reviewedAt'};
  for(let i=0;i<args.length;i+=2){if(!names[args[i]]||!args[i+1])fail('INVALID_ARGUMENT');options[names[args[i]]]=args[i+1];}
  if(!options.snapshotPath||!options.output)fail('MISSING_ARGUMENT');
  if(command==='prepare')return prepareFiles(options);
  if(command==='import-review'&&options.csvPath)return importFiles(options);
  fail('INVALID_COMMAND');
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href) main(process.argv.slice(2)).then(r=>console.log(stable(r))).catch(e=>{console.error(e.code||'PILOT_FILE_OPERATION_FAILED');process.exitCode=1;});
