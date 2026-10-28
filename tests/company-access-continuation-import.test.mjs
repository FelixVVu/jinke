import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {ingest} from '../scripts/company-access/ingest.mjs';
import {stable} from '../scripts/company-access/common.mjs';
import {importReviewedBatch} from '../scripts/company-access/discovery/import-continuation.mjs';
import {createSession,decide} from '../web/src/company-access/review-state.js';
const areas=JSON.parse(await fs.readFile('web/public/data/reach-areas.geojson'));
const date='2026-10-27T00:00:00Z';
const raw=id=>({source_record_id:id,source_namespace:'synthetic-review',company_name:`SYNTHETIC ${id}`,address:`SYNTHETIC ${id} Road 12 Floor 8`,district:'浦东新区',building_name:null,longitude:121.597836,latitude:31.2064028,coordinate_system:'WGS84',industry_code:null,sector:null,source_type:'licensed_poi',source_url:'https://example.invalid/poi',source_evidence:{kind:'map_poi',reviewed:false,description:'SYNTHETIC ONLY'},collected_at:date,verified_at:null});
const item=(batch,id,status='pending',locked=false)=>({key:`${batch}:${id}`,row:{amap_poi_id:id,company_name:`SYNTHETIC ${id}`,address:'SYNTHETIC ROAD',review_status:status,review_notes:''},locked});
function fixture(){
  const envelope={schema_version:1,dataset_kind:'candidate',dataset_version:'synthetic-import-test',records:[{...raw('OLD'),source_evidence:{...raw('OLD').source_evidence,reviewed:true}}]};
  const baseline={envelope,artifacts:ingest(envelope,areas),decisions:[{amap_poi_id:'OLD',decision:'accept',reviewer:'Test',reviewed_at:date,notes:''}]};
  const incoming={schema_version:1,bundle_id:'new',batches:[{id:'new',columns:[],rows:['A','R','N','P'].map(id=>item('new',id))}]};
  const combined={...incoming,bundle_id:'combined',batches:[...incoming.batches,{id:'old',columns:[],rows:[item('old','OLD','accept',true),item('old','PENDING')]}]};
  let session=createSession(combined);session.reviewer='Synthetic human';
  for(const [id,status]of [['A','accept'],['R','reject'],['N','needs_review']])session=decide(combined,session,[`new:${id}`],status,`Keep ${id} note`,date);
  return {baseline,areas,combined,incoming,session,candidates:['A','R','N','P'].map(id=>({amap_poi_id:id,raw:raw(id),query_ids:['synthetic-query']}))};
}
test('only explicit accepts enter canonical merge; all decisions and events are retained deterministically',()=>{
  const f=fixture(),before=stable(f),r=importReviewedBatch(f);
  assert.equal(r.artifacts.offices.features.length,2);assert.equal(r.report.net_new_offices,1);
  assert.deepEqual(r.report.review_dispositions,{accept:1,reject:1,needs_review:1,pending:1});
  assert.equal(r.decisions.length,4);assert.deepEqual(r.decisions[0],f.baseline.decisions[0]);
  assert.deepEqual(r.artifacts.offices.features.find(o=>o.id===f.baseline.artifacts.offices.features[0].id),f.baseline.artifacts.offices.features[0]);
  assert.equal(r.events[0].decision.notes,'Keep A note');assert(r.events.every(e=>e.decision.history.length===1));
  assert(r.artifacts.offices.features.every(f=>f.properties.location_confidence==='building'));
  assert.deepEqual(r.envelope.records.map(r=>r.source_record_id),['OLD','A']);
  assert.equal(stable(f),before);assert.equal(stable(importReviewedBatch(f)),stable(r));
});
test('forged acceptance, changed historical/other-batch decisions and source IDs fail closed',()=>{
  let f=fixture();f.session.decisions['new:P'].status='accept';assert.throws(()=>importReviewedBatch(f),/explicit review history/);
  f=fixture();f.session.decisions['old:OLD'].notes='changed';assert.throws(()=>importReviewedBatch(f),/locked/);
  f=fixture();f.session=decide(f.combined,f.session,['old:PENDING'],'reject','outside import',date);assert.throws(()=>importReviewedBatch(f),/OTHER_BATCH_CHANGED/);
  f=fixture();f.candidates[0].amap_poi_id='foreign';assert.throws(()=>importReviewedBatch(f),/SOURCE_CANDIDATE_MISMATCH/);
});
test('human acceptance cannot bypass geometry, coordinate or evidence validation',()=>{
  let f=fixture();f.candidates[0].raw.coordinate_system='unknown';assert.throws(()=>importReviewedBatch(f),/CANONICAL_VALIDATION_FAILED/);
  f=fixture();f.candidates[0].raw.longitude=120;assert.throws(()=>importReviewedBatch(f),/ACCEPT_OUTSIDE_30_MINUTES/);
  f=fixture();f.candidates[0].raw.source_evidence.kind='registered_address';assert.throws(()=>importReviewedBatch(f),/UNEXPECTED_SOURCE_EVIDENCE/);
});
test('exact duplicate offices collapse; conflicting coordinates never displace an approved office',()=>{
  let f=fixture();f.session=decide(f.combined,f.session,['new:P'],'accept','same physical office',date);
  f.candidates[3].raw={...f.candidates[0].raw,source_record_id:'P'};
  const r=importReviewedBatch(f);assert.equal(r.report.human_accepts,2);assert.equal(r.report.net_new_offices,1);assert.equal(r.report.duplicates_collapsed,1);
  f=fixture();f.candidates[0].raw={...f.candidates[0].raw,company_name:'SYNTHETIC OLD',address:raw('OLD').address,longitude:121.600};
  assert.throws(()=>importReviewedBatch(f),/BASELINE_OFFICE_CONFLICT_REQUIRES_REVIEW/);
});
