// Suggestion-only second pass. Never writes a review decision or canonical identity.
import {validateBundle,validateSession,decide} from './review-state.js';
import {providerTypes,corporateType,companyType,mixedCommercialType} from './provider-types.js';
export const TRIAGE_VERSION='company-review-triage-v3';
export const GROUPS={trusted:'可信候选',exception:'重点核实',exclude:'建议排除',history:'历史锁定',all:'全部记录'};
export const REASONS={
  DUPLICATE_OR_CONFLICT:'存在重复或来源冲突，不能批量接受',PRIOR_SOURCE_CHANGED:'历史来源字段有变化',PRIOR_INVENTORY_MATCH:'与历史已接受办公室名称、地址一致',
  SAME_NAME_MULTIPLE_POIS:'同名多个 POI，须区分不同办公室与重复点',UNCERTAIN_LOCATION:'坐标或位置不明确',STALE_OR_UNCERTAIN:'存在过期、搬迁或不确定提示',
  PROJECT_SITE:'施工项目部／工地，不是稳定公司办公室',ONSITE_PROPERTY:'小区物业服务点／管理处，不是企业总部办公室',STORE_OR_SERVICE:'名称明确指向门店或到店服务',
  PLACE_NOT_COMPANY:'园区、共享空间、站点或入口，不是可识别的独立公司办公室',FACTORY_SITE:'明确工厂／生产点，不作为办公地点',
  NON_OFFICE_INFRASTRUCTURE:'停车、充电、出入口或民防设施，不是公司办公室',BUILDING_NOT_OFFICE:'楼栋／园区位置不能单独证明一家公司的办公地点',
  VAGUE_ADDRESS:'地址只有路口、方位、附近或地标，缺少具体办公位置',AMBIGUOUS_IDENTITY:'公司身份不完整或名称像营销关键词',
  INDUSTRIAL_LOCATION:'工业活动与办公用途未区分',SERVICE_OR_HEADQUARTERS:'不能区分门店服务与管理办公室',ADDRESS_DETAIL:'只有门牌／楼宇信息，缺少办公用途依据',
  ADDRESS_CONFLICT:'公开资料与 POI 地址／楼层／机构口径不一致',RELATION_UNRESOLVED:'存在关联名称或重复计数风险，未自动合并',
  GROUND_OR_BASEMENT:'一层／地下层可能是门店或楼宇默认位置，需进一步区分',
  MIXED_SITE_LOCATION:'同址有总部／研发与生产活动，需确认办公位置；不是制造业一律排除',
  MIXED_PROVIDER_CATEGORY:'多个 POI 类别含公司与服务／商业用途，需要核实具体办公用途',
  PUBLIC_OFFICE_MATCH:'公开办公地址与该 POI 相符',SPECIFIC_MAPPED_OFFICE:'公司身份、具体楼层和办公地址相互一致',HISTORICAL_LOCK:'已有人工决定，保持锁定'
};
export const normalizeTriage=value=>String(value||'').normalize('NFKC').toLowerCase().replace(/\s+/gu,'').trim();
export function addressSignals(value){
  // A parenthesized metro/walking hint is navigation, not the office address.
  const core=String(value||'').normalize('NFKC').replace(/\([^)]*(地铁|步行|近)[^)]*\)/gu,'');
  return {core,vague:/交叉口|附近|门旁|最后面|[东西南北]门[东西南北]|[东西南北]{1,2}\d+米/u.test(core),
    unit:/(?:\d+|[一二三四五六七八九十]+)(?:层|楼(?!宇)|室|单元)|\d{3,}[A-Za-z]?(?:室|单元)/u.test(core),
    office:/大厦|商务|金融广场|金控广场|商厦|写字楼|研发园|总部园|创芯天地|众创|办公/u.test(core),
    industrial:/创业路|利航路|华东路|建业路|工业|厂区|村|宅|别墅/u.test(core)};
}
export function secondPass(row,context={}){
  const name=String(row.company_name||''),type=String(row.amap_type||''),address=addressSignals(row.address);
  const evidence=context.evidence||null;
  const result=(group,reason,tier='rule')=>({group,disposition:group==='trusted'?'accept':group==='exclude'?'reject':'needs_review',reason,explanation:REASONS[reason],tier,version:TRIAGE_VERSION,
    provider_fields:{name,address:row.address,type,typecode:row.amap_typecode},seed_flags:context.seed_flags||[],public_evidence:evidence,
    confidence_notice:'接受后仍为 reviewed mapped office；公开资料不自动升级为 verified physical office。'});
  if(context.locked)return result('history','HISTORICAL_LOCK');
  // Final continuation review only: do not reinterpret earlier batches.
  if(context.seed_flags?.includes('CONTINUATION_FINAL_REVIEW_V1')){
    if(/停车场|充电站|民防工程|人防工程|快递柜|迷你仓/u.test(name))return result('exclude','NON_OFFICE_INFRASTRUCTURE');
    if(/暂停营业|停业|歇业|已搬迁|建设中/u.test(name))return result('exception','STALE_OR_UNCERTAIN','public_exception');
  }

  if(row.possible_duplicate===true||row.possible_duplicate==='true'||row.duplicate_group||row.provider_conflict)return result('exception','DUPLICATE_OR_CONFLICT');
  if(['PRIOR_SOURCE_CHANGED','PRIOR_INVENTORY_MATCH'].includes(context.prior_reason))return result('exception',context.prior_reason);
  if(context.same_name_multiple&&!context.seed_flags?.includes('TARGETED_PRECISION_V1'))return result('exception','SAME_NAME_MULTIPLE_POIS');
  if(!row.longitude_wgs84||!row.latitude_wgs84||!Number.isFinite(+row.longitude_wgs84)||!Number.isFinite(+row.latitude_wgs84))return result('exception','UNCERTAIN_LOCATION');
  if(evidence&&['address_conflict','identity_conflict','relation_unresolved'].includes(evidence.assessment))return result('exception',evidence.assessment==='relation_unresolved'?'RELATION_UNRESOLVED':'ADDRESS_CONFLICT','public_exception');
  if(/搬迁|注销|关闭|待核实|过期|closed|stale/iu.test(name+' '+(row.review_notes||'')))return result('exception','STALE_OR_UNCERTAIN');
  // Scoped to the targeted campaign: original recovery suggestions remain stable.
  // A brand in a facility name does not establish a company office.
  if(context.seed_flags?.includes('TARGETED_PRECISION_V1')){
    if(/停车场|充电站|民防工程|人防工程/u.test(name)||providerTypes(row.amap_typecode).some(t=>/^(15090|0111|2004)/.test(t)))return result('exclude','NON_OFFICE_INFRASTRUCTURE');
    if(/食堂|咖啡|冒菜|养车|汽车维修|便利店|餐厅|餐饮店/u.test(name)||(!corporateType(row.amap_typecode)&&providerTypes(row.amap_typecode).some(t=>/^(05|06|0104|0105|03)/.test(t))))return result('exclude','STORE_OR_SERVICE');
    if(/物业$/u.test(name))return result('exclude','ONSITE_PROPERTY');
    if(providerTypes(row.amap_typecode).some(t=>/^120[12]/.test(t))||/先锋站|科创中心|医药科技园|引创空间|盛创中心|Co\.Lab/iu.test(name))return result('exception','BUILDING_NOT_OFFICE');
    if(context.seed_flags.includes('POSSIBLE_SHARED_OFFICE'))return result('exception','RELATION_UNRESOLVED');
    if(/(?<!\d)1\s*[-~至]\s*\d+\s*(层|楼)/u.test(address.core))return result('exception','GROUND_OR_BASEMENT');
  }
  if(context.same_name_multiple)return result('exception','SAME_NAME_MULTIPLE_POIS');
  if(/项目部|项目办公室|工地|地块项目|中心项目|project office/iu.test(name))return result('exclude','PROJECT_SITE');
  if(/物业.*(管理处|服务中心|办公室)|小区物业|豪庭物业|苑物业|四季物业|^(汤臣豪庭物业|安培物业)$/u.test(name))return result('exclude','ONSITE_PROPERTY');
  if(/足道|养生|餐厅|饭店|健身|专卖店|便利店|汽车修理|车主服务中心|图文广告|书法|美术|生日派对|餐饮.*(分店|路店)|装饰.*店\)|装潢.*店\)/u.test(name)||(!corporateType(row.amap_typecode)&&providerTypes(row.amap_typecode).some(t=>/^(05|06|07)/.test(t))))return result('exclude','STORE_OR_SERVICE');
  if(/污水处理厂/u.test(name)&&evidence?.assessment!=='mixed_site_office_match')return result('exclude','FACTORY_SITE');
  if(/孵化器|商务空间|公共平台|公共服务|\([东南西北正]门\)|集电港站/u.test(name))return result('exclude','PLACE_NOT_COMPANY');
  if(evidence?.assessment==='non_office_place')return result('exclude','PLACE_NOT_COMPANY','public_exception');
  if(evidence?.assessment==='manufacturing_only')return result('exclude','FACTORY_SITE','public_exception');
  if(evidence?.assessment==='mixed_site_office_match')return result('exception','MIXED_SITE_LOCATION','public_exception');
  if(!corporateType(row.amap_typecode))return result('exception','AMBIGUOUS_IDENTITY');
  if(evidence?.assessment==='office_address_match')return result('trusted','PUBLIC_OFFICE_MATCH','public_address');
  if(/工厂|厂区|factory|\([^)]*厂\)/iu.test(name)||providerTypes(row.amap_typecode).includes('170100'))return result('exception','MIXED_SITE_LOCATION');
  if(mixedCommercialType(row.amap_typecode))return result('exception','MIXED_PROVIDER_CATEGORY');
  if(!companyType(row.amap_typecode))return result('exception','AMBIGUOUS_IDENTITY');
  if(address.vague||!address.core.trim())return result('exception','VAGUE_ADDRESS');
  if(/注册公司|代办|财务记账|专注公装|旗下$/u.test(name)||!/有限公司|股份公司|集团|分公司/u.test(name))return result('exception','AMBIGUOUS_IDENTITY');
  if(/(?<!\d)(?:F?1|一)(?:层|楼)(?!\d)|B\d+层|地下/iu.test(address.core))return result('exception','GROUND_OR_BASEMENT');
  if(/餐饮|酒店|物业|教育|服饰|门窗|装潢|装饰|商贸/u.test(name)&&!address.office)return result('exception','SERVICE_OR_HEADQUARTERS');
  if(/餐饮|酒店用品|门业|门窗|配餐|保安/u.test(name))return result('exception','SERVICE_OR_HEADQUARTERS');
  if((address.industrial||/制造|生产|包装|金属制品|塑料|机械|化工|工业/u.test(name+' '+type))&&!address.office)return result('exception','INDUSTRIAL_LOCATION');
  if(address.unit&&(address.office||/信息|软件|科技|资产|投资|证券|咨询|设计|通信/u.test(name)))return result('trusted','SPECIFIC_MAPPED_OFFICE','mapped_consistent');
  return result('exception','ADDRESS_DETAIL');
}
export function triageItems(items,evidence=[],seeds=[]){
  const map=new Map(evidence.map(e=>[e.poi_id,e])),seedMap=new Map(seeds.map(e=>[e.poi_id,e]));
  const names=new Map();for(const i of items){const n=normalizeTriage(i.row.company_name),ids=names.get(n)||new Set();ids.add(i.row.amap_poi_id);names.set(n,ids);}
  return items.map(i=>{const e=map.get(i.row.amap_poi_id),s=seedMap.get(i.row.amap_poi_id);
    if(e&&(e.company_name!==i.row.company_name||e.address!==i.row.address))throw Error('Evidence identity/address mismatch');
    return {...i,triage:secondPass(i.row,{locked:i.locked,prior_reason:i.suggestion?.reason,same_name_multiple:names.get(normalizeTriage(i.row.company_name)).size>1,evidence:e,seed_flags:s?.flags})};
  });
}
export const isPriority=i=>i.triage.group==='exception'&&(i.triage.tier==='public_exception'||['DUPLICATE_OR_CONFLICT','SAME_NAME_MULTIPLE_POIS','PRIOR_INVENTORY_MATCH','PRIOR_SOURCE_CHANGED'].includes(i.triage.reason));
const ASSESSMENTS=['office_address_match','identity_only','registered_only','address_conflict','identity_conflict','relation_unresolved','non_office_place','mixed_site_office_match','manufacturing_only'];
export function validateSecondPass(bundle,pack){
  validateBundle(bundle);
  if(pack?.schema_version!==1||![TRIAGE_VERSION,'company-review-triage-v2'].includes(pack.version)||pack.bundle_id!==bundle.bundle_id||!Array.isArray(pack.seeds)||!Array.isArray(pack.evidence))throw Error('Second-pass bundle mismatch');
  const rows=bundle.batches.flatMap(b=>b.rows),index=new Map(rows.map(i=>[i.row.amap_poi_id,i]));
  const check=(records,evidence)=>{
    const ids=new Set();for(const r of records){const i=index.get(r.poi_id);
      if(ids.has(r.poi_id)||!i||i.locked||i.row.company_name!==r.company_name||i.row.address!==r.address)throw Error('Evidence/seed identity or address mismatch');ids.add(r.poi_id);
      if(evidence){
        if(!ASSESSMENTS.includes(r.assessment)||!r.summary||!r.scope||!r.limitations||!Array.isArray(r.sources)||!r.sources.length)throw Error('Incomplete public evidence');
        for(const s of r.sources){const u=new URL(s.url);if(u.protocol!=='https:'||u.username||u.password||!s.title||!Number.isFinite(Date.parse(s.checked_at)))throw Error('Invalid evidence source');}
      }else if(r.decision!=='pending'||!Array.isArray(r.flags))throw Error('Triage input is suggestion-only');
    }return ids;
  };
  check(pack.evidence,true);const covered=check(pack.seeds,false);
  if(rows.filter(i=>!i.locked).some(i=>!covered.has(i.row.amap_poi_id)))throw Error('Incomplete second-pass coverage');
  return pack;
}
export function groupTargets(items,session,group){
  if(!['trusted','exception','exclude'].includes(group))return [];
  return items.filter(i=>!i.locked&&i.triage.group===group&&session.decisions[i.key]?.status==='pending');
}
// The only bulk-write entry point requires an explicit human confirmation.
// Previously decided rows (including notes/history) are never bulk-overwritten.
export function confirmGroup(bundle,session,items,group,{confirmed=false,notes='',at=new Date().toISOString()}={}){
  validateSession(bundle,session);
  if(!confirmed||!session.reviewer.trim())throw Error('请填写审核人，并明确确认本组决定');
  const targets=groupTargets(items,session,group);if(!targets.length)throw Error('本组没有尚未决定的记录');
  const decision={trusted:'accept',exception:'needs_review',exclude:'reject'}[group];
  let next=session;
  for(const i of targets){
    const links=(i.triage.public_evidence?.sources||[]).map(s=>s.url).join(' ');
    const note=[next.decisions[i.key].notes,notes,`[${TRIAGE_VERSION} · 人工批量确认] ${i.triage.reason}: ${i.triage.explanation}`,links].filter(Boolean).join('\n');
    next=decide(bundle,next,[i.key],decision,note,at);
  }
  return next;
}
// Stable, stratified spot-check: cover reason/type strata, then spread through IDs.
export function sampleGroup(items,size=8){
  const sorted=[...items].sort((a,b)=>a.key<b.key?-1:a.key>b.key?1:0),picked=[],seen=new Set();
  for(const i of sorted){const stratum=i.triage.reason+':'+i.row.amap_typecode;if(!seen.has(stratum)&&picked.length<size){seen.add(stratum);picked.push(i);}}
  for(let n=0;picked.length<Math.min(size,sorted.length)&&n<sorted.length;n++){const i=sorted[Math.floor(n*sorted.length/Math.min(size,sorted.length))];if(!picked.includes(i))picked.push(i);}
  for(const i of sorted)if(picked.length<Math.min(size,sorted.length)&&!picked.includes(i))picked.push(i);
  return picked;
}
