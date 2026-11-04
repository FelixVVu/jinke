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

import {identityAudit,coordinateCheck,relationshipSearchTerms} from '../web/src/company-access/identity-audit.js';
import {gcj02ToWgs84} from '../web/src/location-search.js';
test('identity/location audit checks conversion without moving, merging or changing decisions',()=>{
 const raw=[121.585,31.207],wgs=gcj02ToWgs84(...raw);
 const row={amap_poi_id:'synthetic-a',company_name:'SYNTHETIC 华虹公司',address:'Test',longitude_gcj02:raw[0],latitude_gcj02:raw[1],longitude_wgs84:wgs[0],latitude_wgs84:wgs[1],review_status:'needs_review'};
 const second={...row,amap_poi_id:'synthetic-b'},before=structuredClone([row,second]);
 const audits=identityAudit([row,second]);assert.equal(audits[row.amap_poi_id].coordinate.status,'CONVERSION_MATCH');assert(audits[row.amap_poi_id].flags.includes('POSSIBLE_DUPLICATE'));
 assert.deepEqual([row,second],before);assert.equal(coordinateCheck({...row,longitude_wgs84:raw[0],latitude_wgs84:raw[1]}).status,'CONVERSION_MISMATCH');
 assert.equal(coordinateCheck({...row,longitude_gcj02:''}).status,'RAW_COORDINATES_UNAVAILABLE');
 assert.deepEqual(relationshipSearchTerms(row),[]);
});
test('Huahong related searches preserve separate corporate entities and reject identity binding drift',()=>{
 const group={amap_poi_id:'B0LA7UOCSL',company_name:'华虹(集团)有限公司',address:'碧波路与松涛路交叉口西南120米'};
 const factory={amap_poi_id:'B0FFLEW84S',company_name:'上海华虹宏力半导体制造有限公司(二厂)',address:'张江高科技园区哈雷路288号'};
 const rows=[group,factory],before=structuredClone(rows);
 assert.equal(createCompanySearchIndex(rows)('Hua Hong').length,2);assert.equal(createReviewSearchIndex(rows.map(row=>({row})))('Huahong').length,2);
 const a=identityAudit(rows);assert.notEqual(a[group.amap_poi_id].entity,a[factory.amap_poi_id].entity);assert.deepEqual(rows,before);
 assert.deepEqual(relationshipSearchTerms({...factory,address:'Changed'}),[]);
});

import {acceptanceIssues} from '../scripts/company-access/discovery/import-reviewed-inventory.mjs';
import {candidateStatusLabel} from '../web/src/company-access/candidate-search.js';
test('bulk human accept is independently screened; missing notes do not imply rejection or verification',()=>{
 const p=gcj02ToWgs84(121.6,31.2),row={amap_poi_id:'SYNTHETIC',company_name:'SYNTHETIC 制造技术有限公司',address:'张江路505号8层803室',amap_type:'公司企业;公司;公司',amap_typecode:'170200',longitude_gcj02:121.6,latitude_gcj02:31.2,longitude_wgs84:p[0],latitude_wgs84:p[1],review_notes:''};
 const item={row,triage:{group:'exception',reason:'INDUSTRIAL_LOCATION'}};
 assert.deepEqual(acceptanceIssues(item),[]);assert(acceptanceIssues({...item,row:{...row,company_name:'SYNTHETIC 停车场'}}).includes('NON_OFFICE_PLACE'));
 assert(acceptanceIssues({...item,row:{...row,address:'路口附近'}}).includes('VAGUE_ADDRESS'));
 assert(acceptanceIssues({...item,triage:{public_evidence:{assessment:'address_conflict'}}}).includes('EVIDENCE_ADDRESS_CONFLICT'));
 assert(acceptanceIssues(item,{flags:['ENTITY_ADDRESS_CONFLICT'],kind:'公司候选'}).includes('ENTITY_ADDRESS_CONFLICT'));
});
test('quarantined human accept stays searchable with explicit label and unchanged decision',()=>{
 const i=item('held','accept');i.validation_status='quarantined';i.validation_reasons=['VAGUE_ADDRESS'];
 const bundle={schema_version:1,bundle_id:'test',batches:[{id:'test',columns:[],rows:[i]}]},before=structuredClone(bundle);
 const candidates=candidateSearchRecords(bundle,areas);assert.equal(candidates.length,1);validateCandidateSearch(candidates);
 assert.match(candidateStatusLabel(candidates[0]),/人工接受.*隔离/);assert.deepEqual(bundle,before);
});
