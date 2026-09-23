import { normalizeText } from './normalize.mjs';
export const CORE_PLUS_CODES = Object.freeze(['I', 'J', 'M', '721', '723', '724', '725']);

export function classifyLocation(raw) {
  const evidence = raw.source_evidence;
  const strongTypes = { official_office: 'company_website', official_recruitment: 'company_website',
    tenant_directory: 'building_directory', government_office: 'government' };
  if (evidence.reviewed && strongTypes[evidence.kind] === raw.source_type && raw.verified_at) {
    return { location_confidence: 'verified', reason: 'REVIEWED_PHYSICAL_OFFICE_EVIDENCE', evidence_kind: evidence.kind };
  }
  if (evidence.reviewed && ((evidence.kind === 'map_poi' && ['licensed_poi', 'osm'].includes(raw.source_type)) ||
      (evidence.kind === 'office_building' && raw.source_type === 'building_directory'))) {
    return { location_confidence: 'building', reason: 'REVIEWED_MAPPED_OFFICE_EVIDENCE', evidence_kind: evidence.kind };
  }
  return { location_confidence: 'approximate', reason: evidence.kind === 'registered_address' ? 'REGISTERED_ADDRESS_ONLY' : 'WEAK_OR_UNREVIEWED_LOCATION', evidence_kind: evidence.kind };
}

export function classifyIndustry(raw) {
  const evidence = raw.classification_evidence;
  if (!raw.industry_code || !evidence?.reviewed || evidence.scheme !== 'GB/T 4754-2017') return {
    industry_code: null, sector: null, core_plus_code: null, classification_source: null,
    classification_confidence: 'unknown', reason: 'NO_REVIEWED_INDUSTRY_CLASSIFICATION',
  };
  const code = normalizeText(raw.industry_code).toUpperCase();
  // Numeric descendants are admitted only for the explicitly approved groups.
  const core = CORE_PLUS_CODES.find(group => code === group || (/^\d{3}$/.test(group) && new RegExp(`^${group}\\d$`).test(code))) || null;
  return { industry_code: code, sector: normalizeText(raw.sector), core_plus_code: core,
    classification_source: evidence.source_url, classification_confidence: evidence.kind,
    reason: core ? 'REVIEWED_CORE_PLUS_CODE' : 'REVIEWED_CODE_OUTSIDE_EXPLICIT_CORE_PLUS_MAPPING' };
}
