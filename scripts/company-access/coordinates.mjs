// Keep AMap search and offline ingestion on exactly the same GCJ inverse.
import { gcj02ToWgs84 } from '../../web/src/location-search.js';
import { fail } from './common.mjs';
export const CONVERSION_VERSION = 'jinke-amap-iterative10-1e8+bd09-v1';
export function bd09ToGcj02(lng, lat) {
  const x = lng - 0.0065, y = lat - 0.006;
  const xPi = Math.PI * 3000 / 180;
  const z = Math.sqrt(x * x + y * y) - 0.00002 * Math.sin(y * xPi);
  const theta = Math.atan2(y, x) - 0.000003 * Math.cos(x * xPi);
  return [z * Math.cos(theta), z * Math.sin(theta)];
}
export function normalizeCoordinates(raw) {
  const { longitude, latitude, coordinate_system } = raw;
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude) || Math.abs(longitude) > 180 || Math.abs(latitude) > 90) fail('INVALID_COORDINATES');
  if (!['WGS84', 'GCJ02', 'BD09'].includes(coordinate_system)) fail('UNKNOWN_COORDINATE_SYSTEM');
  // Do not extend China-specific transforms to unsupported areas.
  if (coordinate_system !== 'WGS84' && (longitude < 72.004 || longitude > 137.8347 || latitude < 0.8293 || latitude > 55.8271)) fail('CONVERSION_OUTSIDE_SUPPORTED_REGION');
  const gcj = coordinate_system === 'BD09' ? bd09ToGcj02(longitude, latitude) : [longitude, latitude];
  const coordinates = coordinate_system === 'WGS84' ? gcj : gcj02ToWgs84(...gcj);
  return { coordinates, audit: {
    raw_longitude: longitude, raw_latitude: latitude, raw_coordinate_system: coordinate_system,
    conversion_method: { WGS84: 'identity', GCJ02: 'jinke-amap-gcj02-to-wgs84', BD09: 'bd09-to-gcj02-to-jinke-wgs84' }[coordinate_system],
    conversion_version: CONVERSION_VERSION,
  } };
}
