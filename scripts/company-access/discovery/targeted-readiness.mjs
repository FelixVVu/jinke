// Offline preflight only. Requires the private approved archive and pending bundle.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {stable,sha256} from '../common.mjs';
import {loadApproved} from '../amap/pilot3-workflow.mjs';
import {validateArtifacts} from '../ingest.mjs';
import {buildBaseline} from './targeted-baseline.mjs';
import {baseline,targetedPlan,TARGETED_POLICY,regions} from './targeted-plan.mjs';
import {prepareTargeted,targetedReport} from './targeted.mjs';
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const inside=(bbox,p)=>p[0]>=bbox[0]&&p[0]<=bbox[2]&&p[1]>=bbox[1]&&p[1]<=bbox[3];
const areaKm2=polygons=>polygons.reduce((total,p)=>total+p.reduce((sum,r,i)=>sum+(i?-1:1)*Math.abs(r.slice(1).reduce((v,b,j)=>v+r[j][0]*b[1]-b[0]*r[j][1],0)/2),0),0)*111.32**2*Math.cos(31.2*Math.PI/180);
export async function readiness(base,pendingRoot,output){
  const areas=await read('web/public/data/reach-areas.geojson'),approved=await loadApproved(base);validateArtifacts(approved.artifacts,areas);
  const pending=await read(path.join(pendingRoot,'pending-review-bundle.json'));
  const snapshots=await Promise.all([1,2,3].map(n=>read(path.join(base,`source-imports/pilot-${n}/provider-cache/snapshot.json`))));
  const calculated=buildBaseline({decisions:approved.decisions,offices:approved.artifacts.offices,pending,snapshots});
  if(stable(calculated)!==stable(baseline()))throw Error('BASELINE_CHANGED: do not dispatch this fixed campaign');
  const plan=targetedPlan(areas),snapshot={version:TARGETED_POLICY.version,collected_at:'2026-10-23T00:00:00Z',plan,responses:[],attempts:[],execution:{api_requests_total:0,api_requests_this_execution:0,stop_reason:'READY_NOT_DISPATCHED'}};
  const report=targetedReport(snapshot,prepareTargeted(snapshot,areas)),previous=await read(path.join(pendingRoot,'coverage-diagnostics.json'));
  report.baseline_regions=regions.regions.map(region=>({id:region.id,label:region.label,
    approved:approved.artifacts.offices.features.filter(f=>inside(region.bbox_wgs84,f.geometry.coordinates)).length,
    pending_recovery:pending.batches.flatMap(b=>b.rows).filter(i=>inside(region.bbox_wgs84,[+i.row.longitude_wgs84,+i.row.latitude_wgs84])).length,
    clipped_area_km2:areaKm2(plan.cells.filter(c=>c.region_id===region.id).flatMap(c=>c.geometry.coordinates))}));
  report.previous_benchmark=previous.benchmark;report.previous_summary=previous.summary;
  const reach=areas.features.find(f=>f.properties.limit===30).geometry;
  report.priority_footprint={approx_km2:report.baseline_regions.reduce((n,r)=>n+r.clipped_area_km2,0),reach_km2:areaKm2(reach.type==='Polygon'?[reach.coordinates]:reach.coordinates),method:'planar lon/lat area scaled at latitude 31.2; diagnostics only, not membership'};
  report.inputs={approved_sha256:calculated.approved_sha256,ledger_sha256:calculated.ledger_sha256,pending_sha256:calculated.pending_sha256,snapshot_sha256:snapshots.map(s=>sha256(stable(s))),plan_sha256:plan.plan_sha256};
  await fs.mkdir(output);await fs.writeFile(path.join(output,'targeted-readiness.json'),stable(report)+'\n',{flag:'wx'});await fs.writeFile(path.join(output,'targeted-plan.json'),stable(plan)+'\n',{flag:'wx'});
  return {counts:calculated.counts,regions:report.baseline_regions,footprint:report.priority_footprint,previous_benchmark:previous.summary,plan_sha256:plan.plan_sha256};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){const [base,pending,output]=process.argv.slice(2);if(!output||path.dirname(path.resolve(output))!==path.resolve('offline-output/company-access'))throw Error('Usage: targeted-readiness.mjs APPROVED_ROOT PENDING_ROOT FRESH_OFFLINE_OUTPUT');console.log(stable(await readiness(base,pending,output)));}
