# Independent employment benchmark v1

This directory contains an audit-only benchmark of **2023 secondary- and
tertiary-sector legal-entity workplace employment**. Its denominator is fixed at
13,099,795 workers as of 31 December 2023. Individual-business employment is not
included. The pipeline is separate from `gdp_pipeline` and does not regenerate the
production reach polygons.

## Reproduce

Create an isolated environment from `requirements-employment.txt`. Keep large or
restricted inputs outside the repository, then run:

```bash
python scripts/prepare_employment_inputs.py \
  --repository-root . \
  --source-cache /absolute/path/to/employment-source-cache \
  --xuhui-bulletin /absolute/path/to/xuhui-original.pdf

python scripts/run_employment_benchmark.py \
  --repository-root . \
  --source-cache /absolute/path/to/employment-source-cache
```

After the benchmark outputs exist, reproduce the allocation-free 50-minute
structural-certainty audit without the external source cache and without refitting
PPML:

```bash
python scripts/run_employment_structural_certainty.py --repository-root .
```

The structural audit classifies all 116 selected supports against the pinned
production 50-minute polygon, reports fine-control geometric bounds, decomposes
partial-control model spread, and keeps residual-location and Pudong zone-boundary
uncertainty in separate ledgers. Its report and CSV/JSON evidence are written under
`data/employment/outputs/structural-certainty-*`.

The preparation step verifies every frozen source hash, extracts exactly 113 OSM
relations, rejects non-exact name matches, and rebuilds the manifests. The model
step reads the production reaches but cannot write or regenerate them; it fails if
their SHA-256 differs from the pinned value.

## Boundary disclosure and licenses

- Ordinary street/town geometry is extracted from the 19 August 2026 Shanghai OSM
  PBF. It is licensed under ODbL 1.0 and must retain attribution to OpenStreetMap
  contributors. It is a cross-walked approximation, not an official 2023
  accounting boundary.
- The three Pudong functional-zone supports are approximate 2020 statistical
  polygons acquired from Ruiduobao. Its terms limit use to academic/education
  reference and prohibit commercial use. The source geometries must remain in the
  external cache and must not be committed or redistributed. The public Parquet
  contains one null-geometry aggregate ledger row per restricted stratum.
- JRC non-residential built volume and Overture Places remain external inputs. The
  source manifest records release, URL, checksum, license/attribution, and use.

Every public result carries `geometry_is_approximate = true`. Geometric overlap
between a Pudong functional zone and a street/town is intentional: each is a
separate census accounting stratum, and each employment row enters exactly once.

## Official-map validation

Reach-relevant control segments were reviewed against the authoritative Shanghai
Tianditu standard map and its `SHMAP_D`/`SHMAP_LAN` display services on 19 August
2026. The review used WGS84 bbox `121.33,31.015,121.83,31.325` at `4096x2540`
pixels. Source-image and audit-overlay hashes are retained in
`intermediate/official-map-visual-review.csv`; the display images are not
redistributed. A pass means no visible material contradiction at that display
precision, not government endorsement or official-boundary equivalence.

The three zone supports remain failed for scope equivalence. Their selected,
official-reported-area morphology, and conservative 0%/100% reach allocations are
reported separately. The reported-area morphology is not an official vector.

## Checked-in outputs

- `manifests/` preserves census identity, rounding intervals, residuals, sources,
  relation IDs, and boundary terms.
- `intermediate/employment-allocation-grid.parquet` is the auditable 100 m grid;
  restricted source geometry is redacted.
- `outputs/` contains reach, district, Pudong-stratum, and Minhang diagnostics.
- `web/public/data/reach-employment.json` and
  `web/public/data/employment-methodology.json` are intentionally not wired into
  the production UI.
