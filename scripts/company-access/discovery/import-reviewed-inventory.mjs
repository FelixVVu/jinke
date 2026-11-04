// Source-rebuilt bulk review import. Human choice and validation disposition are separate.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {stable,sha256} from '../common.mjs';
import {ingest,artifactNames,validateArtifacts} from '../ingest.mjs';
import {loadApproved} from '../amap/pilot3-workflow.mjs';
import {writeReviewBundle} from '../amap/console.mjs';
import {recoverCandidates,recoveryBundle} from './recover.mjs';
import {prepareTargeted,targetedBundle,validateTargeted} from './targeted.mjs';
import {validateContinuation} from './continuation.mjs';
import {attachReviewHistory} from '../../../web/src/company-access/review-history.js';
import {appendPending} from '../../../web/src/company-access/review-append.js';
import {createSession,validateSession} from '../../../web/src/company-access/review-state.js';
import {companyType,mixedCommercialType} from '../../../web/src/company-access/provider-types.js';
import {addressSignals} from '../../../web/src/company-access/review-triage.js';
import {triageItems,validateSecondPass} from '../../../web/src/company-access/review-triage.js';
import {identityAudit,coordinateCheck} from '../../../web/src/company-access/identity-audit.js';
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const equal=(a,b,reason)=>{if(stable(a)!==stable(b))throw Error(reason);};
export function acceptanceIssues(item,audit){
 const reasons=[];const r=item.row;
 if(coordinateCheck(r).status!=='CONVERSION_MATCH')reasons.push('COORDINATE_CONVERSION_MISMATCH');
 // Independent eligibility gate; an old suggestion is not a validation decision.
 const n=r.company_name||'',t=r.amap_type||'',a=addressSignals(r.address),e=item.triage.public_evidence;
 const hard=/停车|充电|食堂|咖啡|餐厅|饭店|健身|养车|汽修|民防|人防|项目部|工地|便利店|专卖店|共享空间|孵化器|公共平台/.test(n);
 if(hard)reasons.push('NON_OFFICE_PLACE');
 if(/暂停营业|关闭|搬迁|注销|建设中/.test(n))reasons.push('STALE_OR_UNCERTAIN');
 if(e&&['address_conflict','identity_conflict','relation_unresolved','non_office_place','manufacturing_only','mixed_site_office_match','registered_only'].includes(e.assessment))reasons.push('EVIDENCE_'+e.assessment.toUpperCase());
 if(r.possible_duplicate||r.duplicate_group||['PRIOR_SOURCE_CHANGED','PRIOR_INVENTORY_MATCH'].includes(item.suggestion?.reason)||item.triage.reason==='SAME_NAME_MULTIPLE_POIS')reasons.push('DUPLICATE_OR_SOURCE_CONFLICT');
 if(!companyType(r.amap_typecode)||mixedCommercialType(r.amap_typecode))reasons.push('PROVIDER_USE_UNRESOLVED');
 if(!/公司|集团|办公室|研发中心|service office/i.test(n)||/注册公司|代办|旗下|物业.*(服务|管理处)/.test(n))reasons.push('ENTITY_UNRESOLVED');
 if(a.vague||!a.core.trim())reasons.push('VAGUE_ADDRESS');
 const located=a.unit||/\d+.*(?:幢|栋|号楼|座)|(?:大厦|商务|写字楼|办公楼|研发园|总部园|展想中心|德国中心|科技园|软件园).*(?:\d|[A-Z]座)/i.test(a.core);
 if(!located&&e?.assessment!=='office_address_match')reasons.push('OFFICE_ADDRESS_DETAIL_REQUIRED');
 if(/工厂|厂区|\([^)]*厂\)|[一二三四五六]厂/i.test(n)||/170100/.test(String(r.amap_typecode)))reasons.push('FACTORY_OFFICE_USE_UNRESOLVED');
 if(/门窗|餐饮|酒店|服饰|商贸|装潢|装饰/.test(n)&&!a.office&&e?.assessment!=='office_address_match')reasons.push('STORE_OR_OFFICE_UNRESOLVED');
 for(const flag of audit?.flags||[])if(['GATE_OR_ENTRANCE','INTERSECTION_ADDRESS','ENTITY_ADDRESS_CONFLICT','ADDRESS_LOCATION_CONFLICT','POSSIBLE_DUPLICATE','NON_OFFICE_POI'].includes(flag))reasons.push(flag);
 if(audit&&/楼栋|园区|厂区|二厂|三厂/.test(audit.kind))reasons.push('PRECISE_OFFICE_USE_UNRESOLVED');
 return [...new Set(reasons)].sort();
}
export async function validateInventory(base,sessionFile){
 const areas=await read('web/public/data/reach-areas.geojson'),baseline=await loadApproved(base),session=await read(sessionFile);
 validateArtifacts(baseline.artifacts,areas);equal(ingest(baseline.envelope,areas).offices,baseline.artifacts.offices,'BASELINE_REBUILD_FAILED');
 const snapshots=await Promise.all([1,2,3].map(n=>read(path.join(base,`source-imports/pilot-${n}/provider-cache/snapshot.json`))));
 const recovered=recoverCandidates({snapshots,areas,priorDecisions:baseline.decisions});
 const recovery=recoveryBundle(recovered,baseline.artifacts.offices.features.map(f=>f.properties));
 equal(recovery.batches,(await read(path.join(base,'review-pending/pending-review-bundle.json'))).batches,'RECOVERY_SOURCE_MISMATCH');
 const extras=(await fs.readdir(path.join(base,'source-imports'))).filter(n=>n.startsWith('coverage-'));
 const retained=await Promise.all(extras.map(n=>read(path.join(base,'source-imports',n,'snapshot.json'))));
 const source=retained.find(s=>s.version==='amap-targeted-30-v1');if(!source)throw Error('MISSING_TARGETED_SNAPSHOT');validateTargeted(source,areas);
 for(const s of retained)if(s.version==='targeted-30-continuation-v1'){validateContinuation(s,areas);equal(source,s.parent,'PARENT_CHANGED');}
 const prepared=prepareTargeted(source,areas),targeted=targetedBundle(source,prepared),locked=new Set(baseline.decisions.map(d=>d.amap_poi_id));
 for(const b of targeted.batches)b.rows=b.rows.filter(i=>!locked.has(i.row.amap_poi_id));
 equal(targeted.batches,(await read(path.join(base,'review-targeted/targeted-review-bundle.json'))).batches,'TARGETED_SOURCE_MISMATCH');
 const temp=await fs.mkdtemp('offline-output/.inventory-validation-');let history;try{history=await writeReviewBundle(base,path.join(temp,'history.json'));}finally{await fs.rm(temp,{recursive:true});}
 const current=attachReviewHistory(recovery,history),combined=appendPending(current,targeted,history,createSession(current)).bundle;
 validateSession(combined,session);if(!session.reviewer.trim())throw Error('REVIEWER_REQUIRED');
 const recoveryPack=await read(path.join(base,'review-pending/second-pass.json')),targetPack=await read(path.join(base,'review-targeted/targeted-second-pass.json'));
 validateSecondPass(current,recoveryPack);validateSecondPass(await read(path.join(base,'review-targeted/targeted-review-bundle.json')),targetPack);
 const items=triageItems(combined.batches.flatMap(b=>b.rows),[...recoveryPack.evidence,...targetPack.evidence],[...recoveryPack.seeds,...targetPack.seeds]);
 const audit=identityAudit(items.map(i=>i.row)),candidates=new Map([...recovered.candidates,...prepared.candidates].map(c=>[c.amap_poi_id,c]));
 const reports=[],decisions=[],records=[];
 for(const i of items.filter(i=>!i.locked)){
  const c=candidates.get(i.row.amap_poi_id),d=session.decisions[i.key],event=d.history.at(-1);if(!c||!event||d.status==='pending')throw Error('MISSING_SOURCE_OR_HUMAN_DECISION');
  if(c.raw.source_evidence.kind!=='map_poi'||c.raw.source_evidence.reviewed!==false)throw Error('UNEXPECTED_SOURCE_EVIDENCE');
  const decision={amap_poi_id:c.amap_poi_id,decision:d.status,notes:d.notes,reviewer:event.reviewer,reviewed_at:event.at,query_ids:c.query_ids,raw_sha256:sha256(stable(c.raw))};decisions.push(decision);
  const reasons=d.status==='accept'?acceptanceIssues(i,audit[c.amap_poi_id]):[];
  const report={key:i.key,amap_poi_id:c.amap_poi_id,company_name:i.row.company_name,address:i.row.address,human_status:d.status,notes:d.notes,history:d.history,raw_sha256:decision.raw_sha256,coordinate_check:coordinateCheck(i.row),evidence:i.triage.public_evidence,reason_codes:reasons,validation_status:d.status!=='accept'?'human_excluded':reasons.length?'quarantined':'eligible'};reports.push(report);
  if(report.validation_status==='eligible')records.push({...c.raw,source_evidence:{...c.raw.source_evidence,reviewed:true,description:`Human-reviewed mapped office. Reviewer: ${event.reviewer}. Notes: ${d.notes}`}});
 }
 // Run all eligible sources through unchanged Phase 2 together with baseline. Quarantine
 // whole incoming conflict components; never remove or rewrite a baseline office.
 const envelope={...baseline.envelope,dataset_version:`reviewed-inventory-${sha256(stable(session)).slice(0,16)}`,records:[...baseline.envelope.records,...records]};
 let artifacts=ingest(envelope,areas);const priorIDs=new Set(baseline.envelope.records.map(r=>r.source_record_id)),holds=new Map();
 for(const r of artifacts.rejected.records)if(!priorIDs.has(r.raw_record.source_record_id))holds.set(r.raw_record.source_record_id,r.reason_codes);
 const original=new Map(baseline.artifacts.offices.features.map(f=>[f.id,f]));
 for(const a of artifacts.audit.accepted){const feature=artifacts.offices.features.find(f=>f.id===a.office_id);if(original.has(a.office_id)&&stable(original.get(a.office_id))!==stable(feature))for(const s of a.sources)if(!priorIDs.has(s.raw_record.source_record_id))holds.set(s.raw_record.source_record_id,['BASELINE_REPRESENTATIVE_CONFLICT']);}
 for(const r of reports)if(holds.has(r.amap_poi_id)){r.reason_codes.push(...holds.get(r.amap_poi_id));r.validation_status='quarantined';}
 envelope.records=envelope.records.filter(r=>!holds.has(r.source_record_id));artifacts=ingest(envelope,areas);validateArtifacts(artifacts,areas);
 if(artifacts.rejected.records.length)throw Error('UNRESOLVED_CANONICAL_CONFLICT');
 const final=new Map(artifacts.offices.features.map(f=>[f.id,f]));for(const [id,f]of original)equal(final.get(id),f,'BASELINE_CHANGED');
 if(artifacts.offices.features.some(f=>!f.properties.reach_minutes.includes(30)))throw Error('OUTSIDE_30_MINUTES');
 const incorporated=new Map(artifacts.audit.accepted.flatMap(a=>a.sources.map(s=>[s.raw_record.source_record_id,a.office_id])));
 for(const r of reports)if(r.validation_status==='eligible'){r.validation_status='incorporated';r.office_id=incorporated.get(r.amap_poi_id);if(!r.office_id)throw Error('UNRECONCILED_ACCEPT');}
 const report={session_sha256:sha256(await fs.readFile(sessionFile)),source_hashes:[...snapshots,source].map(s=>sha256(stable(s))),prior_offices:original.size,final_offices:final.size,net_new_offices:final.size-original.size,human_accepts:reports.filter(r=>r.human_status==='accept').length,human_rejects:reports.filter(r=>r.human_status==='reject').length,accepts_without_notes:reports.filter(r=>r.human_status==='accept'&&!r.notes.trim()).length,incorporated_accepts:reports.filter(r=>r.validation_status==='incorporated').length,quarantined_accepts:reports.filter(r=>r.validation_status==='quarantined').length,duplicates_collapsed:artifacts.review.duplicates.length-baseline.artifacts.review.duplicates.length,historical_decisions:baseline.decisions.length+decisions.length};
 return {baseline,areas,combined,session,decisions:[...baseline.decisions,...decisions],reports,report,envelope,artifacts};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){const [base,sessionFile]=process.argv.slice(2);const r=await validateInventory(base,sessionFile);await fs.writeFile('offline-output/review-import-nov3/validation-result.json',stable({...r,baseline:undefined,areas:undefined})+'\n');console.log(stable(r.report));}
