import { fail, sha256, stable } from '../common.mjs';
import { ingest } from '../ingest.mjs';
import { validateSnapshot, candidatesFromCache } from './acquire.mjs';
export const COLUMNS=['review_status','company_name','amap_poi_id','amap_type','amap_typecode','address','district','adcode','building_name_if_available','longitude_gcj02','latitude_gcj02','longitude_wgs84','latitude_wgs84','inside_30_minute_reach','possible_duplicate','duplicate_group','source_reference','review_notes'];
// Prevent spreadsheet formula execution without altering the original JSON evidence.
const safeCell=value=>{const s=String(value??'');return /^[\s]*[=+\-@\t\r]/u.test(s)||s.startsWith("'")?"'"+s:s;};
export function reviewRows(candidates){return candidates.map(c=>({review_status:'pending',company_name:c.raw.company_name,amap_poi_id:c.amap_poi_id,
  amap_type:c.provider.type||'',amap_typecode:c.provider.typecode,address:c.raw.address,district:c.raw.district||'',adcode:c.provider.adcode||'',
  building_name_if_available:c.raw.building_name||'',longitude_gcj02:c.raw.longitude,latitude_gcj02:c.raw.latitude,longitude_wgs84:c.longitude_wgs84,latitude_wgs84:c.latitude_wgs84,
  inside_30_minute_reach:true,possible_duplicate:c.possible_duplicate,duplicate_group:c.duplicate_group,source_reference:c.raw.source_url,review_notes:''}));}
export function toCSV(rows){return [COLUMNS,...rows.map(row=>COLUMNS.map(key=>safeCell(row[key])))].map(row=>row.map(s=>'"'+String(s).replaceAll('"','""')+'"').join(',')).join('\r\n')+'\r\n';}
export function parseCSV(csv){
  const rows=[];let row=[],value='',quoted=false,closed=false;
  csv=csv.replace(/^\uFEFF/,'');
  for(let i=0;i<csv.length;i++){
    const c=csv[i];
    if(quoted){if(c==='"'){if(csv[i+1]==='"'){value+='"';i++;}else{quoted=false;closed=true;}}else value+=c;continue;}
    if(c==='"'){if(value||closed)fail('INVALID_CSV');quoted=true;continue;}
    if(c===','||c==='\n'||c==='\r'){
      row.push(value);value='';closed=false;
      if(c!==','){rows.push(row);row=[];if(c==='\r'&&csv[i+1]==='\n')i++;}continue;
    }
    if(closed)fail('INVALID_CSV');value+=c;
  }
  if(quoted)fail('INVALID_CSV');if(value||row.length||closed){row.push(value);rows.push(row);}
  if(stable(rows.shift())!==stable(COLUMNS)||rows.some(r=>r.length!==COLUMNS.length))fail('INVALID_CSV_COLUMNS');
  return rows.map(row=>Object.fromEntries(COLUMNS.map((key,i)=>[key,row[i]])));
}
export function approvedFromReview({snapshot,areas,csv,reviewer,reviewedAt}){
  validateSnapshot(snapshot,areas);
  if(typeof reviewer!=='string'||!reviewer.trim()||!/^\d{4}-\d{2}-\d{2}T.*Z$/.test(reviewedAt)||!Number.isFinite(Date.parse(reviewedAt)))fail('MISSING_REVIEW_ATTRIBUTION');
  const {candidates}=candidatesFromCache(snapshot,areas), expected=reviewRows(candidates), rows=parseCSV(csv);
  const byId=new Map(expected.map(row=>[safeCell(row.amap_poi_id),row])), seen=new Set(),records=[],decisions=[];
  for(const row of rows){
    const original=byId.get(row.amap_poi_id);
    if(!original||seen.has(row.amap_poi_id))fail('UNKNOWN_OR_DUPLICATE_REVIEW_ID');seen.add(row.amap_poi_id);
    for(const key of COLUMNS)if(!['review_status','review_notes'].includes(key)&&row[key]!==safeCell(original[key]))fail('IMMUTABLE_REVIEW_FIELD',key);
    if(!['pending','accept','reject','needs_review'].includes(row.review_status))fail('INVALID_REVIEW_STATUS');
    const candidate=candidates.find(c=>c.amap_poi_id===original.amap_poi_id);
    decisions.push({amap_poi_id:candidate.amap_poi_id,decision:row.review_status,notes:row.review_notes,reviewer,reviewed_at:reviewedAt,query_ids:candidate.query_ids,raw_sha256:sha256(stable(candidate.raw))});
    if(row.review_status==='accept')records.push({...candidate.raw,source_evidence:{...candidate.raw.source_evidence,reviewed:true,
      description:`Human-reviewed mapped office candidate. Reviewer: ${reviewer}. Notes: ${row.review_notes}`}});
  }
  if(seen.size!==candidates.length)fail('MISSING_REVIEW_ROWS');
  records.sort((a,b)=>a.source_record_id<b.source_record_id?-1:1);decisions.sort((a,b)=>a.amap_poi_id<b.amap_poi_id?-1:1);
  const envelope={schema_version:1,dataset_kind:'candidate',dataset_version:`amap-pilot-${sha256(stable(snapshot)).slice(0,16)}`,records};
  const artifacts=ingest(envelope,areas);
  return {envelope,artifacts,decisions,review_csv_sha256:sha256(csv),snapshot_sha256:sha256(stable(snapshot))};
}
const breakdown=(items,key)=>{const counts={};for(const c of items){const value=String(key(c)||'unknown');counts[value]=(counts[value]||0)+1;}return counts;};
export function qaReport(bundle,approved=null){
  const {candidates,exclusions,counts,snapshot}=bundle;
  const decisions=approved?.decisions||candidates.map(()=>({decision:'pending'}));
  const canonical=approved?.artifacts;
  return {label:'Identified office candidates; source-dependent coverage. Research QA only; not a census or employment estimate.',
    query_cell_count:snapshot.plan.cells.length,api_requests_total:snapshot.attempts.length,...snapshot.execution,...counts,
    accepted_count:decisions.filter(d=>d.decision==='accept').length,rejected_count:decisions.filter(d=>d.decision==='reject').length,
    pending_count:decisions.filter(d=>['pending','needs_review'].includes(d.decision)).length,
    district_breakdown:breakdown(candidates,c=>c.raw.district),amap_type_breakdown:breakdown(candidates,c=>c.provider.typecode),
    building_name_count:candidates.filter(c=>c.raw.building_name).length,building_name_denominator:candidates.length,
    possible_duplicate_count:candidates.filter(c=>c.possible_duplicate).length,exclusion_reasons:breakdown(exclusions,e=>e.reason),
    canonical_dispositions:canonical?.metadata.ingestion.dispositions||null,
    canonical_ingestion_quarantine_count:canonical?.metadata.ingestion.dispositions.quarantined??candidates.length,
    canonical_quarantine_scope:canonical?'accepted records only':'all unreviewed records remain excluded by Phase 2 confidence rules',
    reviewed_office_locations:canonical?.offices.features.length||0,
    final_exact_reach_membership_counts:Object.fromEntries([10,20,30,40,50].map(limit=>[limit,canonical?.offices.features.filter(f=>f.properties.reach_minutes.includes(limit)).length||0]))};
}
export const reportMarkdown=report=>'# AMap company-office pilot QA\n\n'+report.label+'\n\n```json\n'+JSON.stringify(report,null,2)+'\n```\n';
