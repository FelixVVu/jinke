import test from 'node:test';
import assert from 'node:assert/strict';
import {candidateSearchRecords,candidateFromLink,reviewCandidateHref,validateCandidateSearch} from '../web/src/company-access/candidate-search.js';
import {createCompanySearchIndex,createReviewSearchIndex} from '../web/src/company-access/search.js';
import {priorityEvidence,priorityEvidenceFor} from '../web/src/company-access/priority-evidence.js';
import {createSession} from '../web/src/company-access/review-state.js';
const areas={type:'FeatureCollection',features:[10,20,30,40,50].map(limit=>({type:'Feature',properties:{limit},geometry:{type:'Polygon',coordinates:[[[-1,-1],[1,-1],[1,1],[-1,1],[-1,-1]]]}}))};
const item=(id,status='pending')=>({key:`test:${id}`,locked:status!=='pending',row:{amap_poi_id:id,company_name:`SYNTHETIC ${id}`,address:'Test address',district:'Test',longitude_wgs84:0,latitude_wgs84:0,review_status:status,review_notes:'Keep note',amap_type:'Test company',source_reference:'https://example.invalid'}});
test('candidate index is separate, exact reach derived, nonaccept statuses retained without decision mutation',()=>{
  const bundle={schema_version:1,bundle_id:'test',batches:[{id:'test',columns:[],rows:['pending','needs_review','reject','accept'].map(s=>item(s,s))}]};
  const before=structuredClone(bundle),session=createSession(bundle),records=candidateSearchRecords(bundle,areas);
  assert.equal(records.length,3);assert(records.every(c=>c.kind==='candidate'&&c.reach_minutes.join(',')==='10,20,30,40,50'));
  assert.deepEqual(validateCandidateSearch(records),records);assert.deepEqual(bundle,before);assert.deepEqual(createSession(bundle),session);
  assert.throws(()=>validateCandidateSearch([{...records[0],review_status:'accept'}]));
  bundle.batches[0].rows[0].row.longitude_wgs84='';assert.throws(()=>candidateSearchRecords(bundle,areas),/coordinate/);
});
test('SMIC and Hua Hong searches use exact reviewed identities in both drawer and console; facilities are separate',()=>{
  for(const [id,queries]of [['B0FFFV60W5',['中芯国际','SMIC','S.M.I.C.']],['B0LA7UOCSL',['华虹','Hua Hong','ＨＵＡＨＯＮＧ']]]){
    const e=priorityEvidence.find(e=>e.poi_id===id),i=item(id);Object.assign(i.row,{company_name:e.company_name,address:e.address});
    const before=structuredClone(i);
    for(const query of queries){assert.equal(createReviewSearchIndex([i])(query).length,1);assert.equal(createCompanySearchIndex([i.row])(query).length,1);}
    assert.deepEqual(i,before);assert.equal(priorityEvidenceFor(i.row),e);
    assert.equal(priorityEvidenceFor({...i.row,address:'Changed assertion'}),null);
    assert.equal(createReviewSearchIndex([{...i,row:{...i.row,amap_poi_id:'unreviewed'}}])(queries[1]).length,0);
  }
  const restaurant=item('synthetic-restaurant');restaurant.row.company_name='中芯国际食堂';
  assert.equal(createReviewSearchIndex([restaurant])('SMIC').length,0);
});
test('map review link selects exact stable provider identity including locked records without changing decisions',()=>{
  const items=[item('synthetic-A'),item('synthetic-B','needs_review')],before=structuredClone(items);
  assert.equal(candidateFromLink(items,'?poi=synthetic-B'),items[1]);assert.equal(candidateFromLink(items,'?poi=unknown'),null);
  assert.equal(reviewCandidateHref('A&B'),'company-review.html?poi=A%26B');assert.deepEqual(items,before);
});
