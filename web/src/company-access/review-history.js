// Pure overlay shared by the console and trusted offline importer. No decisions
// are inferred from suggestions. Previous decisions always win by provider ID.
export function attachReviewHistory(incoming,baseline){
  const prior=new Map(baseline.batches.flatMap(b=>b.rows.map(i=>[i.row.amap_poi_id,i])));
  const key=row=>[row.company_name,row.address].map(s=>String(s||'').normalize('NFKC').trim().toLowerCase().replace(/\s+/gu,' ')).join('\u0000');
  const accepted=new Set([...prior.values()].filter(i=>i.row.review_status==='accept').map(i=>key(i.row)));
  const next=structuredClone(incoming);
  for(const batch of next.batches)for(const item of batch.rows){
    const previous=prior.get(item.row.amap_poi_id);
    if(!previous){if(accepted.has(key(item.row)))item.suggestion={disposition:'needs_review',reason:'PRIOR_INVENTORY_MATCH',version:'company-review-suggestions-v1'};continue;}
    const changed=['company_name','address','longitude_wgs84','latitude_wgs84'].some(k=>item.row[k]!==previous.row[k]);
    item.row.review_status=previous.row.review_status;item.row.review_notes=previous.row.review_notes;
    item.locked=true;item.prior_review=previous.prior_review;
    if(changed)item.suggestion={disposition:'needs_review',reason:'PRIOR_SOURCE_CHANGED',version:'company-review-suggestions-v1'};
  }
  next.batches.push(...structuredClone(baseline.batches));
  next.bundle_id=`${incoming.bundle_id}.${baseline.bundle_id}`;
  return next;
}
