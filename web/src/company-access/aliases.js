// Search metadata only. Exact office/name binding; never an identity merge rule.
// Reviewed mappings supplied explicitly by the user, 2026-10-02.
export const reviewedAliases = Object.freeze([
  {office_id:'office-a687151c1b1fc0bded20bdd0',canonical_name:'思爱普有限公司',brand_name:'SAP',acronym:'SAP',aliases:['思爱普'],reviewed_by:'User request 2026-10-02'},
  {office_id:'office-6416a1738f6ca3e36b50c291',canonical_name:'英伟达半导体科技(上海)有限公司',brand_name:'NVIDIA',aliases:['英伟达'],reviewed_by:'User request 2026-10-02'},
]);
export function aliasTerms(office,metadata=reviewedAliases){
  const record=metadata.find(r=>r.office_id===office.id&&r.canonical_name===office.company_name&&r.reviewed_by);
  return record?[record.english_name,record.brand_name,record.acronym,...(record.aliases||[])].filter(Boolean):[];
}
