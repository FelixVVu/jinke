import { createHash } from 'node:crypto';
export const VERSION = 'company-access-offline-v1';
export const compare = (a, b) => a < b ? -1 : a > b ? 1 : 0;
export function stable(value) {
  return JSON.stringify(value, function (_, item) {
    return item && typeof item === 'object' && !Array.isArray(item)
      ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item;
  });
}
export const sha256 = value => createHash('sha256').update(value).digest('hex');
export const idFor = (prefix, value) => `${prefix}-${sha256(stable(value)).slice(0, 24)}`;
export function fail(code, detail) { throw Object.assign(new TypeError(detail || code), { code }); }
export function distance(a, b) {
  const rad = Math.PI / 180;
  const dLat = (a[1] - b[1]) * rad, dLng = (a[0] - b[0]) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLng / 2) ** 2;
  return 6371008.8 * 2 * Math.asin(Math.sqrt(Math.min(1, h)));
}
export const defaults = Object.freeze({ duplicate_metres: 15, include_approximate: false,
  cluster_metres: 0, cluster_min_offices: 2 });
export function validateSettings(input = {}) {
  if (!input || typeof input !== 'object' || Array.isArray(input) || Object.keys(input).some(key => !Object.hasOwn(defaults, key))) fail('INVALID_SETTINGS');
  const settings = { ...defaults, ...input };
  if (!Number.isFinite(settings.duplicate_metres) || settings.duplicate_metres < 0 || settings.duplicate_metres > 50 ||
    typeof settings.include_approximate !== 'boolean' || !Number.isFinite(settings.cluster_metres) || settings.cluster_metres < 0 || settings.cluster_metres > 250 ||
    !Number.isInteger(settings.cluster_min_offices) || settings.cluster_min_offices < 2 || settings.cluster_min_offices > 100) fail('INVALID_SETTINGS');
  return settings;
}
