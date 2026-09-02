export const ALL_REACH_BANDS = Object.freeze([
  Object.freeze({
    start: 0,
    end: 10,
    label: '0–10 min',
    fillColor: '#006f73',
    fillOpacity: 0.07,
    legendFill: 'rgba(0, 111, 115, 0.07)',
    borderColor: '#004f54',
    borderWidth: 2.4,
  }),
  Object.freeze({
    start: 10,
    end: 20,
    label: '10–20 min',
    fillColor: '#138a8c',
    fillOpacity: 0.06,
    legendFill: 'rgba(19, 138, 140, 0.06)',
    borderColor: '#0a7075',
    borderWidth: 2.1,
  }),
  Object.freeze({
    start: 20,
    end: 30,
    label: '20–30 min',
    fillColor: '#2fa3a0',
    fillOpacity: 0.05,
    legendFill: 'rgba(47, 163, 160, 0.05)',
    borderColor: '#218e8e',
    borderWidth: 1.8,
  }),
  Object.freeze({
    start: 30,
    end: 40,
    label: '30–40 min',
    fillColor: '#6bc6bf',
    fillOpacity: 0.04,
    legendFill: 'rgba(107, 198, 191, 0.04)',
    borderColor: '#55b4ae',
    borderWidth: 1.6,
  }),
  Object.freeze({
    start: 40,
    end: 50,
    label: '40–50 min',
    fillColor: '#b9e8e4',
    fillOpacity: 0.03,
    legendFill: 'rgba(185, 232, 228, 0.03)',
    borderColor: '#91d6d2',
    borderWidth: 1.9,
  }),
]);

function geometryAsMultiPolygon(geometry) {
  if (geometry?.type === 'Polygon') return [geometry.coordinates];
  if (geometry?.type === 'MultiPolygon') return geometry.coordinates;
  throw new TypeError('Reach bands require Polygon or MultiPolygon geometry.');
}

function featureAtLimit(collection, limit) {
  return collection?.features?.find(
    feature => Number(feature?.properties?.limit) === Number(limit),
  );
}

function polygonClipper() {
  const clipper = globalThis.polygonClipping;
  if (!clipper || typeof clipper.difference !== 'function') {
    throw new Error('Polygon clipping is unavailable.');
  }
  return clipper;
}

export function buildReachBandCollection(collection) {
  return buildReachBandView(collection).bands;
}

export function buildReachBandView(collection) {
  const clipper = polygonClipper();
  const outerFeature = featureAtLimit(
    collection,
    ALL_REACH_BANDS[ALL_REACH_BANDS.length - 1].end,
  );
  if (!outerFeature) throw new Error('Missing 50-minute reach geometry.');
  const outerReach = geometryAsMultiPolygon(outerFeature.geometry);
  let previousReach;
  const contourFeatures = [];

  const features = ALL_REACH_BANDS.map(band => {
    const sourceFeature = featureAtLimit(collection, band.end);
    if (!sourceFeature) {
      throw new Error(`Missing ${band.end}-minute reach geometry.`);
    }

    const currentReach = geometryAsMultiPolygon(sourceFeature.geometry);
    const clippedReach =
      band.end === ALL_REACH_BANDS[ALL_REACH_BANDS.length - 1].end
        ? outerReach
        : clipper.intersection(currentReach, outerReach);
    const nestedReach = previousReach
      ? band.end === ALL_REACH_BANDS[ALL_REACH_BANDS.length - 1].end
        ? outerReach
        : clipper.union(previousReach, clippedReach)
      : clippedReach;
    const bandCoordinates = previousReach
      ? clipper.difference(nestedReach, previousReach)
      : nestedReach;
    previousReach = nestedReach;

    contourFeatures.push({
      type: 'Feature',
      properties: {
        limit: band.end,
        band_label: band.label,
      },
      geometry: {
        type: 'MultiPolygon',
        coordinates: nestedReach,
      },
    });

    return {
      type: 'Feature',
      properties: {
        band_start: band.start,
        band_end: band.end,
        band_label: band.label,
      },
      geometry: {
        type: 'MultiPolygon',
        coordinates: bandCoordinates,
      },
    };
  });

  return {
    bands: {
      type: 'FeatureCollection',
      features,
    },
    contours: {
      type: 'FeatureCollection',
      features: contourFeatures,
    },
  };
}

export function bandStyleExpression(property, fallback) {
  return [
    'match',
    ['get', 'band_end'],
    ...ALL_REACH_BANDS.flatMap(band => [band.end, band[property]]),
    fallback,
  ];
}

export function contourStyleExpression(property, fallback) {
  return [
    'match',
    ['get', 'limit'],
    ...ALL_REACH_BANDS.flatMap(band => [band.end, band[property]]),
    fallback,
  ];
}
