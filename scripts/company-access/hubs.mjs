import { compare, distance, idFor } from './common.mjs';
import { normalizeText, addressKey } from './normalize.mjs';
const priorities={verified_building:0,mapped_building:1,reviewed_campus:2};
const hubKind=kind=>kind==='reviewed_campus'?'named_campus':'physical_building';
const pointCell=(point,size)=>{
  const lng=point[0]*Math.PI/180,lat=point[1]*Math.PI/180,r=6371008.8;
  return [r*Math.cos(lat)*Math.cos(lng),r*Math.cos(lat)*Math.sin(lng),r*Math.sin(lat)].map(n=>Math.floor(n/size));
};

export function assignHubs(records,settings){
  const assignments=new Map(),conflicts=[],registry=new Map();
  for(const record of records){
    const candidates=record.members.flatMap(r=>(r.raw.hub_candidates||[]).map(h=>({...h,record_ref:r.ref})))
      .sort((a,b)=>priorities[a.kind]-priorities[b.kind]||compare(a.id,b.id)||compare(a.record_ref,b.record_ref));
    if(!candidates.length)continue;
    const chosen=candidates[0];
    const peers=candidates.filter(c=>priorities[c.kind]===priorities[chosen.kind]);
    if(new Set(peers.map(c=>c.id)).size>1){conflicts.push({reason_codes:['AMBIGUOUS_HUB_ASSIGNMENT'],record_refs:record.members.map(r=>r.ref).sort()});continue;}
    const id=`${hubKind(chosen.kind)}:${chosen.id}`;
    assignments.set(record.office_id,{hub_id:id,hub_name:normalizeText(chosen.name),hub_kind:hubKind(chosen.kind),
      assignment_reason:chosen.kind,source_url:chosen.source_url,record_ref:chosen.record_ref});
    if(!registry.has(id))registry.set(id,[]);
    registry.get(id).push({record,chosen});
  }
  for(const members of registry.values()){
    if(new Set(members.map(({chosen})=>addressKey(chosen.name))).size>1){
      conflicts.push({reason_codes:['HUB_DEFINITION_CONFLICT'],record_refs:members.flatMap(({record})=>record.members.map(r=>r.ref)).sort()});
    }else{
      // Canonical spelling independent of which office occurred first.
      const spelling=members.map(({chosen})=>normalizeText(chosen.name)).sort(compare)[0];
      for(const {record} of members)assignments.get(record.office_id).hub_name=spelling;
    }
  }
  const conflictRefs=new Set(conflicts.flatMap(c=>c.record_refs));
  const accepted=records.filter(r=>!r.members.some(m=>conflictRefs.has(m.ref)));
  const acceptedIDs=new Set(accepted.map(r=>r.office_id));
  for(const record of records)if(!acceptedIDs.has(record.office_id))assignments.delete(record.office_id);
  if(settings.cluster_metres>0){
    const points=accepted.filter(r=>!assignments.has(r.office_id)&&r.location.location_confidence!=='approximate');
    const grid=new Map(),used=new Set();
    for(const record of points){const key=pointCell(record.coordinates,settings.cluster_metres).join(',');if(!grid.has(key))grid.set(key,[]);grid.get(key).push(record);}
    for(const seed of points){
      if(used.has(seed.office_id))continue;
      const cell=pointCell(seed.coordinates,settings.cluster_metres),members=[];
      for(let x=-1;x<=1;x++)for(let y=-1;y<=1;y++)for(let z=-1;z<=1;z++){
        for(const candidate of grid.get([cell[0]+x,cell[1]+y,cell[2]+z].join(','))||[]){
          if(!used.has(candidate.office_id)&&distance(seed.coordinates,candidate.coordinates)<=settings.cluster_metres)members.push(candidate);
        }
      }
      if(members.length<settings.cluster_min_offices)continue;
      members.sort((a,b)=>compare(a.office_id,b.office_id));
      const id=idFor('spatial-cluster',members.map(r=>r.office_id));
      for(const member of members){used.add(member.office_id);assignments.set(member.office_id,{hub_id:id,
        hub_name:`Unnamed office cluster ${id.slice(-8)}`,hub_kind:'spatial_cluster',
        assignment_reason:'DETERMINISTIC_SEED_RADIUS',seed_office_id:seed.office_id,
        radius_metres:settings.cluster_metres,min_offices:settings.cluster_min_offices});}
    }
  }
  return {accepted,assignments,conflicts};
}
