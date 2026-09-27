import { COMPANY_DISCLOSURE } from './schema.js';
import { selectCompanyOffices } from './model.js';
export const companyPanelMarkup=`
<details id="companyAccess" class="control-section company-access">
<summary>Company Access</summary><div class="details-content">
<p id="companyAccessStatus" role="status" aria-live="polite"></p>
<label class="toggle"><input id="showCompanyOffices" type="checkbox" disabled> Company offices</label>
<a id="companySamplingCoverage" hidden target="_blank" rel="noopener">View geographic sampling coverage ↗</a>
<div id="companyAccessAnalytics" class="company-analytics"></div>
<p class="company-access-note">${COMPANY_DISCLOSURE}</p>

</div></details>`;
export function companyAnalytics(output,limit){
  const minutes=limit==='all'?50:limit,offices=selectCompanyOffices(output,limit).features.map(f=>f.properties);
  const previous=new Set(minutes===10?[]:selectCompanyOffices(output,minutes-10).features.map(f=>f.id));
  const counts=key=>Object.fromEntries([...new Set(offices.map(o=>o[key]||'Unknown'))].sort().map(v=>[v,offices.filter(o=>(o[key]||'Unknown')===v).length]));
  return {count:offices.length,incremental:offices.filter(o=>!previous.has(o.id)).length,districts:counts('district'),confidence:counts('location_confidence'),
    hubs:(output?.hubs.features||[]).filter(f=>f.properties.counts_by_reach[minutes]>0).map(f=>({name:f.properties.hub_name,count:f.properties.counts_by_reach[minutes]})).sort((a,b)=>b.count-a.count||a.name.localeCompare(b.name)).slice(0,5)};
}
export function companyPanelState(output,limit){
  const minutes=limit==='all'?50:limit;
  if(!output||output.metadata.status!=='ready')return {enabled:false,message:'Company-office data has not been connected yet.'};
  const record=output.summary.records.find(r=>r.limit_minutes===minutes);
  return {enabled:true,message:`Pilot 1 · REVIEW ONLY · ${record.office_count} identified offices · within ${minutes} minutes${limit==='all'?' (All reach view)':''}. Limited sampling; missing inventory does not mean no offices.`};
}
const line=(root,text,tag='p')=>{const el=root.ownerDocument.createElement(tag);el.textContent=text;root.append(el);return el;};
const confidenceLabel={verified:'Verified physical office',building:'Reviewed mapped office',approximate:'Approximate location'};
export function renderCompanyPanel(root,output,limit){
  const view=companyPanelState(output,limit);root.querySelector('#companyAccessStatus').textContent=view.message;
  const toggle=root.querySelector('#showCompanyOffices');toggle.disabled=!view.enabled;if(!view.enabled)toggle.checked=false;
  const analytics=root.querySelector('#companyAccessAnalytics');analytics.replaceChildren();
  if(view.enabled){const a=companyAnalytics(output,limit);line(analytics,`${a.incremental} additional offices versus the previous reach`);
    line(analytics,'Districts','strong');for(const [district,n] of Object.entries(a.districts))line(analytics,`${district} · ${n}`);
    line(analytics,'Location confidence','strong');for(const [confidence,n] of Object.entries(a.confidence))line(analytics,`${confidenceLabel[confidence]||confidence} · ${n} / ${a.count}`);
    line(analytics,'Known hubs','strong');if(!a.hubs.length)line(analytics,'No reviewed hub assignments');for(const hub of a.hubs)line(analytics,`${hub.name} · ${hub.count}`);
  }

}
