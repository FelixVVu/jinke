import { readFileSync } from 'node:fs';
import { fail } from './common.mjs';
export const rawSchema = JSON.parse(readFileSync(new URL('./raw-schema.json', import.meta.url), 'utf8'));

// Deliberately implements only keywords used by this checked-in schema; no framework.
function check(value, schema, path = 'record') {
  const type = value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value;
  if (schema.type && ![schema.type].flat().includes(type)) fail('RAW_SCHEMA_TYPE', path);
  if (Object.hasOwn(schema, 'const') && value !== schema.const) fail('RAW_SCHEMA_VALUE', path);
  if (schema.enum && !schema.enum.includes(value)) fail('RAW_SCHEMA_VALUE', path);
  if (type === 'number' && (!Number.isFinite(value) || value < schema.minimum || value > schema.maximum)) fail('INVALID_COORDINATES', path);
  if (type === 'string' && schema.minLength && !value.trim()) fail('RAW_EMPTY_FIELD', path);
  if (schema.format && value !== null) {
    if (schema.format === 'uri' || schema.format === 'http-url') {
      let url; try { url = new URL(value); } catch { fail('INVALID_SOURCE_URL', path); }
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) fail('INVALID_SOURCE_URL', path);
    } else if (schema.format === 'date-time') {
      if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(value) || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0,19) !== value.slice(0,19)) fail('INVALID_TIMESTAMP', path);
    }
  }
  if (schema.type === 'object') {
    for (const key of schema.required || []) if (!Object.hasOwn(value,key)) fail('RAW_MISSING_FIELD', `${path}.${key}`);
    for (const key of Object.keys(value)) {
      if (!Object.hasOwn(schema.properties,key)) fail('RAW_UNKNOWN_FIELD', `${path}.${key}`);
      check(value[key],schema.properties[key],`${path}.${key}`);
    }
  }
  if (schema.type === 'array') for (const item of value) check(item,schema.items,`${path}[]`);
}
export function validateRawRecord(record) { check(record,rawSchema); return record; }
export function validateEnvelope(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input) || input.schema_version !== 1 ||
    !['synthetic','candidate'].includes(input.dataset_kind) || typeof input.dataset_version !== 'string' || !input.dataset_version.trim() ||
    !Array.isArray(input.records) || Object.keys(input).some(key => !['schema_version','dataset_kind','dataset_version','records'].includes(key))) fail('INVALID_RAW_ENVELOPE');
  return input;
}
