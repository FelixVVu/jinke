// Only irreversible identity/assertion digests go into git. No real company rows.
import {sha256,stable} from '../common.mjs';
export const providerDigest=id=>sha256(stable(['amap',id]));
export const assertionDigest=p=>sha256(stable([p.name,p.address,p.location,p.adcode,p.typecode]));
export const officeDigest=(name,address)=>sha256(stable([name,address].map(v=>String(v||'').normalize('NFKC').trim().toLowerCase().replace(/\s+/gu,' '))));
export function buildBaseline({decisions,offices,pending,snapshots}){
  const entries={};
  for(const d of decisions){const key=providerDigest(d.amap_poi_id);if(entries[key])throw Error('Duplicate historical identity');entries[key]={origin:'historical',assertions:[]};}
  for(const item of pending.batches.flatMap(b=>b.rows)){if(item.locked||item.row.review_status!=='pending')throw Error('Pending-only baseline required');const key=providerDigest(item.row.amap_poi_id);if(entries[key])throw Error('Overlapping baseline identity');entries[key]={origin:'pending_recovery',assertions:[]};}
  for(const s of snapshots)for(const r of s.responses)for(const p of r.payload.pois){const entry=entries[providerDigest(p.id)];if(entry&&!entry.assertions.includes(assertionDigest(p)))entry.assertions.push(assertionDigest(p));}
  for(const e of Object.values(entries)){e.assertions.sort();if(!e.assertions.length)throw Error('Missing baseline source assertion');}
  return {schema_version:1,counts:{approved:offices.features.length,historical:decisions.length,pending_recovery:pending.batches.flatMap(b=>b.rows).length},
    approved_sha256:sha256(stable(offices)),ledger_sha256:sha256(stable(decisions)),pending_sha256:sha256(stable(pending)),
    approved_office_keys:[...new Set(offices.features.map(f=>officeDigest(f.properties.company_name,f.properties.address)))].sort(),entries};
}
