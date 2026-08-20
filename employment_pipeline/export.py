"""Export the audit grid and lightweight, unwired web JSON artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if value is pd.NA or value is None:
        return None
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            _json_safe(payload),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
            default=_json_default,
        )
        + "\n",
        encoding="utf-8",
    )


def public_audit_grid(
    fine_grid: gpd.GeoDataFrame,
    residual_grid: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Redact the three restricted zone shapes while retaining their ledgers."""

    fine = fine_grid.copy()
    fine["cell_employment_residual_central"] = 0.0
    fine["geometry_redacted"] = False
    fine["redaction_reason"] = ""
    residual = residual_grid.copy()
    if not residual.empty:
        residual["geometry_redacted"] = False
        residual["redaction_reason"] = ""
    unrestricted = fine.loc[~fine["restricted_geometry"].astype(bool)].copy()
    restricted = fine.loc[fine["restricted_geometry"].astype(bool)].copy()
    aggregated_rows: list[dict[str, Any]] = []
    sum_columns = (
        "cell_area_m2",
        "area_fraction",
        "jrc_nres_volume_m3",
        "poi_business_finance",
        "poi_industry_logistics",
        "poi_education_research",
        "poi_retail_hospitality",
        "poi_health_public",
        "poi_other_economic",
        "overture_total_intensity",
        "cell_employment_uniform",
        "cell_employment_building_volume",
        "cell_employment_calibrated_workplace",
        "cell_employment_residual_central",
    )
    for control, group in restricted.groupby("accounting_control", sort=True):
        first = group.iloc[0]
        row = {column: first.get(column) for column in fine.columns if column != "geometry"}
        for column in sum_columns:
            row[column] = float(group[column].sum())
        row.update(
            {
                "cell_id": f"{control}:restricted-support-redacted",
                "grid_col": pd.NA,
                "grid_row": pd.NA,
                "center_x": np.nan,
                "center_y": np.nan,
                "geometry_redacted": True,
                "redaction_reason": (
                    "Source terms prohibit redistribution; this aggregate row preserves "
                    "the accounting/model totals but cannot reconstruct the source polygon."
                ),
                "geometry": None,
            }
        )
        aggregated_rows.append(row)
    redacted = gpd.GeoDataFrame(aggregated_rows, geometry="geometry", crs=fine.crs)
    combined_frames = [unrestricted, redacted]
    if not residual.empty:
        combined_frames.append(residual)
    combined = gpd.GeoDataFrame(
        pd.concat(combined_frames, ignore_index=True, sort=False),
        geometry="geometry",
        crs=fine.crs,
    )
    for column in (
        "cell_employment_uniform",
        "cell_employment_building_volume",
        "cell_employment_calibrated_workplace",
        "cell_employment_residual_central",
    ):
        combined[column] = pd.to_numeric(combined[column], errors="coerce").fillna(0.0)
    combined["cell_employment_preferred"] = (
        combined["cell_employment_calibrated_workplace"]
        + combined["cell_employment_residual_central"]
    )
    combined["geometry_is_approximate"] = True
    combined["grid_disclosure"] = np.where(
        combined["geometry_redacted"],
        "restricted functional-zone support aggregated and redacted",
        "100 m clipped analytical cell",
    )
    return combined


