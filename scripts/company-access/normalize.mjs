import { normalizeCompanyName } from '../../web/src/company-access/schema.js';

// No legal suffix removal, transliteration, translation, or token reordering.
export const normalizeText = value => value == null ? null : value.normalize('NFKC').replace(/\s+/gu, ' ').trim();
export const nameKey = value => normalizeCompanyName(normalizeText(value));
export const addressKey = value => normalizeText(value).toLowerCase()
  .replace(/[，、]/gu, ',').replace(/[“”]/gu, '"').replace(/[‘’]/gu, "'")
  .replace(/\s*([,;:()])\s*/gu, '$1');

// Explicit aliases only. Unknown district spellings are retained, never guessed.
const districts = [
  ['浦东新区', 'pudong', 'pudong new area'], ['黄浦区', 'huangpu'],
  ['徐汇区', 'xuhui'], ['长宁区', 'changning'], ['静安区', 'jingan', "jing'an"],
  ['普陀区', 'putuo'], ['虹口区', 'hongkou'], ['杨浦区', 'yangpu'],
  ['闵行区', 'minhang'], ['宝山区', 'baoshan'], ['嘉定区', 'jiading'],
  ['金山区', 'jinshan'], ['松江区', 'songjiang'], ['青浦区', 'qingpu'],
  ['奉贤区', 'fengxian'], ['崇明区', 'chongming'],
];
const aliases = new Map(districts.flatMap(([cn, ...en]) => [[cn, cn], ...en.flatMap(name => [[name, cn], [`${name} district`, cn]])]));
export function normalizeDistrict(value) {
  const normalized = normalizeText(value);
  return normalized === null ? null : aliases.get(normalized.toLowerCase()) || normalized;
}
export function normalizeRecord(raw) {
  return { company_name: normalizeText(raw.company_name), normalized_name: nameKey(raw.company_name),
    name_variants: [...new Set((raw.name_variants || []).map(nameKey))].sort(),
    address: normalizeText(raw.address), address_key: addressKey(raw.address),
    district: normalizeDistrict(raw.district), building_name: normalizeText(raw.building_name),
    building_key: raw.building_name == null ? null : addressKey(raw.building_name),
  };
}
