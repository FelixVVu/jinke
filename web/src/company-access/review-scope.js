import {validateSession} from './review-state.js';
export const scopeItems=(items,batch)=>batch==='all'?items:items.filter(i=>i.batch===batch);
// A saved composite draft takes precedence over migration from an older batch.
// Never overwrite its human decisions by re-appending the same pending artifact.
export function resumeAppended(bundle,migrated,saved){
  validateSession(bundle,migrated);
  return saved?validateSession(bundle,JSON.parse(saved)):migrated;
}