def write_decision_report(
    path: Path,
    *,
    reach_results: pd.DataFrame,
    district_contributions: pd.DataFrame,
    pudong_contributions: pd.DataFrame,
    methodology: dict[str, Any],
) -> None:
    fifty = reach_results.loc[reach_results["limit_minutes"] == 50].iloc[0]
    model = methodology["allocation_models"]["calibrated_workplace"]
    all_metrics = model["all_control_metrics"]
    top_metrics = model["top_employment_control_metrics"]
    gdp = methodology["gdp_diagnostic"]

    district_rows = []
    for row in district_contributions.itertuples(index=False):
        district_rows.append(
            "| {district_en} | {exact:,.0f} | {fine:,.0f} | {residual:,.0f} | "
            "{inside:,.0f} | {captured:.1f}% | {contribution:.1f}% | OSM; approximate |".format(
                district_en=row.district_en,
                exact=row.exact_district_employment,
                fine=row.fine_controlled_employment,
                residual=row.residual_employment,
                inside=row.employment_inside_50min,
                captured=row.percentage_of_district_employment_captured,
                contribution=row.contribution_to_total_reach_employment_percentage,
            )
        )
    pudong_rows = []
    for row in pudong_contributions.itertuples(index=False):
        pudong_rows.append(
            "| {name} | {total:,.0f} | {inside:,.0f} | {captured:.1f}% | yes |".format(
                name=row.reporting_stratum,
                total=row.stratum_employment,
                inside=row.employment_inside_50min,
                captured=row.percentage_captured,
            )
        )
    text = f"""# Jinke employment benchmark v1 decision report

## Primary result

**Estimated workplace employment within 50-minute reach: {fifty['central_estimated_employment'] / 1_000_000:.2f} million**

**{fifty['percentage_of_shanghai_employment']:.1f}% of Shanghai's 2023 secondary- and tertiary-sector legal-entity employment**

The exact denominator is 13,099,795. Individual-business employment is excluded.
All boundary supports are approximate.

## Uncertainty decomposition

- **Residual-location range:** {fifty['residual_lower_bound_percentage']:.1f}–{fifty['residual_upper_bound_percentage']:.1f}%
- **Spatial-allocation/model range:** {min(fifty['uniform_allocation_percentage'], fifty['building_volume_percentage'], fifty['calibrated_workplace_model_percentage']):.1f}–{max(fifty['uniform_allocation_percentage'], fifty['building_volume_percentage'], fifty['calibrated_workplace_model_percentage']):.1f}%
- **Boundary sensitivity:** ±{fifty['boundary_sensitivity_absolute_percentage_points']:.1f} percentage points (conservative asymmetric envelope {fifty['boundary_sensitivity_minus_percentage_points']:+.1f}/{fifty['boundary_sensitivity_plus_percentage_points']:+.1f}; reach-edge ±100 m alone {fifty['reach_edge_displacement_minus_percentage_points']:+.1f}/{fifty['reach_edge_displacement_plus_percentage_points']:+.1f})
- Publication rounding at 50 minutes is {methodology['rounding']['50min_minus_percentage_points']:+.3f}/{methodology['rounding']['50min_plus_percentage_points']:+.3f} percentage points and is immaterial.

These are separate sensitivity dimensions, not a confidence interval, and they are
not added together.

## Model comparison

| Model | Employment inside 50 min | Shanghai share |
|---|---:|---:|
| Uniform within control | {fifty['uniform_allocation_employment']:,.0f} | {fifty['uniform_allocation_percentage']:.3f}% |
| Raw JRC non-residential building volume | {fifty['building_volume_employment']:,.0f} | {fifty['building_volume_percentage']:.3f}% |
| Calibrated workplace PPML (model-contingent central) | {fifty['calibrated_workplace_model_employment']:,.0f} | {fifty['calibrated_workplace_model_percentage']:.3f}% |

The raw-building surface is highest because the reach captures a disproportionate
share of dense non-residential built volume. Uniform allocation spreads employment
into peripheral portions of partially intersected controls. The calibrated surface
uses uncapped building volume plus interpretable workplace POI categories and lands
between them. Every final surface is normalized within each census accounting
control, so published control totals are preserved exactly. That reconciliation does
not validate the within-control surface.

Six contiguous citywide spatial-block holdouts give MAE {all_metrics['mae_people']:,.0f},
WAPE {all_metrics['weighted_absolute_percentage_error']:.1f}%, MAPE
{all_metrics['mean_absolute_percentage_error']:.1f}%, and Spearman rank correlation
{all_metrics['spearman_rank_correlation']:.3f}. For top-quartile controls, MAE is
{top_metrics['mae_people']:,.0f}, WAPE {top_metrics['weighted_absolute_percentage_error']:.1f}%,
and rank correlation {top_metrics['spearman_rank_correlation']:.3f}. The audit records
{len(model['obvious_high_employment_underprediction'])} obvious top-control
underpredictions rather than concealing them.

The nonlinear Poisson boosting alternative gives top-control WAPE
{model['nonlinear_alternative']['top_employment_control_metrics']['weighted_absolute_percentage_error']:.1f}%
with rank correlation
{model['nonlinear_alternative']['top_employment_control_metrics']['spearman_rank_correlation']:.3f}
and {model['nonlinear_alternative']['obvious_high_employment_underprediction_count']}
severe misses. It does not improve the aggregate high-control diagnostics and fails
the same scientific acceptance gate, so it is retained as a diagnostic and is not
silently substituted as the 100 m allocation surface.

## 50-minute district contributions

| District | Exact district employment | Fine controlled | Residual | Inside reach | District captured | Reach contribution | Boundary |
|---|---:|---:|---:|---:|---:|---:|---|
{chr(10).join(district_rows)}

## Pudong accounting strata

| Stratum | Employment | Inside reach | Captured | Approximate support |
|---|---:|---:|---:|---|
{chr(10).join(pudong_rows)}

Functional-zone counts remain immutable, separate rows and are never merged into
host streets/towns. Their source polygons are not redistributed. The reported-area
morphology comparison changes the 50-minute city share by
{fifty['reported_area_interpretation_delta_percentage_points']:+.3f} percentage points,
but the conservative 0%/100% support envelope drives the broader boundary range.

## GDP diagnostic

The existing 50-minute GDP share is {gdp['existing_50min_gdp_share_percentage']:.3f}%.
GDP share / employment share is
**{gdp['gdp_share_divided_by_employment_share']:.3f}**, implying GDP per worker inside
the reach is **{gdp['gdp_share_divided_by_employment_share'] * 100:.1f}% of the Shanghai
average** under the two independent benchmark surfaces. This is a diagnostic, not a
causal productivity estimate. The GDP pipeline and result were not changed or rerun.

## Classification

**{methodology['benchmark_classification']}**

The accounting benchmark is complete, but the calibrated spatial surface is not.
High-employment controls remain poorly ranked and materially underpredicted under
both PPML and a nonlinear Poisson alternative. The open boundary vintage, Pudong
functional-zone scope, and unresolved residual locations add further uncertainty.
"""
    path.write_text(text, encoding="utf-8")


