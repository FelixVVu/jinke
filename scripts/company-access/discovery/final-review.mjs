// Offline final-artifact preparation only. No network and no decision writes.
import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {stable,sha256} from '../common.mjs';
import {validateContinuation,prepareContinuation,continuationReport} from './continuation.mjs';
import {TARGETED_LEADS} from './targeted-leads.mjs';
import {TRIAGE_VERSION,triageItems,validateSecondPass,isPriority} from '../../../web/src/company-access/review-triage.js';
export function finalReview(snapshot,areas){
  validateContinuation(snapshot,areas);
  if(snapshot.execution?.stop_reason!=='PLAN_COMPLETE')throw Error('Final completed checkpoint required');
  const p=prepareContinuation(snapshot,areas),pack=structuredClone(p.pack);
  for(const seed of pack.seeds)seed.flags.push('CONTINUATION_FINAL_REVIEW_V1');
  for(const i of p.bundle.batches[0].rows){
    if(pack.evidence.some(e=>e.poi_id===i.row.amap_poi_id))continue;
    const lead=TARGETED_LEADS.find(l=>['smic','huahong','usi','amd','omnivision'].includes(l.id)&&l.terms.some(t=>i.row.company_name.toLowerCase().includes(t.toLowerCase())));
    if(!lead)continue;
    pack.evidence.push({poi_id:i.row.amap_poi_id,company_name:i.row.company_name,address:i.row.address,assessment:'relation_unresolved',summary:'发现品牌相关地点；公司、园区、楼栋与附属设施不能互相替代。',scope:lead.address_lead,limitations:lead.limitations,sources:lead.sources});
  }
  validateSecondPass(p.bundle,pack);const items=triageItems(p.bundle.batches[0].rows,pack.evidence,pack.seeds);
  const report=continuationReport(snapshot,p),count=g=>items.filter(i=>i.triage.group===g).length;
  report.review_ready={groups:{trusted:count('trusted'),exception:count('exception'),exclude:count('exclude')},priority_exceptions:items.filter(isPriority).length,analyzed:items.length,automatic_accepts:0};
  report.acquisition_complete=true;
  report.benchmark_findings=TARGETED_LEADS.filter(l=>['smic','huahong','usi','amd','omnivision'].includes(l.id)).map(l=>{
    const pois=[...new Map(snapshot.responses.flatMap(r=>r.payload.pois).filter(p=>l.terms.some(t=>p.name.toLowerCase().includes(t.toLowerCase()))).map(p=>[p.id,p])).values()];
    const dispositions=pois.map(poi=>({id:poi.id,name:poi.name,reason:p.exclusions.find(e=>e.amap_poi_id===poi.id)?.reason||'NEW_PENDING'}));
    const descriptions={smic:'中芯国际主地点与SO8楼已在早期待审中，不重复新增；园区入口不是已核实办公室。',huahong:'集团、宏力厂区、科技园楼栋与停车设施分别保留；不能因制造业身份一律排除或把园区当作公司。',usi:'张东路1558号相关POI已在早期待审中。盛夏路169号销售办公室的定向搜索仍返回原厂区，未获得独立销售办公室POI。',amd:'两条AMD POI已返回，均在精确30分钟范围外。张东路1387号与官网地址相符，但不能绕过范围裁剪；荣科路118号也不能当作官网其他地址。',omnivision:'豪威集团稳定ID的来源字段变化已隔离，历史决定不覆盖；新园区、西塔和附属设施不能当作新增公司办公室。'};
    return {name:l.company_name,status:'发现与确认分离',detail:descriptions[l.id]+' '+dispositions.map(d=>`${d.name}: ${d.reason}`).join('；'),poi_ids:pois.map(p=>p.id),confirmed_offices:0,sources:l.sources};
  });
  return {bundle:{...p.bundle,second_pass:pack,coverage:report.coverage,discovery_report:report},pack,report,verification:{snapshot_sha256:sha256(stable(snapshot)),rows:items.length,status:'pending',groups:report.review_ready.groups}};
}
export async function prepareFinal(input,output){
  const read=async f=>JSON.parse(await fs.readFile(f,'utf8'));
  const snapshot=await read(path.join(input,'provider-cache/snapshot.json')),areas=await read('web/public/data/reach-areas.geojson');
  const original=prepareContinuation(validateContinuation(snapshot,areas),areas);
  if(stable(original.candidates)!==stable(await read(path.join(input,'normalized/candidates.json')))||stable(original.bundle.batches)!==stable((await read(path.join(input,'review/review-bundle.json'))).batches))throw Error('Artifact differs from source-rebuilt records');
  const result=finalReview(snapshot,areas);await fs.mkdir(output);
  for(const [name,value]of Object.entries({'continuation-review-bundle.json':result.bundle,'targeted-readiness.json':result.report,'verification.json':result.verification}))await fs.writeFile(path.join(output,name),stable(value)+'\n',{flag:'wx'});
  return result.verification;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){const [input,output]=process.argv.slice(2);if(!output||path.dirname(path.resolve(output))!==path.resolve('offline-output/company-access'))throw Error('Fresh offline output required');console.log(stable(await prepareFinal(input,output)));}
