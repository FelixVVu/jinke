/** Canonical contract for one physical company office, never an employee count. */
export const REACH_MINUTES = Object.freeze([10, 20, 30, 40, 50]);
const text = { type: 'string', minLength: 1 };
const nullableText = { type: ['string', 'null'], minLength: 1 };
export const officeSchema = {
  $schema: 'https://json-schema.org/draft/2020-12/schema',
  title: 'Jinke company office v1 (canonical WGS84)',
  type: 'object', additionalProperties: false,
  required: ['id', 'company_name', 'normalized_name', 'longitude', 'latitude',
    'coordinate_system', 'district', 'address', 'building_name', 'hub_id',
    'hub_name', 'industry_code', 'sector', 'location_confidence', 'source_type',
    'source_id', 'source_url', 'verified_at', 'min_reach_minutes'],
  properties: {
    id: text, company_name: text, normalized_name: text,
    longitude: { type: 'number', minimum: -180, maximum: 180 },
    latitude: { type: 'number', minimum: -90, maximum: 90 },
    coordinate_system: { const: 'WGS84' },
    district: nullableText, address: text, building_name: nullableText,
    hub_id: nullableText, hub_name: nullableText,
    industry_code: nullableText, sector: nullableText,
    location_confidence: { enum: ['verified', 'building', 'approximate'] },
    source_type: { enum: ['company_website', 'building_directory', 'government', 'licensed_poi', 'osm', 'other'] },
    source_id: text, source_url: { type: 'string', format: 'uri' },
    verified_at: { type: ['string', 'null'], format: 'date-time' },
    min_reach_minutes: { enum: [...REACH_MINUTES, null] },
  },
};

export const COMPANY_DISCLOSURE =
  'Company-office counts are not employment counts. Coverage reflects the sourced office inventory, not all Shanghai companies.';

export function normalizeCompanyName(name) {
  // Deliberately no legal-suffix removal or fuzzy identity merging.
  return name.normalize('NFKC').trim().replace(/\s+/gu, ' ').toLowerCase();
}

export function validateOffice(office) {
  if (!office || typeof office !== 'object' || Array.isArray(office)) throw new TypeError('Office must be an object.');
  for (const key of officeSchema.required) {
    if (!Object.hasOwn(office, key)) throw new TypeError(`Missing office field: ${key}`);
  }
  for (const [key, value] of Object.entries(office)) {
    const rule = Object.hasOwn(officeSchema.properties, key) ? officeSchema.properties[key] : null;
    if (!rule) throw new TypeError(`Unknown office field: ${key}`);
    if (rule.type && ![rule.type].flat().includes(value === null ? 'null' : typeof value)) throw new TypeError(`Invalid ${key} type.`);
    if (rule.const && value !== rule.const) throw new TypeError(`${key} must be ${rule.const}; convert coordinates before ingestion.`);
    if (rule.enum && !rule.enum.includes(value)) throw new TypeError(`Invalid ${key}.`);
    if (typeof value === 'number' && (!Number.isFinite(value) || value < rule.minimum || value > rule.maximum)) throw new TypeError(`Invalid ${key} range.`);
    if (typeof value === 'string' && rule.minLength && !value.trim()) throw new TypeError(`Empty ${key}.`);
    if (rule.format === 'uri') {
      let url;
      try { url = new URL(value); } catch { throw new TypeError('Invalid source_url.'); }
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new TypeError('source_url must be an HTTP(S) evidence URL.');
    }
    if (rule.format === 'date-time' && value !== null &&
        (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(value) ||
         !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 19) !== value.slice(0, 19))) {
      throw new TypeError('verified_at must be a valid UTC timestamp or null.');
    }
  }
  if (office.normalized_name !== normalizeCompanyName(office.company_name)) throw new TypeError('normalized_name does not reconcile.');
  if ((office.hub_id === null) !== (office.hub_name === null)) throw new TypeError('hub_id and hub_name must be supplied together.');
  if (office.location_confidence === 'verified' && office.verified_at === null) throw new TypeError('Verified locations require verified_at.');
  return office;
}
