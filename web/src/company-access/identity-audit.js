import {gcj02ToWgs84} from '../location-search.js';
import {priorityEvidenceFor} from './priority-evidence.js';
// Display/review annotations only: no canonical identity, decision or coordinate mutation.
const hhSource='https://www.huahong.com.cn/?id=62&m=channel';
const fabSource='https://www.huahong.com.cn/?id=459&m=detail';
const bindings={
 B0LA7UOCSL:['华虹(集团)有限公司','碧波路与松涛路交叉口西南120米','上海华虹（集团）有限公司','集团办公室候选','碧波路177号 · 华虹科技园A区四楼',hhSource],
 B0FFLEW84S:['上海华虹宏力半导体制造有限公司(二厂)','张江高科技园区哈雷路288号','上海华虹宏力半导体制造有限公司','二厂 / 办公用途待核实','哈雷路288号',fabSource],
 B0LGYH4ROD:['上海华虹宏力半导体制造有限公司(二厂)','张江高科技园区哈雷路288号','上海华虹宏力半导体制造有限公司','二厂 / 办公用途待核实','哈雷路288号',fabSource],
 B0KA3ZQF8M:['上海华虹宏力半导体制造有限公司(祖冲之路)','祖冲之路1399号','上海华虹宏力半导体制造有限公司','三厂 / 地址与坐标需复核','祖冲之路1399号（2017年厂区名录）',fabSource],
 B0FFFPU5KX:['上海华力微电子有限公司-东区','高斯路497号','上海华力微电子有限公司（POI名称，实体待核实）','东区 / 实体地址冲突','官网上海华力：良腾路6号；2017年五厂：高斯路568号；497号列为集成电路研发中心',hhSource],
};
export function distanceMeters(a,b){const rad=Math.PI/180,lat=(a[1]+b[1])/2*rad;return Math.hypot((a[0]-b[0])*rad*Math.cos(lat),(a[1]-b[1])*rad)*6371008.8;}
const valid=v=>v!==undefined&&v!==null&&String(v).trim()!==''&&Number.isFinite(Number(v));
export function coordinateCheck(row){
 const raw=[row.longitude_gcj02,row.latitude_gcj02],stored=[row.longitude_wgs84,row.latitude_wgs84];
 if(![...raw,...stored].every(valid))return {status:'RAW_COORDINATES_UNAVAILABLE'};
 const original=raw.map(Number),wgs=stored.map(Number);
 if(Math.abs(original[0])>180||Math.abs(original[1])>90||Math.abs(wgs[0])>180||Math.abs(wgs[1])>90)return {status:'INVALID_COORDINATES'};
 const converted=gcj02ToWgs84(...original),residual_m=distanceMeters(converted,wgs);
 return {status:residual_m<=0.2?'CONVERSION_MATCH':'CONVERSION_MISMATCH',raw_gcj02:original,stored_wgs84:wgs,recomputed_wgs84:converted,residual_m,datum_shift_m:distanceMeters(original,wgs)};
}
export function identityAudit(rows){
 const selected=rows.filter(r=>/华虹|华力|中芯|环旭|豪威|超威|超微|\bAMD\b/i.test(`${r.company_name} ${r.address}`));
 return Object.fromEntries(selected.map(row=>{
  const b=bindings[row.amap_poi_id],bound=b&&row.company_name===b[0]&&row.address===b[1]?b:null;
  const evidence=priorityEvidenceFor(row),name=row.company_name||'',type=row.amap_type||row.provider_type||'';
  const nonOffice=/餐厅|食堂|咖啡|停车|充电|民防|项目部|养车|健身/.test(name+' '+type);
  const kind=nonOffice?'配套设施 / 非办公室':/大楼|栋|西塔|楼宇/.test(name+' '+type)?'楼栋 / 用途待核实':/科技园|产业园区/.test(name+' '+type)?'园区 / 不是租户实体':bound?.[3]||(/厂/.test(name)?'厂区 / 办公用途待核实':'公司候选 / 实体待核实');
  const flags=['OFFICE_LOCATION_UNVERIFIED'];
  if(nonOffice)flags.push('NON_OFFICE_POI');
  if(/门|入口|出口/.test(name+' '+row.address))flags.push('GATE_OR_ENTRANCE');
  if(/交叉口/.test(row.address))flags.push('INTERSECTION_ADDRESS');
  if(bound&&row.amap_poi_id==='B0FFFPU5KX')flags.push('ENTITY_ADDRESS_CONFLICT');
  if(bound&&row.amap_poi_id==='B0KA3ZQF8M')flags.push('ADDRESS_LOCATION_CONFLICT');
  const related=[];
  for(const other of selected){if(other.amap_poi_id===row.amap_poi_id)continue;
   const meters=distanceMeters([+row.longitude_wgs84,+row.latitude_wgs84],[+other.longitude_wgs84,+other.latitude_wgs84]);
   const same=other.company_name===name&&other.address===row.address;
   if(same||meters<30){related.push({poi_id:other.amap_poi_id,name:other.company_name,address:other.address,distance_m:Math.round(meters*10)/10,reason:same?'POSSIBLE_DUPLICATE':'NEARBY_DISTINCT_POI'});if(same&&!flags.includes('POSSIBLE_DUPLICATE'))flags.push('POSSIBLE_DUPLICATE');}
  }
  const coordinate=coordinateCheck(row);if(coordinate.status!=='CONVERSION_MATCH')flags.push(coordinate.status);
  return [row.amap_poi_id,{entity:bound?.[2]||evidence?.company_name||'独立POI · 未建立法人关联',kind,official_address:bound?.[4]||null,source_url:bound?.[5]||null,checked_at:'2026-11-01',flags,coordinate,related,note:'距离相近不等于同一实体或办公室。坐标转换一致不代表建筑定位准确；不自动移动、不合并、不更改决定。'}];
 }));
}
export const auditGroup=row=>row.identity_audit?.entity&&row.identity_audit.entity!=='独立POI · 未建立法人关联'?row.identity_audit.entity:`独立地点 · ${row.company_name}`;
// Relationship search terms are not aliases or entity merge keys.
export function relationshipSearchTerms(row){const b=bindings[row.amap_poi_id];return b&&row.company_name===b[0]&&row.address===b[1]?['华虹关联地点','Huahong related locations','Hua Hong related locations']:[];}
