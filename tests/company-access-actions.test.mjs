import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile,rm,writeFile,lstat} from 'node:fs/promises';
import {executePilot,requireManualReviewRun,assertKeyFree,stageArtifact,ARTIFACT_FILES} from '../scripts/company-access/amap/actions-pilot.mjs';
const context={GITHUB_ACTIONS:'true',GITHUB_EVENT_NAME:'workflow_dispatch',GITHUB_REPOSITORY:'FelixVVu/jinke',GITHUB_REF:'refs/heads/review/company-access-scaffold',GITHUB_RUN_ATTEMPT:'1'};
const root=new URL('../offline-output/company-access/',import.meta.url);
const key='SYNTHETIC_ACTIONS_TEST_CREDENTIAL_123';
test('manual adapter refuses production, automatic events, forks and reruns',()=>{
  requireManualReviewRun(context);
  for(const [field,value] of [['GITHUB_ACTIONS','false'],['GITHUB_EVENT_NAME','push'],['GITHUB_EVENT_NAME','pull_request'],['GITHUB_REPOSITORY','other/jinke'],['GITHUB_REF','refs/heads/main'],['GITHUB_RUN_ATTEMPT','2']])assert.throws(()=>requireManualReviewRun({...context,[field]:value}),{code:'MANUAL_REVIEW_BRANCH_ONLY'});
});
test('missing secret fails before a provider request or artifact creation',async()=>{
  await assert.rejects(executePilot({context,key:undefined,dependencies:{fetchFn:()=>assert.fail('No API request allowed')}}),{code:'AMAP_NOT_CONFIGURED'});
});
test('artifact gate rejects raw, escaped and encoded credential representations',()=>{
  assertKeyFree('safe content',key);
  for(const value of [key,encodeURIComponent(key),Buffer.from(key).toString('base64')])assert.throws(()=>assertKeyFree(value,key),{code:'UNSAFE_ARTIFACT'});
  assert.throws(()=>assertKeyFree('prefix a%2Fb suffix','a/b'),{code:'UNSAFE_ARTIFACT'});
});
test('manual adapter reuses real preparation with mocked POIs and uploads only pending review outputs',async()=>{
  let calls=0;const folders=['pilot-1-checkpoint','pilot-1','pilot-1-artifact','unsafe-artifact'];
  for(const folder of folders){
    await assert.rejects(lstat(new URL(folder+'/',root)),{code:'ENOENT'},'Refuse to touch existing pilot outputs');
  }
  try{
    const result=await executePilot({context,key,collectedAt:'2026-09-22T00:00:00Z',dependencies:{sleep:async()=>{},fetchFn:async()=>Response.json({status:'1',pois:calls++===0?[{id:'SYNTHETIC-POI',name:'SYNTHETIC Company',address:'SYNTHETIC Address',typecode:'170200',type:'公司',adname:'浦东新区',adcode:'310115',location:'121.6020353173734,31.204188903093062'}]:[]})}});
    assert.equal(calls,16);assert.equal(result.report.candidate_review_count,1);assert.equal(result.report.stop_reason,'PLAN_COMPLETE');
    const artifact=new URL('pilot-1-artifact/',root);const rows=JSON.parse(await readFile(new URL('review/amap-office-review.json',artifact)));
    assert.equal(rows[0].review_status,'pending');
    for(const path of ARTIFACT_FILES)assertKeyFree(await readFile(new URL(path,artifact)),key);
    assert.equal(ARTIFACT_FILES.filter(f=>f.startsWith('provider-cache/')).length,1);
    await writeFile(new URL('pilot-1/review/amap-office-review.csv',root),key);
    await assert.rejects(stageArtifact({source:new URL('pilot-1/',root).pathname,target:new URL('unsafe-artifact/',root).pathname,key}),{code:'UNSAFE_ARTIFACT'});
  }finally{for(const folder of folders)await rm(new URL(folder+'/',root),{recursive:true,force:true});}
});
test('workflow exposes only manual dispatch, no inputs, one step secret, fixed review branch and safe upload directory',async()=>{
  const yaml=await readFile(new URL('../.github/workflows/company-access-amap-pilot.yml',import.meta.url),'utf8');
  assert.match(yaml,/on:\n  workflow_dispatch:\n/);assert.doesNotMatch(yaml,/\n  (push|pull_request|schedule|workflow_call|repository_dispatch):/);
  assert.doesNotMatch(yaml,/inputs:|pages: write|id-token: write|deploy-pages|AMAP_WEB_SERVICE_KEY/);
  assert.equal(yaml.match(/secrets\.JINKE_AMAP_KEY/g).length,1);
  assert.match(yaml,/github.run_attempt == 1/);assert.match(yaml,/persist-credentials: false/);
  assert.match(yaml,/path: offline-output\/company-access\/pilot-1-artifact\//);
  assert.match(yaml,/steps.pilot.outputs.artifact_ready == 'true'/);
});
