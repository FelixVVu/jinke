import { prepareReachAreas } from '../../../web/src/company-access/model.js';
import { wgs84ToGcj02 } from '../../../web/src/location-search.js';
import { sha256, stable } from '../common.mjs';
export const POLICY = Object.freeze({ version: 'amap-pilot-1', rows: 4, columns: 4, types: '170200', page_size: 25, max_pages: 3, max_requests: 24, max_candidates: 200, pacing_ms: 1100, retry_ms: 2200 });
export const PILOT2_POLICY = Object.freeze({...POLICY, version:'amap-pilot-2'});
export function policyFor(version=POLICY.version){
  if(version===POLICY.version)return POLICY;
  if(version===PILOT2_POLICY.version)return PILOT2_POLICY;
  throw new TypeError('Unknown fixed pilot');
}
export const reachLimitFor = version => policyFor(version).version===PILOT2_POLICY.version?10:30;
export function planQueries(areas,version=POLICY.version) {
  const POLICY=policyFor(version);
  prepareReachAreas(areas);
  const feature = areas.features.find(f => f.properties.limit === reachLimitFor(version));
  const points = feature.geometry.coordinates.flat(feature.geometry.type === 'MultiPolygon' ? 2 : 1);
  const xs=points.map(p=>p[0]), ys=points.map(p=>p[1]);
  const bbox=[Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)];
  const cells=[];
  for(let row=0;row<POLICY.rows;row++) for(let column=0;column<POLICY.columns;column++) {
    const [w,s,e,n]=bbox, dx=(e-w)/POLICY.columns, dy=(n-s)/POLICY.rows;
    const bounds=[w+column*dx,s+row*dy,w+(column+1)*dx,s+(row+1)*dy];
    // Sample every edge before taking a GCJ bounding rectangle. A small padding
    // handles transform curvature; only the subsequent exact WGS clip defines scope.
    const samples=[];
    for(let i=0;i<=16;i++){const t=i/16; samples.push([bounds[0]+t*dx,bounds[1]],[bounds[0]+t*dx,bounds[3]],[bounds[0],bounds[1]+t*dy],[bounds[2],bounds[1]+t*dy]);}
    const gcj=samples.map(p=>wgs84ToGcj02(...p)), gx=gcj.map(p=>p[0]), gy=gcj.map(p=>p[1]);
    const pad=0.0001, polygon=`${(Math.min(...gx)-pad).toFixed(6)},${(Math.max(...gy)+pad).toFixed(6)}|${(Math.max(...gx)+pad).toFixed(6)},${(Math.min(...gy)-pad).toFixed(6)}`;
    cells.push({id:`r${row}c${column}`,bbox_wgs84:bounds,polygon_gcj02:polygon});
  }
  if(version===PILOT2_POLICY.version){
    // Visit station-adjacent cells first; keep the same bounded page-round policy.
    const station=[121.597836,31.2064028]; // ordering only; exact polygons define inclusion
    const distance=c=>((c.bbox_wgs84[0]+c.bbox_wgs84[2])/2-station[0])**2+((c.bbox_wgs84[1]+c.bbox_wgs84[3])/2-station[1])**2;
    cells.sort((a,b)=>distance(a)-distance(b)||a.id.localeCompare(b.id));
  }
  // Page rounds visit all cells before any cell's second page. Bounded sampling,
  // not exhaustive enumeration; provider weighting still biases the inventory.
  const queries=[];
  for(let page=1;page<=POLICY.max_pages;page++) for(const cell of cells){
    const parameters={polygon:cell.polygon_gcj02,types:POLICY.types,page_size:String(POLICY.page_size),page_num:String(page),show_fields:'indoor'};
    queries.push({id:sha256(stable(parameters)),cell_id:cell.id,page,parameters});
  }
  return {policy:POLICY,reach_sha256:sha256(stable(areas)),bbox_wgs84:bbox,cells,queries};
}
