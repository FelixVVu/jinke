import { validateOffice } from '../../web/src/company-access/schema.js';
import { prepareReachAreas, reachMemberships, deriveCompanyAccess, validateCompanyAccessOutput } from '../../web/src/company-access/model.js';
import { VERSION, stable, sha256, compare, validateSettings } from './common.mjs';
import { validateEnvelope, validateRawRecord } from './validate.mjs';
import { normalizeRecord } from './normalize.mjs';
import { normalizeCoordinates } from './coordinates.mjs';
import { classifyLocation, classifyIndustry } from './classify.mjs';
import { deduplicate } from './dedupe.mjs';
import { assignHubs } from './hubs.mjs';

export const artifactNames = Object.freeze({offices:'company-offices.geojson',hubs:'company-hubs.geojson',
  summary:'company-reach-summary.json',metadata:'company-access-metadata.json',
  audit:'company-ingestion-audit.json',rejected:'company-rejected-records.json',review:'company-duplicate-review.json'});

/** Pure preparation: no network, clock, random IDs, geocoder, or writes. */
export function ingest(input,areas,options={}){
  validateEnvelope(input);
  const settings=validateSettings(options.settings);
  const byLimit=prepareReachAreas(areas);
  const seen=new Map();
  const rawRows=input.records.map(raw=>({raw,hash:sha256(stable(raw))})).sort((a,b)=>compare(a.hash,b.hash)).map(row=>{
    const occurrence=(seen.get(row.hash)||0)+1;seen.set(row.hash,occurrence);
    return {...row,ref:`raw-${row.hash}-${occurrence}`};
  });
  const rawByRef=new Map(rawRows.map(row=>[row.ref,row.raw]));
  const candidates=[], rejected=[];
  for(const {raw,ref} of rawRows){
    try{
      validateRawRecord(raw);
      const normalized=normalizeRecord(raw);
      const converted=normalizeCoordinates(raw);
      const location=classifyLocation(raw),industry=classifyIndustry(raw);
      if(location.location_confidence==='approximate'&&!settings.include_approximate){
        rejected.push({record_ref:ref,disposition:'quarantined',reason_codes:['WEAK_LOCATION_EVIDENCE',location.reason],coordinate_provenance:converted.audit,location_classification:location,raw_record:raw});continue;
      }
      const namespace=raw.source_namespace||`${raw.source_type}:${new URL(raw.source_url).host}`;
      candidates.push({raw,ref,normalized,coordinates:converted.coordinates,coordinate_audit:converted.audit,location,industry,
        source_key:JSON.stringify([namespace,raw.source_record_id])});
    }catch(error){
      if(!error.code)throw error;
      rejected.push({record_ref:ref,disposition:['UNKNOWN_COORDINATE_SYSTEM','CONVERSION_OUTSIDE_SUPPORTED_REGION'].includes(error.code)?'quarantined':'rejected',
        reason_codes:[error.code],detail:error.message,raw_record:raw});
    }
  }
  const dedupe=deduplicate(candidates,settings);
  const hubs=assignHubs(dedupe.accepted,settings);
  const conflictByRef=new Map();
  const conflicts=[...dedupe.conflicts,...hubs.conflicts].sort((a,b)=>compare(stable(a),stable(b)));
  for(const conflict of conflicts)for(const ref of conflict.record_refs){
    if(!conflictByRef.has(ref))conflictByRef.set(ref,new Set());
    for(const reason of conflict.reason_codes)conflictByRef.get(ref).add(reason);
  }
  const candidateByRef=new Map(candidates.map(c=>[c.ref,c]));
  for(const [ref,reasons] of conflictByRef)rejected.push({record_ref:ref,coordinate_provenance:candidateByRef.get(ref).coordinate_audit,location_classification:candidateByRef.get(ref).location,disposition:'conflict',reason_codes:[...reasons].sort(),raw_record:rawByRef.get(ref)});
  const canonical=[],acceptedAudit=[];
  for(const record of hubs.accepted){
    const hub=hubs.assignments.get(record.office_id);
    const classification=record.members.find(member=>member.industry.industry_code!==null)?.industry||record.industry;
    const office={id:record.office_id,company_name:record.normalized.company_name,normalized_name:record.normalized.normalized_name,
      longitude:record.coordinates[0],latitude:record.coordinates[1],coordinate_system:'WGS84',
      district:record.normalized.district,address:record.normalized.address,
      building_name:hub?.hub_kind==='physical_building'?hub.hub_name:record.normalized.building_name,
      hub_id:hub?.hub_id||null,hub_name:hub?.hub_name||null,
      industry_code:classification.industry_code,sector:classification.sector,
      location_confidence:record.location.location_confidence,source_type:record.raw.source_type,
      source_id:record.source_key,source_url:record.raw.source_url,verified_at:record.raw.verified_at,
      min_reach_minutes:null};
    const membership=reachMemberships(office,byLimit);
    office.min_reach_minutes=membership[0]??null;
    validateOffice(office);canonical.push(office);
    acceptedAudit.push({office_id:office.id,representative_ref:record.ref,record_refs:record.members.map(m=>m.ref).sort(),
      reach_minutes:membership,classification,hub:hub||{hub_id:null,hub_kind:null,assignment_reason:'NO_REVIEWED_HUB'},
      sources:record.members.map(m=>({record_ref:m.ref,source_key:m.source_key,raw_record:m.raw,
        normalized:m.normalized,coordinate_provenance:m.coordinate_audit,location_classification:m.location,
        industry_classification:m.industry})).sort((a,b)=>compare(a.record_ref,b.record_ref))});
  }
  const provenance={status:'ready',dataset_version:input.dataset_version,dataset_kind:input.dataset_kind,
    inventory_sha256:sha256(stable(canonical)),reach_sha256:options.reachBytes?sha256(options.reachBytes):sha256(stable(areas))};
  const output=deriveCompanyAccess(canonical,areas,provenance);
  validateCompanyAccessOutput(output,canonical,areas,provenance);
  // Extra compact hub semantics prevent algorithmic clusters being shown as buildings.
  for(const feature of output.hubs.features){
    feature.properties.hub_kind=hubs.assignments.get(feature.properties.representative_office_id).hub_kind;
  }
  const acceptedIDs=new Set(canonical.map(o=>o.id));
  const duplicates=dedupe.duplicates.filter(d=>acceptedIDs.has(d.accepted_office_id));
  rejected.sort((a,b)=>compare(a.record_ref,b.record_ref));
  const dispositions={accepted:canonical.length,duplicates:duplicates.length,
    conflicts:rejected.filter(r=>r.disposition==='conflict').length,
    quarantined:rejected.filter(r=>r.disposition==='quarantined').length,
    rejected:rejected.filter(r=>r.disposition==='rejected').length};
  output.metadata.ingestion={pipeline_version:VERSION,settings,input_record_count:input.records.length,
    input_records_sha256:sha256(stable(rawRows.map(r=>r.raw))),dispositions,
    industry_scope:'all accepted offices; Core+ eligibility recorded separately, never employment',
    core_plus_office_count:acceptedAudit.filter(a=>a.classification.core_plus_code!==null).length,
    approximate_office_count:canonical.filter(o=>o.location_confidence==='approximate').length,
    publication_status:'offline_candidate_not_published'};
  output.audit={pipeline_version:VERSION,dataset_kind:input.dataset_kind,settings,
    input_files:options.inputFiles||[],reach_input_hash_mode:options.reachBytes?'file_bytes':'canonical_json',
    canonical_inventory_sha256:provenance.inventory_sha256,dispositions,accepted:acceptedAudit};
  output.rejected={records:rejected};
  output.review={duplicates,conflicts};
  validateArtifacts(output,areas);
  return output;
}

