import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {planQueries} from './plan.mjs';
import {validateSnapshot,pilot3RecoveryState} from './acquire.mjs';
import {makeReviewBundle} from './console.mjs';
import {validateSession,exportRows} from '../../../web/src/company-access/review-state.js';
import {attachReviewHistory} from '../../../web/src/company-access/review-history.js';
import {approvedFromReview,toCSV} from './review.mjs';
import {mergeReviewedPilots} from './merge-reviewed.mjs';
import {ingest,artifactNames,validateArtifacts} from '../ingest.mjs';
import {stable} from '../common.mjs';
export function coverageReport(areas,snapshot=null){
  const plan=planQueries(areas,'amap-pilot-3');if(snapshot)validateSnapshot(snapshot,areas);
  const incomplete=snapshot?pilot3RecoveryState(snapshot).incomplete_queries:[];
  const features=plan.cells.map((cell,index)=>{
    const ids=new Set(plan.queries.filter(q=>q.cell_id===cell.id).map(q=>q.id));
    const responses=(snapshot?.responses||[]).filter(r=>ids.has(r.query_id));
    const issues=incomplete.filter(q=>q.cell_id===cell.id);
    return {type:'Feature',geometry:cell.geometry,properties:{cell_id:cell.id,priority:index+1,prior_poi_observations:cell.prior_poi_observations,attempts:(snapshot?.attempts||[]).filter(a=>ids.has(a.query_id)).length,pages_returned:responses.length,raw_pois:responses.reduce((n,r)=>n+r.payload.pois.length,0),incomplete_queries:issues,status:issues.length?'incomplete_acquisition':responses.length?'sampled_not_complete':'not_sampled_by_pilot3'}};
  });
  return {type:'FeatureCollection',features,summary:{cells:features.length,cells_without_prior_poi_observations:features.filter(f=>!f.properties.prior_poi_observations).length,pilot3_cells_sampled:features.filter(f=>f.properties.pages_returned).length,pilot3_cells_remaining:features.filter(f=>!f.properties.pages_returned).length,pilot3_cells_incomplete:features.filter(f=>f.properties.incomplete_queries.length).length,notice:'Sampling effort, not inventory completeness. No returned offices does not establish an empty reach area.'}};
}
export function importPilot3({snapshot,areas,baseline,historyBundle,session,reviewedAt}){
  if(snapshot.version!=='amap-pilot-3')throw Error('Pilot 3 snapshot required');
  const pending=makeReviewBundle([snapshot],areas),bundle=attachReviewHistory(pending,historyBundle);
  validateSession(bundle,session);
  const rows=exportRows(bundle,session,pending.batches[0].id),csv=toCSV(rows);
  const incoming=approvedFromReview({snapshot,areas,csv,reviewer:session.reviewer,reviewedAt});
  const locked=new Set(baseline.decisions.map(d=>d.amap_poi_id));
  // Historical candidates are audit-only, including unchanged prior accepts.
  incoming.envelope.records=incoming.envelope.records.filter(r=>!locked.has(r.source_record_id));
  incoming.artifacts=ingest(incoming.envelope,areas);
  const merged=mergeReviewedPilots(baseline,incoming,areas);
  const resultById=new Map(merged.artifacts.offices.features.map(f=>[f.id,f]));
  if(baseline.artifacts.offices.features.some(f=>stable(resultById.get(f.id))!==stable(f)))throw Error('BASELINE_OFFICE_CHANGED_REQUIRES_REVIEW');
  return {...merged,session,csv,report:{human_new_accepts:rows.filter(r=>r.review_status==='accept'&&!locked.has(r.amap_poi_id)).length,canonical_offices:merged.artifacts.offices.features.length,prior_offices:baseline.artifacts.offices.features.length,prior_decisions:baseline.decisions.length,dispositions:merged.artifacts.metadata.ingestion.dispositions,new_canonical_dispositions:incoming.artifacts.metadata.ingestion.dispositions}};
}
export async function loadApproved(root){
  const read=async p=>JSON.parse(await fs.readFile(path.join(root,p),'utf8')),artifacts={};
  for(const[key,name]of Object.entries(artifactNames))artifacts[key]=await read(path.join(['audit','rejected','review'].includes(key)?'audit':'frontend',name));
  return {artifacts,envelope:await read('approved/raw-input.json'),decisions:(await read('audit/human-review.json')).decisions};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){
  const [command,base,snapshotPath,sessionPath,output]=process.argv.slice(2);
  if(command!=='import'||!output)throw Error('Usage: pilot3-workflow.mjs import BASE SNAPSHOT SESSION FRESH_OUTPUT');
  const target=path.resolve(output);if(path.dirname(target)!==path.resolve('offline-output/company-access'))throw Error('Unsafe output');
  const areas=JSON.parse(await fs.readFile('web/public/data/reach-areas.geojson','utf8')),baseline=await loadApproved(base);validateArtifacts(baseline.artifacts,areas);
  const snapshots=await Promise.all(['pilot-1','pilot-2'].map(p=>fs.readFile(path.join(base,`source-imports/${p}/provider-cache/snapshot.json`),'utf8').then(JSON.parse)));
  const historyBundle=makeReviewBundle(snapshots,areas,baseline.decisions,baseline.artifacts.offices.features.map(f=>f.properties));
  const snapshot=JSON.parse(await fs.readFile(snapshotPath,'utf8')),session=JSON.parse(await fs.readFile(sessionPath,'utf8'));
  const merged=importPilot3({snapshot,areas,baseline,historyBundle,session,reviewedAt:new Date().toISOString()});
  await fs.mkdir(target);for(const f of ['frontend','approved','audit','source-imports'])await fs.mkdir(path.join(target,f));
  for(const[key,name]of Object.entries(artifactNames))await fs.writeFile(path.join(target,['audit','rejected','review'].includes(key)?'audit':'frontend',name),stable(merged.artifacts[key])+'\n');
  await fs.writeFile(path.join(target,'approved/raw-input.json'),stable(merged.envelope)+'\n');
  await fs.writeFile(path.join(target,'audit/human-review.json'),stable({decisions:merged.decisions})+'\n');
  await fs.writeFile(path.join(target,'audit/pilot3-import-report.json'),stable(merged.report)+'\n');
  await fs.writeFile(path.join(target,'audit/pilot3-review-session.json'),stable(session)+'\n');
  await fs.cp(path.join(base,'source-imports'),path.join(target,'source-imports'),{recursive:true});
  await fs.mkdir(path.join(target,'source-imports/pilot-3/provider-cache'),{recursive:true});
  await fs.copyFile(snapshotPath,path.join(target,'source-imports/pilot-3/provider-cache/snapshot.json'));
  console.log(stable(merged.report));
}
