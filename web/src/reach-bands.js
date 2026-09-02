export const ALL_REACH_BANDS = Object.freeze([
  Object.freeze({
    start: 0,
    end: 10,
    label: '0–10 min',
    fillColor: '#0f766e',
    fillOpacity: 0.1,
    legendFill: 'rgba(15, 118, 110, 0.10)',
    borderColor: '#0a5f58',
    borderWidth: 1.55,
  }),
  Object.freeze({
    start: 10,
    end: 20,
    label: '10–20 min',
    fillColor: '#16877f',
    fillOpacity: 0.085,
    legendFill: 'rgba(22, 135, 127, 0.085)',
    borderColor: '#16776f',
    borderWidth: 1.55,
  }),
  Object.freeze({
    start: 20,
    end: 30,
    label: '20–30 min',
    fillColor: '#2d9c94',
    fillOpacity: 0.07,
    legendFill: 'rgba(45, 156, 148, 0.07)',
    borderColor: '#2b9188',
    borderWidth: 1.65,
  }),
  Object.freeze({
    start: 30,
    end: 40,
    label: '30–40 min',
    fillColor: '#58b8af',
    fillOpacity: 0.055,
    legendFill: 'rgba(88, 184, 175, 0.055)',
    borderColor: '#4ba79f',
    borderWidth: 1.75,
  }),
  Object.freeze({
    start: 40,
    end: 50,
    label: '40–50 min',
    fillColor: '#93d3cd',
    fillOpacity: 0.04,
    legendFill: 'rgba(147, 211, 205, 0.04)',
    borderColor: '#72c1ba',
    borderWidth: 2.15,
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
