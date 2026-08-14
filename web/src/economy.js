export const ECONOMY_LIMITS = Object.freeze([10, 20, 30, 40, 50]);
export const GDP_100M_CNY_PER_TRILLION_CNY = 10_000;

const ESTIMATE_FIELDS = Object.freeze([
  'estimated_gdp_100m_cny',
  'percentage_of_shanghai_gdp',
  'incremental_gdp_100m_cny',
  'building_heavy_gdp_100m_cny',
  'activity_heavy_gdp_100m_cny',
]);

function finiteNonNegative(value) {
  return Number.isFinite(value) && value >= 0;
}

function closeEnough(actual, expected, tolerance = 1e-9) {
  return Math.abs(actual - expected) <= tolerance;
}

export function validateEconomyPayload(
  records,
  methodology,
  expectedLimits = ECONOMY_LIMITS,
) {
  if (!Array.isArray(records) || records.length !== expectedLimits.length) {
    throw new TypeError('Economic estimates must contain exactly five records.');
  }

  const actualLimits = records.map(record => Number(record?.limit_minutes));
  if (
    actualLimits.some((limit, index) => limit !== expectedLimits[index]) ||
    new Set(actualLimits).size !== expectedLimits.length
  ) {
    throw new TypeError('Economic estimates must cover 10/20/30/40/50 minutes once each.');
  }

  const officialGdp = methodology?.official_gdp;
  const cityGdp = Number(officialGdp?.official_city_gdp_100m_cny);
  if (!finiteNonNegative(cityGdp) || cityGdp === 0) {
    throw new TypeError('GDP methodology has no valid official Shanghai denominator.');
  }
  if (officialGdp?.unit !== '100 million current CNY (亿元)') {
    throw new TypeError('GDP methodology uses an unexpected currency unit.');
  }

  const methodologyLimits = methodology?.reach_polygons?.limits_minutes;
  if (
    !Array.isArray(methodologyLimits) ||
    methodologyLimits.join(',') !== expectedLimits.join(',')
  ) {
    throw new TypeError('GDP methodology reach limits do not match the map.');
  }

  let previousCentral = 0;
  let previousBuilding = 0;
  let previousActivity = 0;
  for (const record of records) {
    for (const field of ESTIMATE_FIELDS) {
      if (!finiteNonNegative(Number(record?.[field]))) {
        throw new TypeError(`Economic estimate ${field} is invalid.`);
      }
    }

    const central = Number(record.estimated_gdp_100m_cny);
    const building = Number(record.building_heavy_gdp_100m_cny);
    const activity = Number(record.activity_heavy_gdp_100m_cny);
    const expectedPercentage = (central / cityGdp) * 100;
    const expectedIncrement = central - previousCentral;
    if (
      !closeEnough(
        Number(record.percentage_of_shanghai_gdp),
        expectedPercentage,
      )
    ) {
      throw new TypeError('Economic estimate percentage uses the wrong denominator.');
    }
    if (
      !closeEnough(
        Number(record.incremental_gdp_100m_cny),
        expectedIncrement,
      )
    ) {
      throw new TypeError('Economic estimate increment does not reconcile.');
    }
    if (
      central < previousCentral ||
      building < previousBuilding ||
      activity < previousActivity
    ) {
      throw new TypeError('Economic estimates must be monotonic across limits.');
    }
    previousCentral = central;
    previousBuilding = building;
    previousActivity = activity;
  }

  const { jrc, viirs, overture } = methodology?.sources || {};
  const sensitivityDisclosure = methodology?.sensitivity_disclosure;
  if (
    !Number.isInteger(Number(officialGdp.year)) ||
    !jrc?.dataset ||
    !Number.isInteger(Number(jrc.epoch)) ||
    !viirs?.dataset ||
    !Number.isInteger(Number(viirs.year)) ||
    !viirs?.version ||
    !overture?.dataset ||
    !overture?.release ||
    typeof sensitivityDisclosure !== 'string' ||
    !/not confidence intervals/i.test(sensitivityDisclosure)
  ) {
    throw new TypeError('GDP methodology source versions are incomplete.');
  }

  return {
    cityGdp100mCny: cityGdp,
    recordsByLimit: new Map(
      records.map(record => [Number(record.limit_minutes), record]),
    ),
  };
}

export function formatTrillionCny(value100mCny, digits = 2) {
  const value = Number(value100mCny);
  if (!finiteNonNegative(value)) return '—';
  return `¥${(value / GDP_100M_CNY_PER_TRILLION_CNY).toFixed(digits)} tn`;
}

export function formatShanghaiShare(value) {
  const percentage = Number(value);
  return finiteNonNegative(percentage) ? `${percentage.toFixed(1)}%` : '—';
}

export function formatSensitivityRange(record) {
  const values = [
    Number(record?.building_heavy_gdp_100m_cny),
    Number(record?.activity_heavy_gdp_100m_cny),
  ];
  if (!values.every(finiteNonNegative)) return '—';
  const lower = Math.min(...values) / GDP_100M_CNY_PER_TRILLION_CNY;
  const upper = Math.max(...values) / GDP_100M_CNY_PER_TRILLION_CNY;
  return `¥${lower.toFixed(3)}–${upper.toFixed(3)} tn`;
}

export function methodologyText(methodology) {
  const official = methodology.official_gdp;
  const { jrc, viirs, overture } = methodology.sources;
  return {
    calibration:
      `Official ${official.year} district GDP is used as the calibration control.`,
    proxies:
      `Spatial allocation uses ${jrc.dataset} (${jrc.epoch} epoch), ` +
      `${viirs.dataset} (${viirs.year}, Version ${viirs.version}), and ` +
      `${overture.dataset} (release ${overture.release}).`,
    sensitivity:
      'The range shown above comes from the scenarios documented in the full ' +
      `methodology. ${methodology.sensitivity_disclosure}`,
  };
}
