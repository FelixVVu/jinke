import '../../../web/src/vendor/polygon-clipping.umd.min.js';
import {wgs84ToGcj02} from '../../../web/src/location-search.js';
import {sha256,stable} from '../common.mjs';
import {baseline} from './pilot3-baseline.mjs';
export const PILOT3_POLICY=Object.freeze({version:'amap-pilot-3',rows:16,columns:16,types:'170200',page_size:25,max_pages:2,max_requests:48,max_requests_per_execution:24,max_candidates:300,pacing_ms:1500,retry_ms:3000});
const multi=f=>f.geometry.type==='Polygon'?[f.geometry.coordinates]:f.geometry.coordinates;
const area=polys=>polys.reduce((total,p)=>total+p.reduce((sum,r,i)=>sum+(i?-1:1)*Math.abs(r.slice(1).reduce((v,b,j)=>v+r[j][0]*b[1]-b[0]*r[j][1],0)/2),0),0);
export function pilot3Cells(areas){
  const reach=multi(areas.features.find(f=>f.properties.limit===30)),points=reach.flat(2),xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
  const bbox=[Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)],cells=[];
  const [w,s,e,n]=bbox,dx=(e-w)/16,dy=(n-s)/16;
  for(let row=0;row<16;row++)for(let col=0;col<16;col++){
    const b=[w+col*dx,s+row*dy,w+(col+1)*dx,s+(row+1)*dy],box=[[[b[0],b[1]],[b[2],b[1]],[b[2],b[3]],[b[0],b[3]],[b[0],b[1]]]];
    const clipped=globalThis.polygonClipping.intersection(reach,box),size=area(clipped);if(size<1e-12)continue;
    const samples=[];for(let i=0;i<=16;i++){const t=i/16;samples.push([b[0]+dx*t,b[1]],[b[0]+dx*t,b[3]],[b[0],b[1]+dy*t],[b[2],b[1]+dy*t]);}
    const gcj=samples.map(p=>wgs84ToGcj02(...p)),gx=gcj.map(p=>p[0]),gy=gcj.map(p=>p[1]),pad=.0001;
    cells.push({id:`r${row}c${col}`,bbox_wgs84:b,geometry:{type:'MultiPolygon',coordinates:clipped},reach_area_fraction:size/(dx*dy),
      polygon_gcj02:`${(Math.min(...gx)-pad).toFixed(6)},${(Math.max(...gy)+pad).toFixed(6)}|${(Math.max(...gx)+pad).toFixed(6)},${(Math.min(...gy)-pad).toFixed(6)}`});
  }
  return {bbox,cells};
}
export function planPilot3(areas){
  if(sha256(stable(areas))!==baseline.reach_sha256)throw Error('Pilot 3 geometry differs from reviewed baseline');
  const {bbox,cells}=pilot3Cells(areas),remaining=cells.map(c=>({...c,prior_poi_observations:baseline.cells[c.id]||0})),ordered=[];
  const center=c=>[(c.bbox_wgs84[0]+c.bbox_wgs84[2])/2,(c.bbox_wgs84[1]+c.bbox_wgs84[3])/2];
  const distance=(a,b)=>{a=center(a);b=center(b);return (a[0]-b[0])**2*.73+(a[1]-b[1])**2;};
  while(remaining.length){
    // Sparse first; farthest from already scheduled cells within each sparse tier.
    const tier=c=>c.prior_poi_observations===0?0:c.prior_poi_observations<=3?1:2;
    remaining.sort((a,b)=>tier(a)-tier(b)||(ordered.length?Math.min(...ordered.map(c=>distance(b,c)))-Math.min(...ordered.map(c=>distance(a,c))):b.reach_area_fraction-a.reach_area_fraction)||a.id.localeCompare(b.id));
    ordered.push(remaining.shift());
  }
  const queries=[];for(let page=1;page<=PILOT3_POLICY.max_pages;page++)for(const c of ordered){const parameters={polygon:c.polygon_gcj02,types:'170200',page_size:'25',page_num:String(page),show_fields:'indoor'};queries.push({id:sha256(stable(parameters)),cell_id:c.id,page,parameters});}
  return {policy:PILOT3_POLICY,reach_sha256:baseline.reach_sha256,baseline_sha256:sha256(stable(baseline)),bbox_wgs84:bbox,cells:ordered,queries};
}
