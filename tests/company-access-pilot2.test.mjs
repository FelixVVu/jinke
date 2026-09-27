import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';
import {planQueries,POLICY,reachLimitFor} from '../scripts/company-access/amap/plan.mjs';
import {acquire,validateSnapshot,candidatesFromCache} from '../scripts/company-access/amap/acquire.mjs';
import {sha256,stable} from '../scripts/company-access/common.mjs';
import {reviewRows,approvedFromReview,toCSV} from '../scripts/company-access/amap/review.mjs';
import {mergeReviewedPilots} from '../scripts/company-access/amap/merge-reviewed.mjs';
import {wgs84ToGcj02} from '../web/src/location-search.js';
import {searchOffices} from '../web/src/company-access/drawer.js';
const areas=JSON.parse(await fs.readFile(new URL('../web/public/data/reach-areas.geojson',import.meta.url)));
const station=[121.597836,31.2064028];
test('fixed Pilot 2 narrows grid to actual 10-minute bbox without broadening quotas',()=>{
 const p=planQueries(areas,'amap-pilot-2'),old=planQueries(areas);
 assert.equal(p.cells.length,16);assert.equal(reachLimitFor(p.policy.version),10);
 for(const key of ['max_requests','max_candidates','max_pages','page_size','pacing_ms','retry_ms','types'])assert.equal(p.policy[key],POLICY[key]);
 assert.ok(p.bbox_wgs84[0]>old.bbox_wgs84[0]);assert.ok(p.bbox_wgs84[2]<old.bbox_wgs84[2]);
 assert.throws(()=>planQueries(areas,'arbitrary'));
 assert.deepEqual(p,planQueries(areas,'amap-pilot-2'));
});
async function sample(){let calls=0;const location=wgs84ToGcj02(...station).join(',');return acquire({pilotVersion:'amap-pilot-2',env:{JINKE_AMAP_KEY:'TEST_ONLY_CREDENTIAL_123456789'},areas,collectedAt:'2026-09-26T00:00:00Z',sleep:async()=>{},fetchFn:async()=>Response.json({status:'1',pois:calls++===0?[{id:'SYNTHETIC-JINKE',name:'SYNTHETIC Office',address:'SYNTHETIC Office Address',typecode:'170200',location}]:[]})});}
test('Pilot 2 prepares pending records at Jinke; version and geometry are pinned',async()=>{
 const result=await sample();assert.equal(result.execution.api_requests_total,16);assert.equal(result.candidates.length,1);assert.equal(result.candidates[0].inside_10_minute_reach,true);assert.equal(reviewRows(result.candidates)[0].review_status,'pending');
 validateSnapshot(result.snapshot,areas);const wrong=structuredClone(result.snapshot);wrong.version='amap-pilot-1';assert.throws(()=>validateSnapshot(wrong,areas));
});
test('cross-pilot canonical deduplication retains baseline decisions and rejects unreviewed input',async()=>{
 const {snapshot,candidates}=await sample();const rows=reviewRows(candidates);rows[0].review_status='accept';
 const accepted=approvedFromReview({snapshot,areas,csv:toCSV(rows),reviewer:'Synthetic reviewer',reviewedAt:'2026-09-26T00:00:00Z'});
 const combined=mergeReviewedPilots(accepted,accepted,areas);assert.equal(combined.artifacts.offices.features.length,1);assert.deepEqual(combined.decisions,accepted.decisions);
 const unsafe=structuredClone(accepted);unsafe.decisions[0].decision='pending';assert.throws(()=>mergeReviewedPilots(accepted,unsafe,areas),{code:'UNACCEPTED_MERGE_INPUT'});
});
test('drawer search handles Unicode and address/district matching without changing records',()=>{
 const offices=[{id:'1',company_name:'ＡＢＣ 科技',address:'金科路 1号',district:'浦东新区'},{id:'2',company_name:'Other',address:'Elsewhere'}];
 assert.deepEqual(searchOffices(offices,'abc').map(o=>o.id),['1']);assert.equal(searchOffices(offices,'浦东').length,1);assert.equal(searchOffices(offices,'missing').length,0);assert.equal(offices.length,2);
});
test('Pilot 2 exact clipping excludes a valid 20-minute office; no 30-minute fallback',async()=>{
 const {snapshot}=await sample();const changed=structuredClone(snapshot);
 changed.responses[0].payload.pois[0].location=wgs84ToGcj02(121.55762647136535,31.207003066623745).join(',');
 changed.responses[0].payload_sha256=sha256(stable(changed.responses[0].payload));
 validateSnapshot(changed,areas);const prepared=candidatesFromCache(changed,areas);
 assert.equal(prepared.candidates.length,0);assert.equal(prepared.exclusions[0].reason,'OUTSIDE_10_MINUTES');
});
test('prior non-accept decisions stay locked when merging a newly accepted duplicate',async()=>{
 const {snapshot,candidates}=await sample();const rows=reviewRows(candidates);
 const options={snapshot,areas,reviewer:'Synthetic reviewer',reviewedAt:'2026-09-26T00:00:00Z'};
 rows[0].review_status='needs_review';const baseline=approvedFromReview({...options,csv:toCSV(rows)});
 rows[0].review_status='accept';const incoming=approvedFromReview({...options,csv:toCSV(rows)});
 const combined=mergeReviewedPilots(baseline,incoming,areas);
 assert.equal(combined.artifacts.offices.features.length,0);assert.equal(combined.held[0].reason,'EXISTING_DECISION_LOCKED');assert.deepEqual(combined.decisions,baseline.decisions);
});
