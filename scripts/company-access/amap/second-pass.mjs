// Offline, suggestion-only preparation. Keeps snapshot and review bundle identity
// intact so the existing human-session importer remains the only approval gate.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {stable,sha256} from '../common.mjs';
import {makeReviewBundle} from './console.mjs';
import {loadApproved,coverageReport} from './pilot3-workflow.mjs';
import {attachReviewHistory} from '../../../web/src/company-access/review-history.js';
import {TRIAGE_VERSION,triageItems,validateSecondPass,isPriority} from '../../../web/src/company-access/review-triage.js';
export function prepareSecondPass({incoming,history,seed,evidence}){
  if(seed.bundle_id!==incoming.bundle_id||seed.input_candidate_count!==incoming.batches.flatMap(b=>b.rows).length||seed.all_candidate_decisions_remain!=='pending')throw Error('Attachment does not match the incoming snapshot');
  if(incoming.batches.flatMap(b=>b.rows).some(i=>i.locked||i.row.review_status!=='pending'))throw Error('Incoming candidates must start pending');
  const bundle=attachReviewHistory(incoming,history);
  const editableIds=new Set(bundle.batches.flatMap(b=>b.rows).filter(i=>!i.locked).map(i=>i.row.amap_poi_id));
  const pack={schema_version:1,version:TRIAGE_VERSION,bundle_id:bundle.bundle_id,source_bundle_id:incoming.bundle_id,
    input_sha256:sha256(stable(seed)),evidence_sha256:sha256(stable(evidence)),
    seeds:seed.records.filter(r=>editableIds.has(r.poi_id)),evidence:evidence.filter(e=>editableIds.has(e.poi_id))};
  // Reject unknown/duplicate IDs rather than silently discarding malformed input.
  const sourceIds=new Set(incoming.batches.flatMap(b=>b.rows).map(i=>i.row.amap_poi_id));
  for(const records of [seed.records,evidence])if(new Set(records.map(r=>r.poi_id)).size!==records.length||records.some(r=>!sourceIds.has(r.poi_id)))throw Error('Unknown or duplicate evidence/seed ID');
  validateSecondPass(bundle,pack);
  const items=triageItems(bundle.batches.flatMap(b=>b.rows),pack.evidence,pack.seeds),fresh=items.filter(i=>!i.locked);
  const counts=key=>Object.fromEntries([...new Set(fresh.map(i=>i.triage[key]))].sort().map(v=>[v,fresh.filter(i=>i.triage[key]===v).length]));
  pack.summary={candidates:fresh.length,locked_history:items.filter(i=>i.locked).length,groups:counts('group'),reasons:counts('reason'),tiers:counts('tier'),priority_exceptions:fresh.filter(isPriority).length,public_evidence_records:pack.evidence.length,
    notice:'Suggestions only. Public-source checks are targeted, not exhaustive. No acceptance or physical verification is inferred. All incoming decisions remain pending.'};
  return {incoming,pack,summary:pack.summary};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){
  const [base,snapshotPath,seedPath,evidencePath,output]=process.argv.slice(2);
  if(!output)throw Error('Usage: second-pass.mjs APPROVED SNAPSHOT ATTACHED_TRIAGE PUBLIC_EVIDENCE FRESH_OUTPUT');
  const target=path.resolve(output);if(path.dirname(target)!==path.resolve('offline-output/company-access'))throw Error('Unsafe output');
  const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
  const areas=await read('web/public/data/reach-areas.geojson'),baseline=await loadApproved(base),snapshot=await read(snapshotPath);
  if(snapshot.version!=='amap-pilot-3')throw Error('Pilot 3 snapshot required');
  const snapshots=await Promise.all(['pilot-1','pilot-2'].map(p=>read(path.join(base,`source-imports/${p}/provider-cache/snapshot.json`))));
  const history=makeReviewBundle(snapshots,areas,baseline.decisions,baseline.artifacts.offices.features.map(f=>f.properties));
  const result=prepareSecondPass({incoming:makeReviewBundle([snapshot],areas),history,seed:await read(seedPath),evidence:await read(evidencePath)});
  await fs.mkdir(target);
  for(const [name,value]of Object.entries({'pending-review-bundle.json':result.incoming,'second-pass.json':result.pack,'pilot3-coverage.geojson':coverageReport(areas,snapshot)}))await fs.writeFile(path.join(target,name),stable(value)+'\n',{flag:'wx'});
  console.log(stable(result.summary));
}