def export_outputs(
    *,
    repository_root: Path,
    fine_grid: gpd.GeoDataFrame,
    residual_grid: gpd.GeoDataFrame,
    reach_results: pd.DataFrame,
    district_contributions: pd.DataFrame,
    pudong_contributions: pd.DataFrame,
    rounding: pd.DataFrame,
    control_model_diagnostics: pd.DataFrame,
    model_diagnostics: dict[str, Any],
    topology_by_district: pd.DataFrame,
    topology_summary: dict[str, Any],
    boundary_review: pd.DataFrame,
    zone_attribution: pd.DataFrame,
    zone_sensitivity: pd.DataFrame,
    minhang_sliver: dict[str, Any],
    validation: dict[str, Any],
    methodology: dict[str, Any],
) -> dict[str, Path]:
    intermediate = repository_root / "data/employment/intermediate"
    outputs = repository_root / "data/employment/outputs"
    web = repository_root / "web/public/data"
    intermediate.mkdir(parents=True, exist_ok=True)
    outputs.mkdir(parents=True, exist_ok=True)
    web.mkdir(parents=True, exist_ok=True)
    paths = {
        "grid": intermediate / "employment-allocation-grid.parquet",
        "control_model": intermediate / "control-model-diagnostics.csv",
        "model_diagnostics": intermediate / "model-diagnostics.json",
        "topology": intermediate / "boundary-topology-diagnostics.csv",
        "topology_summary": intermediate / "boundary-topology-summary.json",
        "boundary_review": intermediate / "official-map-visual-review.csv",
        "zone_attribution": intermediate / "pudong-zone-attribution-audit.csv",
        "zone_sensitivity": intermediate / "pudong-zone-sensitivity.csv",
        "rounding": intermediate / "rounding-sensitivity.csv",
        "validation": intermediate / "employment-validation.json",
        "reach_csv": outputs / "employment-reach-summary.csv",
        "district_50": outputs / "district-50min-contributions.csv",
        "pudong_50": outputs / "pudong-50min-strata.csv",
        "minhang": outputs / "minhang-sliver-sensitivity.json",
        "decision_report": outputs / "decision-report.md",
        "reach_web": web / "reach-employment.json",
        "methodology_web": web / "employment-methodology.json",
    }
    exported_grid = public_audit_grid(fine_grid, residual_grid)
    exported_grid.to_parquet(paths["grid"], index=False, compression="zstd")
    control_model_diagnostics.to_csv(paths["control_model"], index=False)
    topology_by_district.to_csv(paths["topology"], index=False)
    boundary_review.to_csv(paths["boundary_review"], index=False)
    zone_attribution.to_csv(paths["zone_attribution"], index=False)
    zone_sensitivity.to_csv(paths["zone_sensitivity"], index=False)
    rounding.to_csv(paths["rounding"], index=False)
    reach_results.to_csv(paths["reach_csv"], index=False)
    district_contributions.to_csv(paths["district_50"], index=False)
    pudong_contributions.to_csv(paths["pudong_50"], index=False)
    write_json(paths["model_diagnostics"], model_diagnostics)
    write_json(paths["topology_summary"], topology_summary)
    write_json(paths["validation"], validation)
    write_json(paths["minhang"], minhang_sliver)
    write_decision_report(
        paths["decision_report"],
        reach_results=reach_results,
        district_contributions=district_contributions,
        pudong_contributions=pudong_contributions,
        methodology=methodology,
    )

    reach_payload = {
        "schema_version": 1,
        "employment_universe": methodology["employment_universe"],
        "denominator": methodology["denominator"],
        "reference_date": methodology["reference_date"],
        "geometry_is_approximate": True,
        "results": reach_results.to_dict(orient="records"),
        "district_contributions_50min": district_contributions.to_dict(
            orient="records"
        ),
        "pudong_strata_50min": pudong_contributions.to_dict(orient="records"),
        "uncertainty_is_not_a_confidence_interval": True,
    }
    write_json(paths["reach_web"], reach_payload)
    write_json(paths["methodology_web"], methodology)
    return paths
