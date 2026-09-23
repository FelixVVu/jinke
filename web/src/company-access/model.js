import { pointInGeoJson } from '../location-search.js';
import { COMPANY_DISCLOSURE, REACH_MINUTES, validateOffice } from './schema.js';

const collection = features => ({ type: 'FeatureCollection', features });
const point = (id, coordinates, properties) => ({ type: 'Feature', id,
  geometry: { type: 'Point', coordinates }, properties });

export function validateReachAreas(areas) {
  if (areas?.type !== 'FeatureCollection' || areas.features?.length !== 5) throw new TypeError('All five cumulative reach polygons are required.');
  const byLimit = new Map();
  for (const feature of areas.features) {
    const limit = feature.properties?.limit;
    const geometry = feature.geometry;
    if (!REACH_MINUTES.includes(limit) || byLimit.has(limit) || !['Polygon', 'MultiPolygon'].includes(geometry?.type)) throw new TypeError('Invalid cumulative reach polygon.');
    const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
    if (!Array.isArray(polygons) || !polygons.length) throw new TypeError('Empty reach geometry.');
    for (const polygon of polygons) {
      if (!Array.isArray(polygon) || !polygon.length) throw new TypeError('Missing polygon shell.');
      for (const ring of polygon) {
        if (!Array.isArray(ring) || ring.length < 4 || ring.some(p => !Array.isArray(p) || p.length !== 2 || !p.every(Number.isFinite) || Math.abs(p[0]) > 180 || Math.abs(p[1]) > 90) || JSON.stringify(ring[0]) !== JSON.stringify(ring.at(-1))) throw new TypeError('Invalid reach ring.');
      }
    }
    byLimit.set(limit, feature);
  }
  return byLimit;
}

// Bboxes only shortlist polygons; the existing exact containment code is authoritative.
export function prepareReachAreas(areas) {
  const byLimit = validateReachAreas(areas);
  const polygons = new Map([...byLimit].map(([limit, feature]) => [limit,
    (feature.geometry.type === 'Polygon' ? [feature.geometry.coordinates] : feature.geometry.coordinates).map(coordinates => {
      const box = [Infinity, Infinity, -Infinity, -Infinity];
      for (const [x, y] of coordinates[0]) {
        box[0] = Math.min(box[0], x); box[1] = Math.min(box[1], y);
        box[2] = Math.max(box[2], x); box[3] = Math.max(box[3], y);
      }
      return { box, geometry: { type: 'Polygon', coordinates } };
    })]));
  byLimit.contains = ([x, y], limit) => polygons.get(limit).some(({box, geometry}) =>
    x >= box[0] - 1e-8 && y >= box[1] - 1e-8 && x <= box[2] + 1e-8 && y <= box[3] + 1e-8 && pointInGeoJson([x, y], geometry));
  return byLimit;
}

export function reachMemberships(office, byLimit) {
  const point = [office.longitude, office.latitude];
  return REACH_MINUTES.filter(limit => byLimit.contains
    ? byLimit.contains(point, limit) : pointInGeoJson(point, byLimit.get(limit)));
}

