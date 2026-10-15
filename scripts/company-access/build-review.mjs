// Explicit review packaging only. The default build never includes real offices.
import {readFile,writeFile,mkdir,cp,rm} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {artifactNames,validateArtifacts} from './ingest.mjs';
import {writeReviewBundle} from './amap/console.mjs';
import {coverageReport} from './amap/pilot3-workflow.mjs';
import {attachReviewHistory} from '../../web/src/company-access/review-history.js';
import {validateSecondPass} from '../../web/src/company-access/review-triage.js';
const input=process.argv[2];if(!input)throw Error('Approved import directory required');
const root=resolve(input),artifacts={};
for(const [key,name] of Object.entries(artifactNames))artifacts[key]=JSON.parse(await readFile(join(root,['audit','rejected','review'].includes(key)?'audit':'frontend',name),'utf8'));
const areas=JSON.parse(await readFile('web/public/data/reach-areas.geojson','utf8'));validateArtifacts(artifacts,areas);
const review=JSON.parse(await readFile(join(root,'audit/human-review.json'),'utf8'));
const accepted=new Set(review.decisions.filter(d=>d.decision==='accept').map(d=>d.amap_poi_id));
if(artifacts.metadata.dataset_kind!=='candidate')throw Error('Candidate import required');
for(const office of artifacts.audit.accepted)for(const source of office.sources)if(!accepted.has(source.raw_record.source_record_id)||source.raw_record.source_evidence.reviewed!==true)throw Error('Unaccepted source in approved output');
const build=spawnSync(process.execPath,['scripts/build.mjs'],{env:{...process.env,VITE_BASE:'/'},stdio:'inherit'});if(build.status!==0)process.exit(build.status||1);
await rm('dist-review',{recursive:true,force:true});await cp('dist','dist-review',{recursive:true});
const target='dist-review/data/company-access-review';await mkdir(target,{recursive:true});
for(const key of ['offices','hubs','summary','metadata'])await cp(join(root,'frontend',artifactNames[key]),join(target,artifactNames[key]));
await cp('docs/company-access-sampling-coverage.svg',join(target,'sampling-coverage.svg'));
const history=await writeReviewBundle(root,join(target,'review-bundle.json'));
let pilot3Snapshot=null;
try{pilot3Snapshot=JSON.parse(await readFile(join(root,'source-imports/pilot-3/provider-cache/snapshot.json'),'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
await writeFile(join(target,'pilot3-coverage.geojson'),JSON.stringify(coverageReport(areas,pilot3Snapshot)));
// An explicit extra input packages pending candidates only for this review site.
// Never copies provider snapshots, raw evidence files or any real data to git.
if(process.argv[3]){
  const pendingRoot=resolve(process.argv[3]);
  const incoming=JSON.parse(await readFile(join(pendingRoot,'pending-review-bundle.json'),'utf8'));
  if(incoming.batches.flatMap(b=>b.rows).some(i=>i.locked||i.row.review_status!=='pending'))throw Error('Pending-only review input required');
  const pack=JSON.parse(await readFile(join(pendingRoot,'second-pass.json'),'utf8'));
  validateSecondPass(attachReviewHistory(incoming,history),pack);
  for(const name of ['pending-review-bundle.json','second-pass.json','pilot3-coverage.geojson'])await cp(join(pendingRoot,name),join(target,name));
}
await cp('scripts/company-access/review-console.html','dist-review/company-review.html');
let html=await readFile('dist-review/index.html','utf8');html=html.replace('<head>','<head>\n<meta name="jinke-company-review" content="approved-pilots">');await writeFile('dist-review/index.html',html);
console.log(`Review build ready: ${artifacts.offices.features.length} canonical offices; no raw evidence copied.`);
