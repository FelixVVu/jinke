import {validateBundle,createSession,validateSession} from './review-state.js';
import {attachReviewHistory} from './review-history.js';
import {validateSecondPass} from './review-triage.js';
// Append discovery without losing the recovery queue, decisions or local history.
// A changed provider assertion is blocked, never silently replaced on resume.
export function appendPending(current,incoming,history,session,pack=null){
  validateBundle(current);validateBundle(incoming);validateSession(current,session);
  if(pack)validateSecondPass(current,pack);
  const historical=new Set(history.batches.map(b=>b.id)),priorIds=new Set(history.batches.flatMap(b=>b.rows.map(i=>i.row.amap_poi_id)));
  const batches=structuredClone(current.batches.filter(b=>!historical.has(b.id)));
  for(const batch of incoming.batches){
    if(historical.has(batch.id)||batch.rows.some(i=>i.locked||i.row.review_status!=='pending'||priorIds.has(i.row.amap_poi_id)))throw Error('New pending candidates only; historical decisions cannot be reopened');
    const old=batches.find(b=>b.id===batch.id);
    if(old){
      const next=new Map(batch.rows.map(i=>[i.key,i]));
      if(old.rows.some(i=>!next.has(i.key)||JSON.stringify(next.get(i.key).row)!==JSON.stringify(i.row)))throw Error('Changed discovery assertion: separate conflict review required');
      const keys=new Set(old.rows.map(i=>i.key));old.rows.push(...structuredClone(batch.rows.filter(i=>!keys.has(i.key))));
    }else batches.push(structuredClone(batch));
  }
  const all=batches.flatMap(b=>b.rows);if(new Set(all.map(i=>i.row.amap_poi_id)).size!==all.length)throw Error('Duplicate provider identity across pending batches');
  // Reproducible, browser-safe composite identity; no cryptographic trust inferred.
  const bundle=attachReviewHistory({schema_version:1,bundle_id:`append:${batches.map(b=>`${b.id}:${b.rows.map(i=>i.row.amap_poi_id).join(',')}`).join('|')}`,batches,coverage:incoming.coverage||current.coverage},history);
  const nextSession=createSession(bundle);nextSession.reviewer=session.reviewer;
  for(const key of Object.keys(nextSession.decisions))if(session.decisions[key])nextSession.decisions[key]=structuredClone(session.decisions[key]);
  validateSession(bundle,nextSession);
  let nextPack=null;if(pack){
    const seeded=new Set(pack.seeds.map(s=>s.poi_id));
    nextPack={...structuredClone(pack),bundle_id:bundle.bundle_id,seeds:[...structuredClone(pack.seeds),...all.filter(i=>!seeded.has(i.row.amap_poi_id)).map(i=>({poi_id:i.row.amap_poi_id,company_name:i.row.company_name,address:i.row.address,decision:'pending',flags:['TARGETED_NEW_CANDIDATE']}))]};
    validateSecondPass(bundle,nextPack);
  }
  return {bundle,session:nextSession,pack:nextPack};
}
// A single downloadable bundle can carry its validated suggestion pack. This
// changes neither provider assertions nor human decisions and needs no CSV.
export function appendDiscovery(current,incoming,history,session,pack=null){
  if(incoming.second_pass)validateSecondPass(incoming,incoming.second_pass);
  const next=appendPending(current,incoming,history,session,pack);
  if(incoming.second_pass){
    if(!next.pack)next.pack={schema_version:1,version:incoming.second_pass.version,bundle_id:next.bundle.bundle_id,evidence:[],seeds:next.bundle.batches.flatMap(b=>b.rows).filter(i=>!i.locked).map(i=>({poi_id:i.row.amap_poi_id,company_name:i.row.company_name,address:i.row.address,decision:'pending',flags:[]}))};
    const p=incoming.second_pass,ids=new Set(p.seeds.map(s=>s.poi_id));
    next.pack={...next.pack,evidence:[...next.pack.evidence.filter(e=>!ids.has(e.poi_id)),...p.evidence],seeds:[...next.pack.seeds.filter(s=>!ids.has(s.poi_id)),...p.seeds]};
    validateSecondPass(next.bundle,next.pack);
  }
  return next;
}
