// Pure review state shared by the review-only browser and offline import gate.
export const STATUSES=['pending','accept','reject','needs_review'];
export const RULE_VERSION='company-review-suggestions-v1';
export function suggest(row){
  const name=String(row.company_name||''),type=String(row.amap_type||''),address=String(row.address||'');
  const result=(disposition,reason)=>({disposition,reason,version:RULE_VERSION});
  if(row.possible_duplicate===true||row.possible_duplicate==='true'||row.duplicate_group||row.provider_conflict)
    return result('needs_review','DUPLICATE_OR_CONFLICT');
  if(!Number.isFinite(Number(row.longitude_wgs84))||!Number.isFinite(Number(row.latitude_wgs84))||!row.longitude_wgs84||!row.latitude_wgs84)
    return result('needs_review','UNCERTAIN_LOCATION');
  if(/餐饮|餐厅|饭店|商店|便利店|专卖店|健身|项目部|项目办公室|工厂|厂区|公共平台|公共服务|restaurant|retail|gym|factory|project office/iu.test(`${name} ${type}`)||/^(05|06|07)/.test(String(row.amap_typecode||'')))
    return result('reject','NON_OFFICE_PLACE');
  if(/疑似|待核实|已关闭|注销|搬迁|过期|stale|closed|uncertain/iu.test(`${name} ${row.review_notes||''}`))return result('needs_review','STALE_OR_UNCERTAIN');
  if(!/(路|街|道|弄|巷|号|楼|室|园|road|street|floor|suite)/iu.test(address)||!/[0-9一二三四五六七八九十]/u.test(address))
    return result('needs_review','VAGUE_ADDRESS');
  if(/制造|生产|实业|工业|manufactur/iu.test(`${name} ${type}`))return result('needs_review','FACTORY_OR_OFFICE');
  if(!name.trim()||!/公司|company/iu.test(type)||!String(row.amap_typecode||'').startsWith('1702'))return result('needs_review','AMBIGUOUS_IDENTITY');
  return result('accept','SPECIFIC_MAPPED_COMPANY');
}
export function validateBundle(bundle){
  if(bundle?.schema_version!==1||!Array.isArray(bundle.batches)||typeof bundle.bundle_id!=='string')throw Error('Invalid review bundle');
  const keys=new Set();
  for(const batch of bundle.batches){
    if(!batch.id||!Array.isArray(batch.rows)||!Array.isArray(batch.columns))throw Error('Invalid batch');
    for(const item of batch.rows){
      if(item.key!==`${batch.id}:${item.row?.amap_poi_id}`||keys.has(item.key)||!STATUSES.includes(item.row?.review_status)||typeof item.locked!=='boolean')throw Error('Invalid candidate');
      keys.add(item.key);
    }
  }
  return bundle;
}
export function createSession(bundle){
  validateBundle(bundle);
  return {schema_version:1,bundle_id:bundle.bundle_id,reviewer:'',decisions:Object.fromEntries(bundle.batches.flatMap(b=>b.rows.map(i=>[i.key,{status:i.row.review_status,notes:i.row.review_notes||'',history:[]}])))};
}
export function validateSession(bundle,session){
  const expected=createSession(bundle);
  if(session?.schema_version!==1||session.bundle_id!==bundle.bundle_id||typeof session.reviewer!=='string'||!session.decisions||Object.keys(session.decisions).length!==Object.keys(expected.decisions).length)throw Error('Wrong review session');
  for(const item of bundle.batches.flatMap(b=>b.rows)){
    const d=session.decisions[item.key],initial=expected.decisions[item.key];
    if(!d||!STATUSES.includes(d.status)||typeof d.notes!=='string'||!Array.isArray(d.history))throw Error('Invalid decision');
    if(item.locked&&JSON.stringify(d)!==JSON.stringify(initial))throw Error('Prior decision locked');
    let current={status:initial.status,notes:initial.notes};
    for(const event of d.history){
      if(!event.reviewer?.trim()||!Number.isFinite(Date.parse(event.at))||event.from?.status!==current.status||event.from?.notes!==current.notes||!STATUSES.includes(event.to?.status)||typeof event.to?.notes!=='string')throw Error('Invalid decision history');
      current=event.to;
    }
    if(current.status!==d.status||current.notes!==d.notes)throw Error('Decision requires explicit review history');
  }
  return session;
}
export function decide(bundle,session,keys,status,notes,at=new Date().toISOString()){
  validateSession(bundle,session);
  if(!STATUSES.includes(status)||!session.reviewer.trim()||typeof notes!=='string')throw Error('Reviewer name and valid decision required');
  const items=new Map(bundle.batches.flatMap(b=>b.rows.map(i=>[i.key,i])));
  // Atomic: reject the entire action if any selected candidate is unknown or locked.
  if(!keys.length||keys.some(key=>!items.has(key)||items.get(key).locked))throw Error('Prior decisions are locked');
  const next=structuredClone(session);
  for(const key of new Set(keys)){
    const d=next.decisions[key],to={status,notes};
    d.history.push({from:{status:d.status,notes:d.notes},to,reviewer:session.reviewer.trim(),at});Object.assign(d,to);
  }
  return validateSession(bundle,next);
}
export function exportRows(bundle,session,batchId){
  validateSession(bundle,session);
  const batch=bundle.batches.find(b=>b.id===batchId);if(!batch)throw Error('Unknown batch');
  return batch.rows.map(i=>({...i.row,review_status:session.decisions[i.key].status,review_notes:session.decisions[i.key].notes}));
}
export function rowsToCSV(rows,columns){
  const safe=value=>{const s=String(value??'');return /^[\s]*[=+\-@\t\r]/u.test(s)||s.startsWith("'")?"'"+s:s;};
  return [columns,...rows.map(row=>columns.map(key=>safe(row[key])))].map(row=>row.map(s=>'"'+String(s).replaceAll('"','""')+'"').join(',')).join('\r\n')+'\r\n';
}
