// Offline only: build a sanitized review bundle or validate/export a human session.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {sha256,stable} from '../common.mjs';
import {validateSnapshot,candidatesFromCache} from './acquire.mjs';
import {reviewRows,COLUMNS,toCSV,approvedFromReview} from './review.mjs';
import {suggest,validateSession,exportRows} from '../../../web/src/company-access/review-state.js';
export function makeReviewBundle(snapshots,areas,priorDecisions=[],priorOffices=[]){
  const prior=new Map();
  const normalize=value=>String(value||'').normalize('NFKC').trim().toLowerCase().replace(/\s+/gu,' ');
  const identityKey=(name,address)=>JSON.stringify([normalize(name),normalize(address)]);
  const officeIndex=new Map();for(const o of priorOffices){const key=identityKey(o.company_name,o.address);if(!officeIndex.has(key))officeIndex.set(key,[]);officeIndex.get(key).push(o);}
  for(const d of priorDecisions){if(prior.has(d.amap_poi_id))throw Error('Conflicting prior ledger');prior.set(d.amap_poi_id,d);}
  const batches=snapshots.map(snapshot=>{
    validateSnapshot(snapshot,areas);
    const id=sha256(stable(snapshot)),{candidates}=candidatesFromCache(snapshot,areas);
    return {id,label:snapshot.version,columns:COLUMNS,rows:reviewRows(candidates).map(row=>{
      const decision=prior.get(row.amap_poi_id),candidate=candidates.find(c=>c.amap_poi_id===row.amap_poi_id);
      const changed=decision&&decision.raw_sha256!==sha256(stable(candidate.raw));
      const matches=officeIndex.get(identityKey(row.company_name,row.address))||[];
      if(decision){row.review_status=decision.decision;row.review_notes=decision.notes;}
      const suggestion=changed?{disposition:'needs_review',reason:'PRIOR_SOURCE_CHANGED',version:'company-review-suggestions-v1'}:!decision&&matches.length?{disposition:'needs_review',reason:'PRIOR_INVENTORY_MATCH',version:'company-review-suggestions-v1'}:suggest(row);
      return {key:`${id}:${row.amap_poi_id}`,row,suggestion,locked:Boolean(decision),prior_review:decision?{reviewer:decision.reviewer,reviewed_at:decision.reviewed_at,decision:decision.decision,notes:decision.notes}:null,
        evidence:{source:'AMap mapped POI (not physical-office verification)',reference:row.source_reference,query_count:candidate.query_ids.length,prior_office_matches:matches.map(o=>o.id)}};
    })};
  });
  if(new Set(batches.map(b=>b.id)).size!==batches.length)throw Error('Duplicate snapshot');
  return {schema_version:1,bundle_id:sha256(stable(batches)),batches};
}
export function validateConsoleImport({snapshot,areas,priorDecisions,priorOffices=[],session,reviewedAt}){
  const bundle=makeReviewBundle([snapshot],areas,priorDecisions,priorOffices);validateSession(bundle,session);
  if(!session.reviewer.trim())throw Error('Reviewer required');
  // Extra review annotations must never mutate the provider's immutable CSV columns.
  const original=reviewRows(candidatesFromCache(snapshot,areas).candidates);
  const decisions=new Map(exportRows(bundle,session,bundle.batches[0].id).map(r=>[r.amap_poi_id,r]));
  const csv=toCSV(original.map(r=>({...r,review_status:decisions.get(r.amap_poi_id).review_status,review_notes:decisions.get(r.amap_poi_id).review_notes})));
  // Unchanged canonical validation/confidence/deduplication/reach assignment.
  const approved=approvedFromReview({snapshot,areas,csv,reviewer:session.reviewer,reviewedAt});
  return {csv,approved};
}
export async function writeReviewBundle(approvedRoot,target){
  const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
  const areas=await read('web/public/data/reach-areas.geojson');
  const prior=(await read(path.join(approvedRoot,'audit/human-review.json'))).decisions;
  const snapshots=await Promise.all(['pilot-1','pilot-2'].map(p=>read(path.join(approvedRoot,`source-imports/${p}/provider-cache/snapshot.json`))));
  const offices=(await read(path.join(approvedRoot,'frontend/company-offices.geojson'))).features.map(f=>f.properties);
  const bundle=makeReviewBundle(snapshots,areas,prior,offices);
  await fs.writeFile(target,stable(bundle)+'\n');return bundle;
}
// New batches are prepared against a trusted prior ledger, never browser-provided locks.
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){
  const [command,snapshotPath,ledgerPath,output,sessionPath]=process.argv.slice(2);
  if(!['prepare','validate-export'].includes(command)||!output)throw Error('Usage: console.mjs prepare|validate-export snapshot prior-ledger fresh-output [session]');
  const target=path.resolve(output),root=path.resolve('offline-output/company-access');
  if(path.dirname(target)!==root)throw Error('Output must be a fresh offline-output/company-access directory');
  const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
  const snapshot=await read(snapshotPath),priorDecisions=(await read(ledgerPath)).decisions,areas=await read('web/public/data/reach-areas.geojson');
  const priorOffices=(await read(path.resolve(path.dirname(ledgerPath),'../frontend/company-offices.geojson'))).features.map(f=>f.properties);
  const bundle=makeReviewBundle([snapshot],areas,priorDecisions,priorOffices);
  const imported=command==='validate-export'?validateConsoleImport({snapshot,areas,priorDecisions,priorOffices,session:await read(sessionPath),reviewedAt:new Date().toISOString()}):null;
  await fs.mkdir(target);
  await fs.writeFile(path.join(target,'review-bundle.json'),stable(bundle)+'\n',{flag:'wx'});
  if(imported){
    await fs.writeFile(path.join(target,'amap-office-review.csv'),imported.csv,{flag:'wx'});
    await fs.copyFile(sessionPath,path.join(target,'review-session.json'));
    await fs.writeFile(path.join(target,'canonical-validation.json'),stable({offices:imported.approved.artifacts.offices.features.length,dispositions:imported.approved.artifacts.metadata.ingestion.dispositions})+'\n',{flag:'wx'});
  }
}
