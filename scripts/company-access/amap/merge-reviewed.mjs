// Merge only independently human-reviewed imports. Never mutate a previous pilot.
import fs from 'node:fs/promises';
import path from 'node:path';
import {ingest,artifactNames,validateArtifacts} from '../ingest.mjs';
import {sha256,stable,fail} from '../common.mjs';
export function mergeReviewedPilots(baseline,incoming,areas){
 const check=pilot=>{
   validateArtifacts(pilot.artifacts,areas);
   const accepts=new Set(pilot.decisions.filter(d=>d.decision==='accept').map(d=>d.amap_poi_id));
   if(pilot.envelope.records.some(r=>!accepts.has(r.source_record_id)||r.source_evidence.reviewed!==true))fail('UNACCEPTED_MERGE_INPUT');
   const rebuilt=ingest(pilot.envelope,areas);
   if(stable(rebuilt.offices)!==stable(pilot.artifacts.offices))fail('STALE_REVIEWED_IMPORT');
 };
 check(baseline);check(incoming);
 const locked=new Map(baseline.decisions.map(d=>[d.amap_poi_id,d]));
 const held=incoming.envelope.records.filter(r=>locked.has(r.source_record_id)&&locked.get(r.source_record_id).decision!=='accept');
 const records=[...baseline.envelope.records,...incoming.envelope.records.filter(r=>!held.includes(r))];
 const envelope={...baseline.envelope,dataset_version:`reviewed-pilots-${sha256(stable(records)).slice(0,16)}`,records};
 const artifacts=ingest(envelope,areas);
 const remaining=new Set(artifacts.audit.accepted.flatMap(a=>a.sources.map(s=>s.raw_record.source_record_id)));
 if(baseline.envelope.records.some(r=>!remaining.has(r.source_record_id)))fail('BASELINE_OFFICE_CONFLICT_REQUIRES_REVIEW');
 return {envelope,artifacts,decisions:[...baseline.decisions,...incoming.decisions.filter(d=>!locked.has(d.amap_poi_id))],held:held.map(r=>({amap_poi_id:r.source_record_id,reason:'EXISTING_DECISION_LOCKED'}))};
}
if(process.argv[1]?.endsWith('merge-reviewed.mjs')){
 const [base,next,output]=process.argv.slice(2);if(!output)throw Error('Usage: baseline-import incoming-import fresh-output');
 const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
 const load=async dir=>{const artifacts={};for(const [key,name] of Object.entries(artifactNames))artifacts[key]=await read(path.join(dir,['audit','rejected','review'].includes(key)?'audit':'frontend',name));return {artifacts,envelope:await read(path.join(dir,'approved/raw-input.json')),decisions:(await read(path.join(dir,'audit/human-review.json'))).decisions};};
 const root=path.resolve('offline-output/company-access'),target=path.resolve(output);
 if(path.dirname(target)!==root)fail('UNSAFE_OUTPUT_DIRECTORY');
 const merged=mergeReviewedPilots(await load(base),await load(next),await read('web/public/data/reach-areas.geojson'));
 await fs.mkdir(target);for(const folder of ['frontend','approved','audit'])await fs.mkdir(path.join(target,folder));
 const write=(p,value)=>fs.writeFile(path.join(target,p),stable(value)+'\n',{flag:'wx'});
 for(const [key,name] of Object.entries(artifactNames))await write(path.join(['audit','rejected','review'].includes(key)?'audit':'frontend',name),merged.artifacts[key]);
 await write('approved/raw-input.json',merged.envelope);await write('audit/human-review.json',{decisions:merged.decisions});await write('audit/cross-pilot-held.json',merged.held);
 console.log(stable({offices:merged.artifacts.offices.features.length,held:merged.held.length,dispositions:merged.artifacts.metadata.ingestion.dispositions}));
}
