import {aliasTerms,normalizeSearch,reviewedAliases} from './aliases.js';

/** One read-only search index for approved offices and provider candidate rows.
 * Alias attachment needs a reviewed stable identity AND matching canonical name.
 * Index entries stay separate: matching aliases never combine physical offices.
 */
export function createCompanySearchIndex(records,recordFor=record=>record,metadata=reviewedAliases){
  const entries=records.map(record=>{
    const row=recordFor(record);
    const terms=[row.company_name,...aliasTerms(row,metadata),row.address,row.district,row.building_name,row.building_name_if_available,row.sector,row.amap_poi_id]
      .filter(value=>value!==undefined&&value!==null).map(normalizeSearch);
    return {record,terms};
  });
  return query=>{const q=normalizeSearch(query);return entries.filter(e=>!q||e.terms.some(term=>term.includes(q))).map(e=>e.record);};
}
export const createReviewSearchIndex=items=>createCompanySearchIndex(items,item=>item.row);
