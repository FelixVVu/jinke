export const OFFICE_EMPLOYMENT_LIMITS = Object.freeze([10, 20, 30, 40, 50]);
export const OFFICE_BENCHMARK_KEYS = Object.freeze(['core_plus_base', 'core']);
export const OFFICE_DENSITY_DISCLOSURE =
  'Office-employment density is modelled from official 2023 employment controls and workplace/building evidence. Heatmap smoothing is for visualization only; reach statistics use the unsmoothed 100 m analytical grid.';

const EXPECTED_DENOMINATORS = Object.freeze({
  core: 2_477_585,
  core_plus_base: 3_220_710,
});

const EXPECTED_50_MINUTE_RESULTS = Object.freeze({
  core: Object.freeze({ employment: 945_831.540970, share: 38.1755436 }),
  core_plus_base: Object.freeze({
    employment: 1_212_066.713237,
    share: 37.6335253,
  }),
});

function finiteNonNegative(value) {
  return Number.isFinite(value) && value >= 0;
}

function closeEnough(actual, expected, tolerance = 1e-7) {
  return Math.abs(actual - expected) <= tolerance;
}

export function validateOfficeEmploymentPayload(
  payload,
  methodology,
  expectedLimits = OFFICE_EMPLOYMENT_LIMITS,
) {
  if (
    payload?.primary_benchmark !== 'core_plus_base' ||
    payload?.analytical_grid_metres !== 100 ||
    payload?.analytical_grid_smoothed !== false ||
    payload?.display_density_used_for_statistics !== false
  ) {
    throw new TypeError('Office benchmark analytical provenance is invalid.');
  }
  if (
    payload?.source_commit !== methodology?.source_commit ||
    methodology?.classification !== 'USABLE WITH CAUTION' ||
    methodology?.required_disclosure !== OFFICE_DENSITY_DISCLOSURE ||
    methodology?.reach_statistics?.rendered_heatmap_used !== false
  ) {
    throw new TypeError('Office benchmark methodology is incomplete.');
  }

  const includedCodes = methodology?.definitions?.core_plus_base?.industry_codes;
  if (
    !Array.isArray(includedCodes) ||
    includedCodes.join(',') !== 'I,J,M,721,723,724,725' ||
    includedCodes.includes('726')
  ) {
    throw new TypeError('Core+ industry definition is invalid.');
  }

  const benchmarksByKey = new Map();
  for (const key of OFFICE_BENCHMARK_KEYS) {
    const benchmark = payload?.benchmarks?.[key];
    const denominator = Number(benchmark?.denominator);
    if (
      denominator !== EXPECTED_DENOMINATORS[key] ||
      Number(methodology?.definitions?.[key]?.denominator) !== denominator
    ) {
      throw new TypeError(`${key} uses the wrong Shanghai denominator.`);
    }
    if (!Array.isArray(benchmark.records) || benchmark.records.length !== expectedLimits.length) {
      throw new TypeError(`${key} must contain exactly five reach records.`);
    }

    const recordsByLimit = new Map();
    let previousEmployment = 0;
    benchmark.records.forEach((record, index) => {
      const limit = Number(record?.limit_minutes);
      const employment = Number(record?.employment_inside_reach);
      const share = Number(record?.percentage_of_shanghai);
      const increment = Number(record?.incremental_employment);
      if (
        limit !== expectedLimits[index] ||
        !finiteNonNegative(employment) ||
        !finiteNonNegative(share) ||
        !finiteNonNegative(increment) ||
        employment < previousEmployment ||
        !closeEnough(share, (employment / denominator) * 100, 1e-9) ||
        !closeEnough(increment, employment - previousEmployment, 1e-7)
      ) {
        throw new TypeError(`${key} reach record does not reconcile at ${limit} minutes.`);
      }
      recordsByLimit.set(limit, record);
      previousEmployment = employment;
    });

    const fifty = recordsByLimit.get(50);
    const approved = EXPECTED_50_MINUTE_RESULTS[key];
    if (
      !closeEnough(Number(fifty.employment_inside_reach), approved.employment, 5e-7) ||
      !closeEnough(Number(fifty.percentage_of_shanghai), approved.share, 5e-8)
    ) {
      throw new TypeError(`Approved ${key} 50-minute result changed.`);
    }
    benchmarksByKey.set(key, { ...benchmark, recordsByLimit });
  }

  return {
    primaryBenchmark: payload.primary_benchmark,
    benchmarksByKey,
  };
}

export function validateOfficeDensityPayload(payload, methodology) {
  const metadata = payload?.metadata;
  if (
    payload?.type !== 'FeatureCollection' ||
    !Array.isArray(payload.features) ||
    payload.features.length !== Number(metadata?.feature_count) ||
    metadata?.display_only !== true ||
    metadata?.analytical_use_prohibited !== true ||
    metadata?.source_grid_metres !== 100 ||
    metadata?.aggregation_metres !== 400 ||
    metadata?.disclosure !== OFFICE_DENSITY_DISCLOSURE ||
    metadata?.source_grid_sha256 !== methodology?.source_hashes?.core_plus_grid
  ) {
    throw new TypeError('Office-density display provenance is invalid.');
  }
  if (
    !payload.features.every(feature => {
      const coordinates = feature?.geometry?.coordinates;
      const weight = Number(feature?.properties?.w);
      const jobs = Number(feature?.properties?.j);
      return (
        feature?.geometry?.type === 'Point' &&
        Array.isArray(coordinates) &&
        coordinates.length === 2 &&
        coordinates.every(Number.isFinite) &&
        finiteNonNegative(jobs) &&
        finiteNonNegative(weight) &&
        weight <= 1
      );
    })
  ) {
    throw new TypeError('Office-density display features are invalid.');
  }
  return payload;
}

export function formatOfficeEmployment(value) {
  const employment = Number(value);
  return finiteNonNegative(employment)
    ? Math.round(employment).toLocaleString('en-US')
    : '—';
}

export function formatOfficeShare(value) {
  const share = Number(value);
  return finiteNonNegative(share) ? `${share.toFixed(2)}%` : '—';
}

export function officeMethodologyText(methodology) {
  const core = methodology.definitions.core;
  const corePlus = methodology.definitions.core_plus_base;
  return {
    definition:
      `${corePlus.label} covers ${corePlus.industry_codes.join(', ')}; ` +
      `${core.label} (${core.industry_codes.join(', ')}) remains available as the conservative benchmark.`,
    controls: methodology.allocation.hard_controls,
    boundaries: methodology.approximate_boundary_disclosure,
    scope: methodology.priority_district_scope_note,
    disclosure: methodology.required_disclosure,
  };
}
