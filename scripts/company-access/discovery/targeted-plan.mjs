import fs from 'node:fs';
import '../../../web/src/vendor/polygon-clipping.umd.min.js';
import {wgs84ToGcj02} from '../../../web/src/location-search.js';
import {sha256,stable} from '../common.mjs';
import {DISCOVERY_POLICY,validateLeads} from './plan.mjs';
import {TARGETED_LEADS} from './targeted-leads.mjs';
export const CAMPAIGN='targeted-30-v1';
export const WORKFLOW_NAME='Company Access targeted 30m v1 (manual review only)';
export const TARGETED_POLICY=Object.freeze({...DISCOVERY_POLICY,version:'amap-targeted-30-v1',max_requests:48,max_requests_per_execution:24});
export const regions=JSON.parse(fs.readFileSync(new URL('./targeted-regions.json',import.meta.url),'utf8'));
export const baseline=()=>JSON.parse(fs.readFileSync(new URL('./targeted-baseline.json',import.meta.url),'utf8'));
export function targetedPlan(areas,guard=baseline()){
  validateLeads(TARGETED_LEADS);
  const f=areas.features.find(f=>f.properties.limit===30);if(!f)throw Error('Exact 30-minute geometry required');
  const reach=f.geometry.type==='Polygon'?[f.geometry.coordinates]:f.geometry.coordinates,cells=[];
  // Round-robin across the four marked regions before revisiting a region.
  for(let row=0;row<2;row++)for(let col=0;col<2;col++)for(const region of regions.regions){
    const [w,s,e,n]=region.bbox_wgs84,b=[w+(e-w)*col/2,s+(n-s)*row/2,w+(e-w)*(col+1)/2,s+(n-s)*(row+1)/2];
    const box=[[[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]],[b[0],b[1]]]];
    const clipped=globalThis.polygonClipping.intersection(reach,box);if(!clipped.length)throw Error('Priority cell does not intersect 30-minute reach');
    const samples=[];for(let i=0;i<=16;i++){const t=i/16;samples.push([b[0]+(b[2]-b[0])*t,b[1]],[b[0]+(b[2]-b[0])*t,b[3]],[b[0],b[1]+(b[3]-b[1])*t],[b[2],b[1]+(b[3]-b[1])*t]);}
    const gcj=samples.map(p=>wgs84ToGcj02(...p)),x=gcj.map(p=>p[0]),y=gcj.map(p=>p[1]);
    const polygon=`${(Math.min(...x)-.0001).toFixed(6)},${(Math.max(...y)+.0001).toFixed(6)}|${(Math.max(...x)+.0001).toFixed(6)},${(Math.min(...y)-.0001).toFixed(6)}`;
    cells.push({id:`${region.id}-${row}${col}`,region_id:region.id,label:region.label,bbox_wgs84:b,geometry:{type:'MultiPolygon',coordinates:clipped},operation:'polygon',parameters:{polygon,types:'170000|141100',show_fields:'indoor'}});
  }
  const streams=[...TARGETED_LEADS.filter(l=>l.target_name_search).map(l=>({id:`name:${l.id}`,lead_id:l.id,operation:'text',parameters:{keywords:l.company_name,region:'上海市',city_limit:'true',show_fields:'indoor'}})),...cells];
  const queries=[];for(let page=1;page<=3;page++)for(const stream of streams){const parameters={...stream.parameters,page_size:'25',page_num:String(page)};queries.push({id:sha256(stable({operation:stream.operation,parameters})),cell_id:stream.id,page,operation:stream.operation,parameters});}
  const plan={campaign:CAMPAIGN,policy:TARGETED_POLICY,reach_sha256:sha256(stable(areas)),baseline_sha256:sha256(stable(guard)),regions_sha256:sha256(stable(regions)),leads_sha256:sha256(stable(TARGETED_LEADS)),cells,streams,queries};
  return {...plan,plan_sha256:sha256(stable(plan))};
}
