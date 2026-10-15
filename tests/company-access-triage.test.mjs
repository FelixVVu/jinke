import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {secondPass,triageItems,addressSignals,sampleGroup,validateSecondPass,groupTargets,confirmGroup,isPriority} from '../web/src/company-access/review-triage.js';
import {createSession,validateSession,decide,exportRows} from '../web/src/company-access/review-state.js';
import {attachReviewHistory} from '../web/src/company-access/review-history.js';
import {prepareSecondPass} from '../scripts/company-access/amap/second-pass.mjs';
import {makeReviewBundle,validateConsoleImport} from '../scripts/company-access/amap/console.mjs';
import {acquire} from '../scripts/company-access/amap/acquire.mjs';
import {COLUMNS} from '../scripts/company-access/amap/review.mjs';
import {wgs84ToGcj02} from '../web/src/location-search.js';
const row={amap_poi_id:'SYNTHETIC',company_name:'合成测试软件有限公司',address:'测试路100号测试大厦12层',amap_type:'公司企业;公司',amap_typecode:'170200',longitude_wgs84:121.597836,latitude_wgs84:31.2064028,review_status:'pending',review_notes:''};
const make=(n=12)=>({schema_version:1,bundle_id:'synthetic',batches:[{id:'synthetic-batch',columns:COLUMNS,rows:Array.from({length:n},(_,i)=>({key:`synthetic-batch:SYNTHETIC-${i}`,locked:false,row:{...row,amap_poi_id:`SYNTHETIC-${i}`,company_name:`合成测试${i}软件有限公司`}}))}]});
const seeds=b=>({bundle_id:b.bundle_id,input_candidate_count:b.batches[0].rows.length,all_candidate_decisions_remain:'pending',records:b.batches[0].rows.map(i=>({poi_id:i.row.amap_poi_id,company_name:i.row.company_name,address:i.row.address,decision:'pending',flags:['synthetic-seed-flag']}))});
const empty={schema_version:1,bundle_id:'empty-history',batches:[]};
const evidenceFor=r=>({poi_id:r.amap_poi_id,company_name:r.company_name,address:r.address,assessment:'office_address_match',scope:'office_floor',summary:'Synthetic fixture — office floor matches',limitations:'Synthetic only, never real verification',sources:[{url:'https://example.com/synthetic',title:'Synthetic official page',checked_at:'2026-10-15'}]});
test('second pass catches the old number-plus-company false positives',()=>{
  for(const [name,address,expected]of [
    ['合成测试有限公司','测试路与示例路交叉口北100米','VAGUE_ADDRESS'],
    ['合成测试有限公司','测试大厦附近','VAGUE_ADDRESS'],
    ['合成项目部','测试路100号','PROJECT_SITE'],
    ['合成苑物业服务中心','测试路100号','ONSITE_PROPERTY'],
    ['合成图文广告','测试路100号','STORE_OR_SERVICE'],
    ['合成足道养生','测试路100号','STORE_OR_SERVICE'],
    ['合成孵化器','测试路100号','PLACE_NOT_COMPANY'],
    ['合成污水处理厂','测试路100号','FACTORY_SITE'],
    ['免费注册公司代办','测试大厦13层','AMBIGUOUS_IDENTITY'],
    ['合成工业制造有限公司','工业路100号','INDUSTRIAL_LOCATION'],
    ['合成餐饮管理有限公司','测试大厦12层','SERVICE_OR_HEADQUARTERS']
  ])assert.equal(secondPass({...row,company_name:name,address}).reason,expected,name);
  assert.equal(secondPass({...row,address:'测试路100号'}).group,'exception');
  for(const address of ['测试大厦F1层','测试大厦1楼','测试大厦B1层'])assert.equal(secondPass({...row,address}).reason,'GROUND_OR_BASEMENT');
  for(const address of ['测试大厦11层','测试大厦21楼','测试大厦F31层'])assert.equal(secondPass({...row,address}).group,'trusted');
});
test('navigation hints do not invalidate precise addresses; public office campuses need no invented floor',()=>{
  const address='测试路100号测试大厦12层（地铁2号口步行180米）';
  assert.equal(addressSignals(address).vague,false);assert.equal(secondPass({...row,address}).group,'trusted');
  const campus={...row,address:'测试路100号',company_name:'合成创新研发中心'};
  assert.equal(secondPass(campus).group,'exception');
  const e=evidenceFor(campus);assert.equal(secondPass(campus,{evidence:e}).tier,'public_address');
  for(const assessment of ['registered_only','identity_only'])assert.equal(secondPass(campus,{evidence:{...e,assessment}}).group,'exception');
  assert.match(secondPass(campus,{evidence:e}).confidence_notice,/不自动升级/);
});
test('conflicts take precedence over public matches; same names are held, never merged',()=>{
  const e=evidenceFor(row);
  assert.equal(secondPass({...row,possible_duplicate:true},{evidence:e}).reason,'DUPLICATE_OR_CONFLICT');
  assert.equal(secondPass(row,{evidence:e,prior_reason:'PRIOR_INVENTORY_MATCH'}).group,'exception');
  assert.equal(secondPass(row,{evidence:{...e,assessment:'address_conflict'}}).reason,'ADDRESS_CONFLICT');
  assert.equal(secondPass(row,{locked:true,evidence:e}).group,'history');
  const b=make(2);b.batches[0].rows[1].row.company_name=b.batches[0].rows[0].row.company_name;
  const before=structuredClone(b),items=triageItems(b.batches[0].rows);
  assert.equal(items.length,2);assert.ok(items.every(i=>isPriority(i)));assert.deepEqual(b,before);
});
test('evidence and attachment binding fail closed on stale identities, decisions or incomplete coverage',()=>{
  const incoming=make(2),seed=seeds(incoming),evidence=[evidenceFor(incoming.batches[0].rows[0].row)];
  const result=prepareSecondPass({incoming,history:empty,seed,evidence}),bundle=attachReviewHistory(incoming,empty);
  assert.equal(validateSecondPass(bundle,result.pack),result.pack);
  for(const mutate of [
    p=>p.bundle_id='wrong',p=>p.seeds.pop(),p=>p.seeds[0].decision='accept',p=>p.seeds[0].address='changed',
    p=>p.evidence[0].company_name='impostor',p=>p.evidence[0].address='other office',p=>p.evidence.push(p.evidence[0]),
    p=>p.evidence[0].sources[0].url='javascript:alert(1)',p=>p.evidence[0].sources[0].checked_at='unknown',p=>p.evidence[0].limitations=''
  ]){const p=structuredClone(result.pack);mutate(p);assert.throws(()=>validateSecondPass(bundle,p));}
  assert.throws(()=>prepareSecondPass({incoming,history:empty,seed:{...seed,bundle_id:'wrong'},evidence}));
  assert.throws(()=>prepareSecondPass({incoming,history:empty,seed,evidence:[{...evidence[0],poi_id:'not-in-batch'}]}));
});
test('second pass preserves bundle hashes, all immutable fields and pending decisions reproducibly',()=>{
  const incoming=make(3),before=structuredClone(incoming),seed=seeds(incoming);
  const a=prepareSecondPass({incoming,history:empty,seed,evidence:[]});
  assert.deepEqual(a,prepareSecondPass({incoming,history:empty,seed,evidence:[]}));assert.deepEqual(incoming,before);
  const bundle=attachReviewHistory(incoming,empty),session=createSession(bundle);
  const annotated=triageItems(bundle.batches[0].rows,a.pack.evidence,a.pack.seeds);
  assert.ok(annotated.every(i=>i.row.review_status==='pending'&&i.triage.seed_flags.length===1));
  assert.ok(Object.values(session.decisions).every(d=>d.status==='pending'&&d.history.length===0));
});
test('sampling is deterministic and bounded, covers strata, and never writes decisions',()=>{
  const b=make(30),items=triageItems(b.batches[0].rows),session=createSession(b),before=structuredClone(session);
  items[29].triage.reason='PUBLIC_OFFICE_MATCH';
  const sample=sampleGroup(items);assert.equal(sample.length,8);assert.equal(new Set(sample.map(i=>i.key)).size,8);
  assert.ok(sample.some(i=>i.key===items[29].key));assert.deepEqual(sample,sampleGroup([...items].reverse()));assert.deepEqual(session,before);
  assert.deepEqual(sampleGroup([]),[]);assert.equal(sampleGroup(items.slice(0,3)).length,3);
});
test('bulk decisions require a reviewer and explicit confirmation, retain notes, skip prior decisions atomically',()=>{
  const b=make(12);b.batches[0].rows[0].locked=true;b.batches[0].rows[0].row.review_status='accept';
  const items=triageItems(b.batches[0].rows);let session=createSession(b);
  assert.throws(()=>confirmGroup(b,session,items,'trusted',{confirmed:true}));session.reviewer='Synthetic human';
  assert.throws(()=>confirmGroup(b,session,items,'trusted'));
  session=decide(b,session,[items[1].key],'reject','Prior explicit decision');
  session=decide(b,session,[items[2].key],'pending','Do not lose my note');
  const before=structuredClone(session);assert.equal(groupTargets(items,session,'trusted').length,10);
  assert.throws(()=>confirmGroup(b,session,items,'trusted',{confirmed:true,at:'bad date'}));assert.deepEqual(session,before);
  const next=confirmGroup(b,session,items,'trusted',{confirmed:true,notes:'Checked a sample',at:'2026-10-15T08:00:00Z'});
  assert.deepEqual(next.decisions[items[0].key],before.decisions[items[0].key]);assert.deepEqual(next.decisions[items[1].key],before.decisions[items[1].key]);
  assert.match(next.decisions[items[2].key].notes,/Do not lose my note/);assert.match(next.decisions[items[2].key].notes,/SPECIFIC_MAPPED_OFFICE/);
  assert.equal(groupTargets(items,next,'trusted').length,0);assert.deepEqual(session,before);validateSession(b,JSON.parse(JSON.stringify(next)));
  assert.throws(()=>confirmGroup(b,next,items,'trusted',{confirmed:true}));
});
test('one group confirmation targets all pending group rows, not just the displayed sample, never another group',()=>{
  const b=make(14);b.batches[0].rows[12].row.address='路口附近';b.batches[0].rows[13].row.company_name='合成项目部';
  const items=triageItems(b.batches[0].rows),session=createSession(b);session.reviewer='Synthetic human';
  assert.equal(sampleGroup(groupTargets(items,session,'trusted')).length,8);
  const accepted=confirmGroup(b,session,items,'trusted',{confirmed:true});
  assert.equal(exportRows(b,accepted,'synthetic-batch').filter(r=>r.review_status==='accept').length,12);
  assert.equal(accepted.decisions[items[12].key].status,'pending');
  const held=confirmGroup(b,accepted,items,'exception',{confirmed:true}),rejected=confirmGroup(b,held,items,'exclude',{confirmed:true});
  assert.equal(rejected.decisions[items[12].key].status,'needs_review');assert.equal(rejected.decisions[items[13].key].status,'reject');
});
test('confirmed synthetic group exports through unchanged canonical importer without upgrading mapped confidence',async()=>{
  const areas=JSON.parse(readFileSync('web/public/data/reach-areas.geojson'));let calls=0;
  const {snapshot}=await acquire({pilotVersion:'amap-pilot-2',env:{JINKE_AMAP_KEY:'SYNTHETIC_ONLY'},areas,collectedAt:'2026-10-15T00:00:00Z',sleep:async()=>{},fetchFn:async()=>Response.json({status:'1',pois:calls++===0?[{id:row.amap_poi_id,name:row.company_name,address:row.address,type:row.amap_type,typecode:row.amap_typecode,location:wgs84ToGcj02(row.longitude_wgs84,row.latitude_wgs84).join(',')}]:[]})});
  const b=makeReviewBundle([snapshot],areas),items=triageItems(b.batches[0].rows,[evidenceFor(b.batches[0].rows[0].row)]),session=createSession(b);session.reviewer='Synthetic human';
  const options={snapshot,areas,priorDecisions:[],reviewedAt:'2026-10-15T08:00:00Z'};
  assert.equal(validateConsoleImport({...options,session}).approved.artifacts.offices.features.length,0);
  const next=confirmGroup(b,session,items,'trusted',{confirmed:true});assert.match(next.decisions[items[0].key].notes,/https:\/\/example.com\/synthetic/);
  const imported=validateConsoleImport({...options,session:next}).approved.artifacts.offices.features;
  assert.equal(imported.length,1);assert.equal(imported[0].properties.location_confidence,'building');
});
test('review page preloads validated pending data, confirms complete group scope and retains existing import contract',()=>{
  const ui=readFileSync('web/src/company-access/review-console.js','utf8'),html=readFileSync('scripts/company-access/review-console.html','utf8');
  assert.match(ui,/validateSecondPass\(value,pack\)/);assert.match(ui,/pending-review-bundle.json/);assert.match(ui,/confirmed:\$\('acknowledge'\).checked/);
  assert.match(ui,/包含搜索／抽查未显示的记录/);assert.match(html,/只看关键例外/);assert.match(html,/id="acknowledge" type="checkbox" required/);
  assert.doesNotMatch(ui,/innerHTML|new.*Marker|JINKE_AMAP_KEY|restapi\.amap/);
  assert.match(ui,/group='all';priority=false;\$\('queue'\).value='all'/,'Search includes locked SAP/NVIDIA history');
});
