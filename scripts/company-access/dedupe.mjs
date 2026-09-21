import { compare, distance, idFor } from './common.mjs';
export const entityKey = r => r.raw.company_identity ? `reviewed:${r.raw.company_identity.id}` : `name:${r.normalized.normalized_name}`;
export const officeKey = r => r.raw.office_identity ? `reviewed-office:${r.raw.office_identity.id}` : JSON.stringify([entityKey(r),r.normalized.address_key]);
const confidenceRank = { verified: 0, building: 1, approximate: 2 };
export function preference(a,b) {
  return confidenceRank[a.location.location_confidence] - confidenceRank[b.location.location_confidence] ||
    Number(b.industry.industry_code !== null) - Number(a.industry.industry_code !== null) ||
    compare(b.raw.verified_at || '', a.raw.verified_at || '') || compare(a.ref,b.ref);
}
function conflictReason(records, metres, sameSource = false) {
  const sorted = [...records].sort(preference), anchor = sorted[0];
  const explicit = new Set(records.map(r=>r.raw.office_identity?.id).filter(Boolean));
  if (explicit.size > 1) return 'CONFLICTING_OFFICE_IDENTITIES';
  const oneReviewedOffice = explicit.size === 1 && records.every(r=>r.raw.office_identity?.id === anchor.raw.office_identity?.id);
  if (!oneReviewedOffice && records.some(r=>entityKey(r)!==entityKey(anchor) || r.normalized.address_key!==anchor.normalized.address_key)) return sameSource ? 'SOURCE_ID_CONFLICT' : 'IDENTITY_ADDRESS_CONFLICT';
  if (records.some(r=>distance(r.coordinates,anchor.coordinates)>metres)) return 'LOCATION_CONFLICT';
  if (new Set(records.map(r=>r.industry.industry_code).filter(Boolean)).size > 1) return 'INDUSTRY_CONFLICT';
  if (new Set(records.map(r=>r.normalized.district).filter(Boolean)).size > 1) return 'DISTRICT_CONFLICT';
  return null;
}

/** Hash groups + union-find. No fuzzy matching or all-pairs proximity search. */
export function deduplicate(records, settings) {
  const sorted = [...records].sort((a,b)=>compare(a.ref,b.ref));
  const parent = sorted.map((_,i)=>i);
  const find = i => { while(parent[i]!==i) { parent[i]=parent[parent[i]]; i=parent[i]; } return i; };
  const union = (a,b) => { a=find(a); b=find(b); if(a!==b) parent[b]=a; };
  const groups = [new Map(),new Map()];
  sorted.forEach((r,i)=>[r.source_key,officeKey(r)].forEach((key,index)=>{
    if(!groups[index].has(key)) groups[index].set(key,[]);
    groups[index].get(key).push(i);
  }));
  const issues=[];
  groups.forEach((map,index)=>{
    for(const indices of map.values()) {
      if(indices.length<2)continue;
      const reason=conflictReason(indices.map(i=>sorted[i]),settings.duplicate_metres,index===0);
      if(reason)issues.push({indices,reason});
      for(const i of indices.slice(1)) union(indices[0],i);
    }
  });
  const components=new Map();
  sorted.forEach((record,i)=>{
    const root=find(i);if(!components.has(root))components.set(root,[]);components.get(root).push(record);
  });
  const reasons=new Map();
  for(const issue of issues){const root=find(issue.indices[0]);if(!reasons.has(root))reasons.set(root,new Set());reasons.get(root).add(issue.reason);}
  const accepted=[], duplicates=[], conflicts=[];
  for(const [root,members] of components){
    members.sort(preference);
    const reason=conflictReason(members,settings.duplicate_metres);
    if(reason){if(!reasons.has(root))reasons.set(root,new Set());reasons.get(root).add(reason);}
    if(reasons.has(root)){
      conflicts.push({reason_codes:[...reasons.get(root)].sort(),record_refs:members.map(r=>r.ref).sort()});continue;
    }
    const representative=members[0];
    const office_id=idFor('office',officeKey(representative));
    const acceptedRecord={...representative,office_id,members};
    accepted.push(acceptedRecord);
    for(const duplicate of members.slice(1)) duplicates.push({record_ref:duplicate.ref,accepted_office_id:office_id,
      representative_ref:representative.ref,reason_code:duplicate.source_key===representative.source_key?'SAME_SOURCE_OFFICE':'EXACT_IDENTITY_ADDRESS_NEAR_COORDINATES'});
  }
  return {accepted:accepted.sort((a,b)=>compare(a.office_id,b.office_id)),duplicates:duplicates.sort((a,b)=>compare(a.record_ref,b.record_ref)),conflicts};
}
