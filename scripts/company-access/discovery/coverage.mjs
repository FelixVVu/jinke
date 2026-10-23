import {pilot3Cells} from '../amap/pilot3-plan.mjs';
import {candidatesFromCache,validateSnapshot} from '../amap/acquire.mjs';
import {normalizeCoordinates} from '../coordinates.mjs';
import {prepareReachAreas} from '../../../web/src/company-access/model.js';
import {wgs84ToGcj02} from '../../../web/src/location-search.js';
import {providerTypes} from '../../../web/src/company-access/provider-types.js';
const contains=(b,p)=>p[0]>=b[0]&&p[0]<=b[2]&&p[1]>=b[1]&&p[1]<=b[3];
const counts=rows=>rows.reduce((a,r)=>(a[r]=(a[r]||0)+1,a),{});
export function geographicCoverage({snapshots,areas,offices,decisions,recovered,benchmarks=[]}){
  const reach=prepareReachAreas(areas),raw=new Map(),pilots=[],maxErrors=[],coordinateIndex=new Map();
  for(const snapshot of snapshots){
    validateSnapshot(snapshot,areas);const prepared=candidatesFromCache(snapshot,areas);
    const exclusions=new Map(prepared.exclusions.map(e=>[e.amap_poi_id,e.reason]));
    let outsideQuery=0;
    for(const response of snapshot.responses){const query=snapshot.plan.queries.find(q=>q.id===response.query_id),cell=snapshot.plan.cells.find(c=>c.id===query.cell_id);
      for(const poi of response.payload.pois){let location=null;
        try{const gcj=String(poi.location).split(',').map(Number);location=normalizeCoordinates({longitude:gcj[0],latitude:gcj[1],coordinate_system:'GCJ02'}).coordinates;
          const back=wgs84ToGcj02(...location);maxErrors.push(Math.max(...gcj.map((v,i)=>Math.abs(v-back[i]))));
          if(!contains(cell.bbox_wgs84.map((v,i)=>v+(i<2?-.0002:.0002)),location))outsideQuery++;
          const list=coordinateIndex.get(poi.id)||[];list.push(location);coordinateIndex.set(poi.id,list);
        }catch{}
        const observations=raw.get(poi.id)||[];observations.push({poi,location,pilot:snapshot.version,cell_id:cell.id,exclusion:exclusions.get(poi.id)||null});raw.set(poi.id,observations);
      }
    }
    pilots.push({pilot:snapshot.version,attempts:snapshot.attempts.length,responses:snapshot.responses.length,planned_cells:snapshot.plan.cells.length,
      queried_cells:new Set(snapshot.responses.map(r=>snapshot.plan.queries.find(q=>q.id===r.query_id).cell_id)).size,
      pages:counts(snapshot.responses.map(r=>snapshot.plan.queries.find(q=>q.id===r.query_id).page)),full_pages:snapshot.responses.filter(r=>r.payload.pois.length===25).length,
      ...prepared.counts,exclusions:counts(prepared.exclusions.map(e=>e.reason)),outside_requested_rectangle:outsideQuery,stop_reason:snapshot.execution?.stop_reason});
  }
  const prior=new Map(decisions.map(d=>[d.amap_poi_id,d])),recovery=new Map(recovered.candidates.map(c=>[c.amap_poi_id,c]));
  const fine=snapshots.find(s=>s.version==='amap-pilot-3');
  const features=pilot3Cells(areas).cells.map(cell=>{
    const queries=(fine?.plan.queries||[]).filter(q=>q.cell_id===cell.id),ids=new Set(queries.map(q=>q.id));
    const responses=(fine?.responses||[]).filter(r=>ids.has(r.query_id));
    const failures=(fine?.attempts||[]).filter(a=>ids.has(a.query_id)&&a.outcome!=='success');
    const observations=[...raw].filter(([,rows])=>rows.some(o=>o.location&&contains(cell.bbox_wgs84,o.location)&&reach.contains(o.location,30)));
    const full=responses.some(r=>r.payload.pois.length===25);
    const status=!responses.length?(failures.length?'failed_incomplete':'coarse_only_no_fine_query'):full?'saturated_incomplete':'sampled_partial';
    return {type:'Feature',geometry:cell.geometry,properties:{cell_id:cell.id,bbox_wgs84:cell.bbox_wgs84,status,
      pages_returned:responses.length,full_pages:responses.filter(r=>r.payload.pois.length===25).length,failed_attempts:failures.length,
      raw_unique_in_30:observations.length,approved:offices.features.filter(f=>contains(cell.bbox_wgs84,f.geometry.coordinates)).length,
      recovered_pending:observations.filter(([id])=>recovery.has(id)).length,historical_held:observations.filter(([id])=>['reject','needs_review'].includes(prior.get(id)?.decision)).length,
      prior_poi_observations:observations.length,verified_empty:false}};
  });
  const benchmark=benchmarks.map(b=>{
    // Name hits are diagnostic only; they cannot bind an identity or create aliases.
    const hits=[...raw].filter(([id,rows])=>(b.poi_ids||[]).includes(id)||(b.discovery_terms||[]).some(term=>rows.some(o=>o.poi.name?.includes(term))));
    const exact=hits.filter(([id])=>(b.poi_ids||[]).includes(id));
    return {...b,raw_name_hits:hits.map(([id,rows])=>({poi_id:id,names:[...new Set(rows.map(r=>r.poi.name))]})),
      trace:exact.map(([id,rows])=>({poi_id:id,company_name:rows[0].poi.name,address:rows[0].poi.address,typecode:rows[0].poi.typecode,
        location:rows[0].location,reach_minutes:[10,20,30].filter(n=>rows[0].location&&reach.contains(rows[0].location,n)),
        observed_in:[...new Set(rows.map(r=>r.pilot))],original_exclusions:[...new Set(rows.map(r=>r.exclusion).filter(Boolean))],
        human_decision:prior.get(id)?.decision||null,recovered_pending:recovery.has(id)})),
      stage:exact.some(([id])=>prior.get(id)?.decision==='accept')?'approved':exact.some(([id])=>recovery.has(id))?'recovered_pending':exact.some(([id])=>prior.has(id))?'historical_decision_locked':hits.length?'unresolved_name_hit':'not_returned_in_cached_queries',
      location_status:exact.length?'cached_poi_exact_membership':'unlocated_not_in_recall_denominator'};
  });
  const mismatch=offices.features.filter(f=>{let id;try{id=JSON.parse(f.properties.source_id)[1];}catch{return true;}return !(coordinateIndex.get(id)||[]).some(p=>p.every((v,i)=>Math.abs(v-f.geometry.coordinates[i])<1e-10));}).length;
  const mismatchReach=offices.features.filter(f=>JSON.stringify(f.properties.reach_minutes)!==JSON.stringify([10,20,30,40,50].filter(n=>reach.contains(f.geometry.coordinates,n)))).length;
  const recoveryReasons=counts(recovered.candidates.flatMap(c=>c.recovery.original_exclusions));
  return {schema_version:1,scope_minutes:30,notice:'采样与发现诊断，不是公司总体完整率。灰色仅表示没有细网格成功查询；旧粗网格可能覆盖。零结果不能证明无人办公。',
    pilots,summary:{approved:offices.features.length,historical_decisions:decisions.length,cells:features.length,
      fine_sampled:features.filter(f=>f.properties.pages_returned).length,fine_unqueried:features.filter(f=>f.properties.status==='coarse_only_no_fine_query').length,
      fine_failed:features.filter(f=>f.properties.status==='failed_incomplete').length,saturated:features.filter(f=>f.properties.status==='saturated_incomplete').length,verified_empty:0,
      new_pending:recovered.candidates.length,cross_source_conflicts:recovered.excluded.filter(e=>e.reason==='CROSS_SNAPSHOT_ID_CONFLICT').length,
      recovery_reasons:recoveryReasons,approved_coordinate_mismatches:mismatch,approved_reach_mismatches:mismatchReach,
      max_coordinate_roundtrip_error_degrees:Math.max(0,...maxErrors),benchmark_total:benchmark.length,benchmark_located:benchmark.filter(b=>b.trace.some(t=>t.reach_minutes.includes(30))).length,
      benchmark_approved:benchmark.filter(b=>b.stage==='approved').length,benchmark_recovered:benchmark.filter(b=>b.stage==='recovered_pending').length,
      new_api_requests:0,coverage_complete:false},
    multi_category_occurrences:[...raw.values()].flat().filter(o=>providerTypes(o.poi.typecode).length>1).length,
    benchmark,coverage:{type:'FeatureCollection',features}};
}
