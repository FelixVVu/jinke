// Reviewable search/evidence annotations. Never a decision, geocoder or merge rule.
const source=(url,title)=>({url,title,checked_at:'2026-10-29'});
const smic=[source('https://www.sse.com.cn/star/market/stocklist/info/company/index.shtml?COMPANY_CODE=688981','上交所：中芯国际 / SMIC · 张江路18号'),source('https://www.smics.com/uploads/Semiconductor%20Manufacturing%20-%2027K-3%20%281%29.pdf','中芯国际官方认证：该地址含设计服务与制造设施')];
const hh=[source('https://www.huahong.com.cn/?id=1541&m=detail','华虹2024年度披露：办公地址碧波路177号A区四楼'),source('https://www.huahong.com.cn/?id=62&m=channel','华虹集团：中英文名称及联系地址')];
const grace=[source('https://www.huahong.com.cn/?id=46&m=channel','华虹集团旗下企业：华虹宏力哈雷路288号')];
export const priorityEvidence=[
  {poi_id:'B0FFFV60W5',company_name:'中芯国际',address:'中芯国际1号门张江路18号',aliases:['SMIC','Semiconductor Manufacturing International Corporation'],finding:'官方地址与张江路18号一致；该园区含设计服务和制造功能，不能一律归为纯工厂。',action:'POI地址含1号门，需确认坐标代表公司办公/R&D位置还是入口；本条仍待人工审核，不把入口当作办公室。',sources:smic},
  {poi_id:'B0M2O72EWP',company_name:'中芯国际SO8大楼',address:'中芯国际',aliases:[],finding:'这是楼栋POI，地址未明确办公单元；总部地址证据不证明此楼栋用途。',action:'需楼栋用途或入驻部门证据；不要与公司POI合并或另计办公室。',sources:smic},
  {poi_id:'B0LA7UOCSL',company_name:'华虹(集团)有限公司',address:'碧波路与松涛路交叉口西南120米',aliases:['Hua Hong','Huahong','Shanghai Huahong Group'],finding:'官网明确集团办公地址为碧波路177号华虹科技园A区四楼；不是哈雷路的宏力厂区。',action:'当前POI地址是路口描述，需确认其坐标对应A区办公楼。不要用科技园或停车场POI代替集团办公室。',sources:hh},
  ...['B0FFLEW84S','B0LGYH4ROD'].map(poi_id=>({poi_id,company_name:'上海华虹宏力半导体制造有限公司(二厂)',address:'张江高科技园区哈雷路288号',aliases:['华虹宏力'],finding:'官方企业地址匹配哈雷路288号，但二厂标签不能证明具体办公/R&D建筑。另有同名同址POI。',action:'优先核实办公功能及重复POI；与碧波路集团办公室保持分开。',sources:grace})),
  {poi_id:'B001559Z7C',company_name:'环旭电子股份有限公司(张江厂)',address:'张江镇张江高科技园区张东路1558号',aliases:['USI','Universal Scientific Industrial'],finding:'张东路1558号是张江据点；官网另列盛夏路169号为上海销售办公室。',action:'不要把两个地址视作同一办公室；张江厂需要具体办公/R&D位置证据，盛夏路销售办公室仍缺独立定位。',sources:[source('https://www.usiglobal.com/cn/join','环旭官方：张江据点'),source('https://www.usiglobal.com/en/contact-usi?id=5d9918d8-cd62-4453-99e0-e9e6680c1a9d','USI官方：上海销售办公室盛夏路169号')]},
  {poi_id:'B0H3YC7RYM',company_name:'豪威集团',address:'张江高科技园区上科路88号',aliases:['OMNIVISION'],finding:'官网上海地址为上科路88号；公司、园区、西塔及停车设施不是同一记录。已有来源变更需要单独核实。',action:'保留原Needs Review决定；新证据不得覆盖历史或把附属设施当成额外办公室。',sources:[source('https://www.ovt.com/company/contact-us','OMNIVISION官方：全球地点')]},
];
export const priorityEvidenceFor=row=>priorityEvidence.find(e=>e.poi_id===row.amap_poi_id&&e.company_name===row.company_name&&e.address===row.address)||null;
