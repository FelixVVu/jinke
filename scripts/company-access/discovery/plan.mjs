// Reviewable planning only. No network, secrets, approval, or Actions dispatch.
import '../../../web/src/vendor/polygon-clipping.umd.min.js';
import {pilot3Cells} from '../amap/pilot3-plan.mjs';
import {wgs84ToGcj02} from '../../../web/src/location-search.js';
import {sha256,stable} from '../common.mjs';
export const DISCOVERY_POLICY=Object.freeze({scope_minutes:30,max_attempts:48,max_attempts_per_execution:24,max_retry:1,page_size:25,max_pages:3,pacing_ms:1500,retry_ms:3000,max_candidates:300});
export function validateLeads(leads){
  const ids=new Set();for(const lead of leads){
    if(!lead.id||ids.has(lead.id)||!lead.company_name||!['official_corporate','park_directory','historical_reference','reviewed_inventory'].includes(lead.source_kind)||!lead.scope||!lead.limitations||!Array.isArray(lead.sources)||!lead.sources.length)throw Error('Invalid discovery lead');ids.add(lead.id);
    for(const source of lead.sources){const u=new URL(source.url);if(u.protocol!=='https:'||u.username||u.password||!source.title||!Number.isFinite(Date.parse(source.checked_at)))throw Error('Invalid lead evidence');}
    // A historical image/event can nominate names, never assert current occupancy.
    if(lead.source_kind==='historical_reference'&&lead.current_occupancy===true)throw Error('Historical reference cannot verify occupancy');
    if(lead.coordinates&&!lead.coordinate_system)throw Error('Unknown lead coordinate system');
  }return leads;
}
export function buildTargetedPlan({areas,priorityCellIds,leads}){
  validateLeads(leads);
  if(!Array.isArray(priorityCellIds)||priorityCellIds.length>4||new Set(priorityCellIds).size!==priorityCellIds.length)throw Error('At most four reviewed priority cells');
  const parents=pilot3Cells(areas).cells,streams=[];
  // Broad corporate discovery includes manufacturing businesses. The separate
  // research lane recovers R&D POIs; a building/park is a lead, not a company.
  for(const id of priorityCellIds){const parent=parents.find(c=>c.id===id);if(!parent)throw Error('Priority cell outside exact 30-minute scope');
    const [w,s,e,n]=parent.bbox_wgs84;
    for(let row=0;row<2;row++)for(let col=0;col<2;col++){
      const b=[w+(e-w)*col/2,s+(n-s)*row/2,w+(e-w)*(col+1)/2,s+(n-s)*(row+1)/2];
      const ring=[[[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]],[b[0],b[1]]]];
      const clipped=globalThis.polygonClipping.intersection(parent.geometry.coordinates,ring);if(!clipped.length)continue;
      const samples=[];for(let i=0;i<=16;i++){const t=i/16;samples.push([b[0]+(b[2]-b[0])*t,b[1]],[b[0]+(b[2]-b[0])*t,b[3]],[b[0],b[1]+(b[3]-b[1])*t],[b[2],b[1]+(b[3]-b[1])*t]);}
      const gcj=samples.map(p=>wgs84ToGcj02(...p)),x=gcj.map(p=>p[0]),y=gcj.map(p=>p[1]);
      const polygon=`${(Math.min(...x)-.0001).toFixed(6)},${(Math.max(...y)+.0001).toFixed(6)}|${(Math.max(...x)+.0001).toFixed(6)},${(Math.min(...y)-.0001).toFixed(6)}`;
      streams.push({id:`${id}-${row}${col}`,operation:'polygon',bbox_wgs84:b,geometry:{type:'MultiPolygon',coordinates:clipped},parameters:{polygon,types:'170000|141100',show_fields:'indoor'}});
    }
  }
  const names=leads.filter(l=>l.target_name_search===true);
  if(names.length>4)throw Error('At most four source-backed name targets per plan');
  streams.unshift(...names.map(lead=>({id:`name:${lead.id}`,operation:'text',lead_id:lead.id,parameters:{keywords:lead.company_name,region:'上海市',city_limit:'true',show_fields:'indoor'}})));
  const queries=[];
  // Up to 20 streams leave room for page 2 under a 48-attempt lifetime budget.
  // A full terminal page stays saturated/incomplete; never count as complete.
  for(let page=1;page<=DISCOVERY_POLICY.max_pages;page++)for(const stream of streams){const parameters={...stream.parameters,page_size:'25',page_num:String(page)};
    queries.push({id:sha256(stable({operation:stream.operation,parameters})),stream_id:stream.id,page,operation:stream.operation,parameters});}
  const plan={version:'company-targeted-discovery-plan-v1',execution_enabled:false,policy:DISCOVERY_POLICY,reach_sha256:sha256(stable(areas)),priority_cell_ids:priorityCellIds,leads_sha256:sha256(stable(leads)),streams,queries,
    resume_contract:'One immutable plan hash; original 48 lifetime attempts including failures; reserve before I/O; cached queries and exhausted retries skipped; same cross-cell connectivity cutoff as Pilot 3. No dispatch until this plan is bound to a separate checkpoint.',
    continuation_contract:'Only request page N after a successful full page N-1. Do not use response count as total inventory. Saturated capped streams remain incomplete; split in a separately reviewed plan.',
    scope_contract:'All returned coordinates use existing GCJ02→WGS84 and exact 30-minute clipping. Text results outside the polygon remain audit-only. No 40/50-minute discovery.'};
  return {...plan,plan_sha256:sha256(stable(plan))};
}