/** Pure, deterministic derivation. No imports from economic or density models. */
export function deriveCompanyAccess(offices, areas, provenance) {
  if (!Array.isArray(offices)) throw new TypeError('Offices must be an array.');
  if (!provenance || !['not_loaded', 'ready'].includes(provenance.status) ||
      typeof provenance.dataset_version !== 'string' || !provenance.dataset_version.trim() ||
      !/^[a-f0-9]{64}$/.test(provenance.reach_sha256 || '') ||
      !/^[a-f0-9]{64}$/.test(provenance.inventory_sha256 || '')) throw new TypeError('Dataset version and SHA-256 provenance are required.');
  if (provenance.status === 'not_loaded' && offices.length) throw new TypeError('Unloaded inventory cannot contain offices.');
  const byLimit = prepareReachAreas(areas);
  const ids = new Set();
  const sourceLocations = new Set();
  const hubNames = new Map();
  const normalizedNames = new Map();
  const features = offices.map(office => {
    validateOffice(office);
    if (ids.has(office.id)) throw new TypeError(`Duplicate office id: ${office.id}`);
    ids.add(office.id);
    const sourceLocation = JSON.stringify([office.source_type, office.source_id, office.longitude, office.latitude]);
    if (sourceLocations.has(sourceLocation)) throw new TypeError('Duplicate source office location.');
    sourceLocations.add(sourceLocation);
    if (office.hub_id !== null) {
      if (hubNames.has(office.hub_id) && hubNames.get(office.hub_id) !== office.hub_name) throw new TypeError('Conflicting hub names.');
      hubNames.set(office.hub_id, office.hub_name);
    }
    normalizedNames.set(office.normalized_name, (normalizedNames.get(office.normalized_name) || 0) + 1);
    const reach_minutes = reachMemberships(office, byLimit);
    if (office.min_reach_minutes !== (reach_minutes[0] ?? null)) throw new TypeError(`Stale min_reach_minutes for ${office.id}.`);
    return point(office.id, [office.longitude, office.latitude], { ...office, reach_minutes });
  }).sort((a, b) => a.id.localeCompare(b.id));
  const hubMembers = new Map();
  for (const feature of features) {
    const id = feature.properties.hub_id;
    if (id === null) continue;
    if (!hubMembers.has(id)) hubMembers.set(id, []);
    hubMembers.get(id).push(feature);
  }
  const hubFeatures = [...hubNames.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([id, hub_name]) => {
    const members = hubMembers.get(id);
    // Representative office coordinate, NOT a new geocoded building centroid.
    return point(id, [...members[0].geometry.coordinates], {
      hub_id: id, hub_name, representative_office_id: members[0].id,
      office_ids: members.map(f => f.id), office_count: members.length,
      counts_by_reach: Object.fromEntries(REACH_MINUTES.map(limit => [limit, members.filter(f => f.properties.reach_minutes.includes(limit)).length])),
    });
  });
  const summary = { unit: 'company_offices', status: provenance.status,
    records: REACH_MINUTES.map(limit => {
      const selected = features.filter(f => f.properties.reach_minutes.includes(limit));
      return { limit_minutes: limit,
        office_count: provenance.status === 'ready' ? selected.length : null,
        hub_count: provenance.status === 'ready' ? new Set(selected.map(f => f.properties.hub_id).filter(id => id !== null)).size : null,
        unassigned_hub_office_count: provenance.status === 'ready' ? selected.filter(f => f.properties.hub_id === null).length : null,
      };
    }) };
  const metadata = { schema_version: 1, ...provenance, coordinate_system: 'WGS84',
    disclosure: COMPANY_DISCLOSURE, employment_estimation_permitted: false,
    coverage: 'source_inventory_only', boundary_policy: 'covers_including_hole_boundary',
    office_count: offices.length,
    source_counts: Object.fromEntries([...new Set(offices.map(o => o.source_type))].sort().map(type => [type, offices.filter(o => o.source_type === type).length])),
    quality: {
      unverified: offices.filter(o => o.verified_at === null).length,
      approximate: offices.filter(o => o.location_confidence === 'approximate').length,
      outside_50: features.filter(f => !f.properties.reach_minutes.includes(50)).length,
      repeated_normalized_names: [...normalizedNames].filter(([, count]) => count > 1).map(([name]) => name).sort(),
      non_nested_memberships: features.filter(f => {
        const m = f.properties.reach_minutes;
        return m.length && REACH_MINUTES.filter(v => v >= m[0]).join() !== m.join();
      }).map(f => f.id),
    },
  };
  return { offices: collection(features), hubs: collection(hubFeatures), summary, metadata };
}

export function selectCompanyOffices(output, limit) {
  const minutes = limit === 'all' ? 50 : limit;
  if (!REACH_MINUTES.includes(minutes)) throw new TypeError('Invalid company reach limit.');
  return collection(output?.offices.features.filter(f => f.properties.reach_minutes.includes(minutes)) || []);
}

/** Validate separately serialized derived artifacts against canonical input. */
export function validateCompanyAccessOutput(output, offices, areas, provenance) {
  const expected = deriveCompanyAccess(offices, areas, provenance);
  // Stable serialization ignores object key order, but preserves array ordering.
  const stable = value => JSON.stringify(value, function (key, item) {
    return item && typeof item === 'object' && !Array.isArray(item)
      ? Object.fromEntries(Object.keys(item).sort().map(k => [k, item[k]])) : item;
  });
  for (const key of ['offices', 'hubs', 'summary', 'metadata']) {
    if (stable(output?.[key]) !== stable(expected[key])) throw new TypeError(`Company ${key} does not reconcile with source offices and reach geometry.`);
  }
  return output;
}
