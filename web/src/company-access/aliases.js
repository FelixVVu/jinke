import {priorityEvidence} from './priority-evidence.js';
// Search metadata only. Exact office/name binding; never an identity merge rule.
// Reviewed mappings supplied explicitly by the user, 2026-10-02.
export const reviewedAliases = Object.freeze([
  {office_id:'office-a687151c1b1fc0bded20bdd0',source_identity:{provider:'amap',poi_id:'B0FFG951GY'},canonical_name:'思爱普有限公司',brand_name:'SAP',acronym:'SAP',aliases:['思爱普'],reviewed_by:'User request 2026-10-02'},
  {office_id:'office-6416a1738f6ca3e36b50c291',source_identity:{provider:'amap',poi_id:'B0FFG8GPRH'},canonical_name:'英伟达半导体科技(上海)有限公司',brand_name:'NVIDIA',aliases:['英伟达'],reviewed_by:'User request 2026-10-02'},
  ...priorityEvidence.filter(e=>e.aliases.length).map(e=>({source_identity:{provider:'amap',poi_id:e.poi_id},canonical_name:e.company_name,aliases:e.aliases,reviewed_by:'Source-assisted search metadata review 2026-10-29; not office approval',sources:e.sources})),
]);
// Search-only normalization; never used for canonical naming or deduplication.
export const normalizeSearch=value=>String(value??'').normalize('NFKC').toLowerCase().replace(/[\p{P}\p{Z}\s]+/gu,'');
function sourceIdentity(record){
  if(typeof record.amap_poi_id==='string')return {provider:'amap',poi_id:record.amap_poi_id};
  if(record.source_type==='licensed_poi'&&typeof record.source_id==='string'){
    try{const value=JSON.parse(record.source_id);if(Array.isArray(value)&&value.length===2)return {provider:value[0],poi_id:value[1]};}catch{}
  }
  return null;
}
export function aliasTerms(office,metadata=reviewedAliases){
  const source=sourceIdentity(office);
  const record=metadata.find(r=>r.reviewed_by&&normalizeSearch(r.canonical_name)===normalizeSearch(office.company_name)&&
    ((r.office_id&&r.office_id===office.id)||(source&&source.provider===r.source_identity?.provider&&source.poi_id===r.source_identity?.poi_id)));
  return record?[record.english_name,record.brand_name,record.acronym,...(record.aliases||[])].filter(Boolean):[];
}