/** Independently reconcile counts, canonical schema, geometry and every raw disposition. */
export function validateArtifacts(output,areas){
  const canonical=output.offices.features.map(({properties})=>{
    const {reach_minutes,...office}=properties;return office;
  });
  const {ingestion,...provenance}=output.metadata;
  const base={...output,hubs:structuredClone(output.hubs),metadata:provenance};
  for(const feature of base.hubs.features)delete feature.properties.hub_kind;
  // deriveCompanyAccess accepts metadata provenance; fixed fields are recomputed.
  validateCompanyAccessOutput(base,canonical,areas,{
    status:provenance.status,dataset_version:provenance.dataset_version,dataset_kind:provenance.dataset_kind,
    inventory_sha256:provenance.inventory_sha256,reach_sha256:provenance.reach_sha256,
  });
  if(sha256(stable(canonical))!==provenance.inventory_sha256)throw new TypeError('Canonical inventory hash mismatch.');
  const accepted=new Map(output.audit.accepted.map(a=>[a.office_id,a]));
  if(accepted.size!==canonical.length)throw new TypeError('Accepted audit count mismatch.');
  if(stable(validateSettings(ingestion.settings))!==stable(output.audit.settings)||output.audit.pipeline_version!==VERSION||ingestion.pipeline_version!==VERSION)throw new TypeError('Pipeline settings/version mismatch.');
  const refs=[];
  const reconstructed=[];
  const reachIndex=prepareReachAreas(areas);
  for(const office of canonical){
    const audit=accepted.get(office.id);
    if(!audit||!audit.record_refs.includes(audit.representative_ref)||stable(audit.reach_minutes)!==stable(reachMemberships(office,reachIndex)))throw new TypeError('Accepted audit does not reconcile.');
    const representative=audit.sources.find(s=>s.record_ref===audit.representative_ref);
    for(const source of audit.sources){
      validateRawRecord(source.raw_record);
      const raw=source.raw_record;
      const expectedRefPrefix=`raw-${sha256(stable(raw))}-`;
      if(!source.record_ref.startsWith(expectedRefPrefix))throw new TypeError('Raw evidence hash mismatch.');
      const converted=normalizeCoordinates(raw);
      if(stable(converted.audit)!==stable(source.coordinate_provenance)||stable(classifyLocation(raw))!==stable(source.location_classification)||stable(classifyIndustry(raw))!==stable(source.industry_classification))throw new TypeError('Source classification or coordinate audit mismatch.');
      reconstructed.push(raw);
    }
    if(!representative||stable(normalizeCoordinates(representative.raw_record).coordinates)!==stable([office.longitude,office.latitude])||classifyLocation(representative.raw_record).location_confidence!==office.location_confidence)throw new TypeError('Representative coordinate/confidence mismatch.');
    if(audit.classification.industry_code!==office.industry_code||!audit.sources.some(s=>stable(s.industry_classification)===stable(audit.classification)))throw new TypeError('Industry audit mismatch.');
    refs.push(audit.representative_ref);
    const sources=audit.sources.map(s=>s.record_ref).sort();
    if(stable(sources)!==stable(audit.record_refs))throw new TypeError('Audit sources mismatch.');
  }
  for(const duplicate of output.review.duplicates){
    const office=accepted.get(duplicate.accepted_office_id);
    if(!office?.record_refs.includes(duplicate.record_ref)||office.representative_ref!==duplicate.representative_ref)throw new TypeError('Duplicate target mismatch.');
    refs.push(duplicate.record_ref);
  }
  refs.push(...output.rejected.records.map(r=>r.record_ref));
  reconstructed.push(...output.rejected.records.map(r=>r.raw_record));
  const orderedRaw=reconstructed.map(raw=>({raw,hash:sha256(stable(raw))})).sort((a,b)=>compare(a.hash,b.hash)).map(r=>r.raw);
  if(sha256(stable(orderedRaw))!==ingestion.input_records_sha256)throw new TypeError('Raw inventory hash mismatch.');
  const conflictRefs=[...new Set(output.review.conflicts.flatMap(c=>c.record_refs))].sort();
  if(stable(conflictRefs)!==stable(output.rejected.records.filter(r=>r.disposition==='conflict').map(r=>r.record_ref).sort()))throw new TypeError('Conflict review mismatch.');
  if(ingestion.core_plus_office_count!==output.audit.accepted.filter(a=>a.classification.core_plus_code!==null).length||ingestion.approximate_office_count!==canonical.filter(o=>o.location_confidence==='approximate').length)throw new TypeError('Classification totals mismatch.');
  if(new Set(refs).size!==refs.length||refs.length!==ingestion.input_record_count)throw new TypeError('Raw disposition count mismatch.');
  for(const feature of output.hubs.features){
    for(const id of feature.properties.office_ids){
      const hub=accepted.get(id)?.hub;
      if(!hub||hub.hub_id!==feature.id||hub.hub_kind!==feature.properties.hub_kind)throw new TypeError('Hub type audit mismatch.');
    }
  }
  const counts={accepted:canonical.length,duplicates:output.review.duplicates.length,
    conflicts:output.rejected.records.filter(r=>r.disposition==='conflict').length,
    quarantined:output.rejected.records.filter(r=>r.disposition==='quarantined').length,
    rejected:output.rejected.records.filter(r=>r.disposition==='rejected').length};
  if(stable(counts)!==stable(ingestion.dispositions)||stable(counts)!==stable(output.audit.dispositions))throw new TypeError('Disposition summary mismatch.');
  return output;
}
