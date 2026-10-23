import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {recoverCandidates,recoveryBundle,importRecovery} from './recover.mjs';
import {geographicCoverage} from './coverage.mjs';
import {buildTargetedPlan,validateLeads} from './plan.mjs';
import {loadApproved} from '../amap/pilot3-workflow.mjs';
import {writeReviewBundle} from '../amap/console.mjs';
import {prepareSecondPass} from '../amap/second-pass.mjs';
import {artifactNames,validateArtifacts} from '../ingest.mjs';
import {stable,sha256} from '../common.mjs';
import {triageItems} from '../../../web/src/company-access/review-triage.js';
import {attachReviewHistory} from '../../../web/src/company-access/review-history.js';
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
export async function prepareRecoveryFiles(base,evidenceFile,output){
  const areas=await read('web/public/data/reach-areas.geojson'),baseline=await loadApproved(base);validateArtifacts(baseline.artifacts,areas);
  const snapshots=await Promise.all([1,2,3].map(n=>read(path.join(base,`source-imports/pilot-${n}/provider-cache/snapshot.json`))));
  const inputs=await read(evidenceFile);validateLeads(inputs.leads);
  const recovered=recoverCandidates({snapshots,areas,priorDecisions:baseline.decisions}),incoming=recoveryBundle(recovered,baseline.artifacts.offices.features.map(f=>f.properties));
  await fs.mkdir(output);const write=(p,value)=>fs.writeFile(path.join(output,p),stable(value)+'\n',{flag:'wx'});
  const history=await writeReviewBundle(base,path.join(output,'history-bundle.json'));
  const seed={bundle_id:incoming.bundle_id,input_candidate_count:recovered.candidates.length,all_candidate_decisions_remain:'pending',records:incoming.batches[0].rows.map(i=>({poi_id:i.row.amap_poi_id,company_name:i.row.company_name,address:i.row.address,decision:'pending',flags:i.evidence.recovery.original_exclusions}))};
  const {pack}=prepareSecondPass({incoming,history,seed,evidence:inputs.evidence});
  const report=geographicCoverage({snapshots,areas,offices:baseline.artifacts.offices,decisions:baseline.decisions,recovered,benchmarks:inputs.leads});
  const combined=attachReviewHistory(incoming,history),items=triageItems(combined.batches.flatMap(b=>b.rows),pack.evidence,pack.seeds).filter(i=>!i.locked);
  report.review_groups=items.reduce((a,i)=>(a[i.triage.group]=(a[i.triage.group]||0)+1,a),{});
  report.source_limitations=inputs.limitations;
  const plan=buildTargetedPlan({areas,priorityCellIds:inputs.priority_cell_ids,leads:inputs.leads});
  for(const [p,value] of Object.entries({'pending-review-bundle.json':{...incoming,coverage:report.coverage},'second-pass.json':pack,
    'pilot3-coverage.geojson':report.coverage,'coverage-diagnostics.json':report,'discovery-plan.json':plan,
    'recovery-audit.json':recovered,'discovery-evidence.json':inputs,
    'input-manifest.json':{version:recovered.version,snapshot_hashes:recovered.sourceHashes,baseline_ledger_sha256:sha256(stable(baseline.decisions)),approved_sha256:sha256(stable(baseline.artifacts.offices))}}))await write(p,value);
  return report;
}
export async function importRecoveryFiles(base,sessionFile,output){
  const areas=await read('web/public/data/reach-areas.geojson'),baseline=await loadApproved(base),session=await read(sessionFile);
  const snapshots=await Promise.all([1,2,3].map(n=>read(path.join(base,`source-imports/pilot-${n}/provider-cache/snapshot.json`))));
  // Temp history has no generated company data in the source tree.
  const temporary=await fs.mkdtemp(path.join(path.dirname(output),'.coverage-import-'));
  let merged;
  try{const historyBundle=await writeReviewBundle(base,path.join(temporary,'history.json'));
    merged=importRecovery({snapshots,areas,baseline,historyBundle,session,reviewedAt:new Date().toISOString()});
  }finally{await fs.rm(temporary,{recursive:true,force:true});}
  await fs.mkdir(output);for(const dir of ['frontend','audit','approved','source-imports'])await fs.mkdir(path.join(output,dir));
  for(const [key,name]of Object.entries(artifactNames))await fs.writeFile(path.join(output,['audit','rejected','review'].includes(key)?'audit':'frontend',name),stable(merged.artifacts[key])+'\n');
  await fs.writeFile(path.join(output,'approved/raw-input.json'),stable(merged.envelope)+'\n');
  await fs.writeFile(path.join(output,'audit/human-review.json'),stable({decisions:merged.decisions})+'\n');
  await fs.writeFile(path.join(output,'audit/coverage-import-report.json'),stable(merged.report)+'\n');
  await fs.copyFile(sessionFile,path.join(output,'audit/coverage-human-session.json'));
  await fs.cp(path.join(base,'source-imports'),path.join(output,'source-imports'),{recursive:true});
  const provenance=path.join(output,`source-imports/coverage-${merged.incoming.bundle_id.slice(0,16)}`);await fs.mkdir(provenance);
  await fs.writeFile(path.join(provenance,'recovery-bundle.json'),stable(merged.incoming)+'\n');
  await fs.writeFile(path.join(provenance,'recovery-audit.json'),stable(merged.recovered)+'\n');
  return merged.report;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){
  const [command,base,input,output]=process.argv.slice(2);
  if(!['prepare','import'].includes(command)||!output||path.dirname(path.resolve(output))!==path.resolve('offline-output/company-access'))throw Error('Usage: workflow.mjs prepare|import APPROVED_ROOT EVIDENCE_OR_SESSION FRESH_OFFLINE_OUTPUT');
  const result=command==='prepare'?await prepareRecoveryFiles(base,input,output):await importRecoveryFiles(base,input,output);
  console.log(stable(result.summary||result));
}
