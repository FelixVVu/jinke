// Reviewed discovery terms and address leads, not aliases, coordinates or approvals.
const source=(url,title)=>({url,title,checked_at:'2026-10-26'});
export const CONTINUATION_SOURCES=[
  {id:'amd-en',company_name:'AMD',terms:['AMD','超威半导体'],addresses:['张东路1387号','环科路669号','博云路2号'],use:'office',sources:[source('https://www.amd.com/en/corporate/locations.html','AMD official corporate locations'),source('https://www.amd.com/zh-cn/legal/trademarks.html','AMD official Chinese trademark 超威半导体')]},
  {id:'amd-cn',company_name:'超威半导体',terms:['超威半导体','AMD'],addresses:['张东路1387号','环科路669号','博云路2号'],use:'office',sources:[source('https://www.amd.com/en/corporate/locations.html','AMD official corporate locations'),source('https://www.amd.com/zh-cn/legal/trademarks.html','AMD official Chinese trademark 超威半导体')]},
  {id:'ov-cn',company_name:'豪威科技',terms:['豪威','OMNIVISION'],addresses:['上科路88号'],use:'corporate_location',sources:[source('https://www.ovt.com/company/contact-us','OMNIVISION official Shanghai location; Songjiang is separate')]},
  {id:'ov-en',company_name:'OMNIVISION',terms:['豪威','OMNIVISION'],addresses:['上科路88号'],use:'corporate_location',sources:[source('https://www.ovt.com/company/contact-us','OMNIVISION official Shanghai location')]},
  {id:'usi-sales',company_name:'环旭电子 盛夏路',terms:['环旭','USI'],addresses:['盛夏路169号'],use:'office',sources:[source('https://www.usiglobal.com/en/contact-usi?id=5d9918d8-cd62-4453-99e0-e9e6680c1a9d','USI official Shanghai sales office')]},
  {id:'park-datagran',company_name:'达观数据',terms:['达观数据'],addresses:[],use:'historical_park_lead',sources:[source('https://www.spsp.com.cn/企业孵化与投资融资','Pudong Software Park incubated-company directory; not current tenancy')]},
];
export const FACILITY_LEADS=[
  {id:'smic',terms:['中芯国际','SMIC'],addresses:['张江路18号'],use:'mixed',sources:[source('https://www.sse.com.cn/star/market/stocklist/info/company/index.shtml?COMPANY_CODE=688981','SSE SMIC corporate contact; campus office position unbound')]},
  {id:'huahong',terms:['华虹宏力'],addresses:['哈雷路288号'],use:'mixed',sources:[source('https://www.huahong.com.cn/?id=46&m=channel','Huahong official subsidiary directory')]},
  {id:'huahong-group',terms:['华虹集团','华虹(集团)'],addresses:['碧波路177号'],use:'office',sources:[source('https://www.huahong.com.cn/?id=46&m=channel','Huahong group address: Area A fourth floor; subsidiary identities separate')]},
  {id:'usi',terms:['环旭','USI'],addresses:['张东路1558号'],use:'mixed',sources:[source('https://www.usiglobal.com/en/global-locations?location_id=usi-shanghai-zhangjiang-china','USI Zhangjiang design/manufacturing site; not the sales office')]},
];
const norm=s=>String(s||'').normalize('NFKC').toLowerCase().replace(/[\s\p{P}\p{S}]/gu,'');
export function matchingSources(row){return [...CONTINUATION_SOURCES,...FACILITY_LEADS].filter(l=>l.terms.some(t=>norm(row.company_name).includes(norm(t))));}
export function addressLeadMatches(address,lead){
  const a=norm(address);return lead.addresses.some(value=>{const v=norm(value);return a.includes(v)||a.includes(v.replace(/号$/u,''))&&!/\d/.test(a.split(v.replace(/号$/u,''))[1]?.[0]||'');});
}
export function sourceEvidence(row){
  const matches=matchingSources(row),lead=matches.find(l=>addressLeadMatches(row.address,l));
  if(!lead)return null;
  return {poi_id:row.amap_poi_id,company_name:row.company_name,address:row.address,
    assessment:lead.use==='office'?'office_address_match':lead.use==='mixed'?'mixed_site_office_match':'identity_only',
    summary:lead.use==='mixed'?'公开公司地址与混合用途园区地址相符；须区分具体办公室、研发楼和生产／附属设施。':lead.use==='office'?'公司名称线索与官方办公街道门牌一致，需人工确认 POI 实体与具体办公位置。':'官方列有该公司上海地点；未证明本 POI 为办公室。',
    scope:'Deterministic name + exact street-number corroboration only; human identity/office decision required.',
    limitations:'No automatic acceptance, identity merge, invented location, or verified-physical confidence upgrade. Campus facilities are not interchangeable.',sources:lead.sources};
}
