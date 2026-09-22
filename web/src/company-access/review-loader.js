import { deriveCompanyAccess } from './model.js';
/** An explicit review-build marker is required. Normal builds never request data. */
export async function loadCompanyReview({enabled,areas,fetchJson}){
  if(!enabled)return null;
  const [offices,hubs,summary,metadata]=await Promise.all(['company-offices.geojson','company-hubs.geojson','company-reach-summary.json','company-access-metadata.json'].map(fetchJson));
  const canonical=offices.features.map(({properties})=>{const {reach_minutes,...office}=properties;return office;});
  if(metadata.ingestion?.publication_status!=='offline_candidate_not_published'||metadata.dataset_kind!=='candidate')throw Error('Not an approved review inventory');
  const expected=deriveCompanyAccess(canonical,areas,{status:metadata.status,dataset_version:metadata.dataset_version,inventory_sha256:metadata.inventory_sha256,reach_sha256:metadata.reach_sha256,dataset_kind:metadata.dataset_kind});
  const stable=v=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
  const plainHubs={...hubs,features:hubs.features.map(f=>{const {hub_kind,...properties}=f.properties;return {...f,properties};})};
  for(const [a,b] of [[offices,expected.offices],[plainHubs,expected.hubs],[summary,expected.summary]])if(stable(a)!==stable(b))throw Error('Review data does not reconcile');
  return {offices,hubs,summary,metadata};
}
