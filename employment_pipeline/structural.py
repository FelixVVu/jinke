"""Allocation-free structural certainty for the selected 50-minute supports.

This module is deliberately a post-processing audit.  It reads the frozen census
controls, selected support geometries, existing three-model allocation grid, and
the exact production reach.  It does not fit or refit a workplace model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from .boundaries import load_ordinary_controls
from .config import (
    ANALYSIS_CRS,
    CITY_EMPLOYMENT,
    NOMINAL_FINE_CONTROL_EMPLOYMENT,
    NOMINAL_RESIDUAL_EMPLOYMENT,
)
from .export import write_json
from .manifests import sha256_file
from .reach import load_production_reaches, partial_cell_fractions


AREA_FRACTION_TOLERANCE = 1e-6
MODEL_SPREAD_COVERAGE_TARGET = 0.80

FULLY_INSIDE = "effectively_fully_inside"
FULLY_OUTSIDE = "effectively_fully_outside"
MATERIALLY_PARTIAL = "materially_partially_intersected"
CLASSIFICATION_ORDER = (FULLY_INSIDE, FULLY_OUTSIDE, MATERIALLY_PARTIAL)

MODEL_OUTPUT_COLUMNS = {
    "uniform_jobs_inside": "cell_employment_uniform",
    "building_jobs_inside": "cell_employment_building_volume",
    "ppml_jobs_inside": "cell_employment_calibrated_workplace",
}


def classify_support_fraction(
    area_fraction_inside: float,
    *,
    tolerance: float = AREA_FRACTION_TOLERANCE,
) -> str:
    """Classify a selected support using a disclosed relative-area tolerance."""

    if not 0.0 <= tolerance < 0.5:
        raise ValueError("The support-classification tolerance must be in [0, 0.5).")
    if not np.isfinite(area_fraction_inside):
        raise ValueError("Support area fraction is not finite.")
    if area_fraction_inside < -tolerance or area_fraction_inside > 1.0 + tolerance:
        raise ValueError(f"Support area fraction is outside [0, 1]: {area_fraction_inside}")
    fraction = float(np.clip(area_fraction_inside, 0.0, 1.0))
    if fraction <= tolerance:
        return FULLY_OUTSIDE
    if fraction >= 1.0 - tolerance:
        return FULLY_INSIDE
    return MATERIALLY_PARTIAL


def _read_current_50min_result(repository_root: Path) -> dict[str, float]:
    payload = json.loads(
        (repository_root / "web/public/data/reach-employment.json").read_text(
            encoding="utf-8"
        )
    )
    rows = [row for row in payload["results"] if int(row["limit_minutes"]) == 50]
    if len(rows) != 1:
        raise ValueError("Existing employment output must contain one 50-minute row.")
    row = rows[0]
    return {
        "current_numerator": float(row["central_estimated_employment"]),
        "current_percentage": float(row["percentage_of_shanghai_employment"]),
        "fine_uniform": float(row["fine_control_uniform_employment"]),
        "fine_building": float(row["fine_control_building_volume_employment"]),
        "fine_ppml": float(row["fine_control_calibrated_workplace_employment"]),
        "residual_central": float(row["residual_central_employment"]),
    }


def _ordinary_model_inside(
    public_grid: gpd.GeoDataFrame,
    reach_geometry: Any,
) -> pd.DataFrame:
    fine = public_grid.loc[
        public_grid["control_type"].isin(["street", "town"])
        & public_grid.geometry.notna()
    ].copy()
    if fine.crs is None or fine.crs.to_string() != ANALYSIS_CRS:
        raise ValueError("The public employment grid is not in EPSG:32651.")
    fractions = partial_cell_fractions(fine, reach_geometry)
    records = {"accounting_stratum_id": fine["accounting_control"].astype(str)}
    for output_column, grid_column in MODEL_OUTPUT_COLUMNS.items():
        records[output_column] = (
            fractions * fine[grid_column].to_numpy(dtype=float)
        )
    grouped = pd.DataFrame(records).groupby(
        "accounting_stratum_id", as_index=False
    ).sum()
    if len(grouped) != 113:
        raise ValueError(f"Expected 113 visible ordinary controls, found {len(grouped)}.")
    return grouped


def _selected_zone_rows(zone_sensitivity: pd.DataFrame) -> pd.DataFrame:
    zones = zone_sensitivity.loc[zone_sensitivity["limit_minutes"] == 50].copy()
    if len(zones) != 3 or zones["accounting_stratum_id"].duplicated().any():
        raise ValueError("Expected exactly three selected 50-minute zone-support rows.")
    zone_employment = zones["zone_employment"].to_numpy(dtype=float)
    if (zone_employment <= 0).any():
        raise ValueError("A Pudong zone has non-positive employment.")
    return pd.DataFrame(
        {
            "accounting_stratum_id": zones["accounting_stratum_id"].astype(str),
            "area_fraction_inside": np.clip(
                zones["selected_uniform_employment_inside"].to_numpy(dtype=float)
                / zone_employment,
                0.0,
                1.0,
            ),
            "uniform_jobs_inside": zones[
                "selected_uniform_employment_inside"
            ].to_numpy(dtype=float),
            "building_jobs_inside": zones[
                "selected_building_employment_inside"
            ].to_numpy(dtype=float),
            "ppml_jobs_inside": zones[
                "selected_calibrated_employment_inside"
            ].to_numpy(dtype=float),
        }
    )


def build_control_decomposition(
    *,
    repository_root: Path,
    tolerance: float = AREA_FRACTION_TOLERANCE,
) -> tuple[pd.DataFrame, dict[str, float], dict[str, str]]:
    """Build one structural-certainty record for each of the 116 strata."""

    repository_root = repository_root.resolve()
    crosswalk_path = (
        repository_root / "data/employment/manifests/control-crosswalk-2023.csv"
    )
    boundary_manifest_path = (
        repository_root / "data/employment/manifests/boundary-manifest.csv"
    )
    crosswalk = pd.read_csv(
        crosswalk_path,
        dtype={"accounting_stratum_id": "string"},
    )
    boundary = pd.read_csv(
        boundary_manifest_path,
        dtype={"accounting_stratum_id": "string"},
    )
    ordinary = load_ordinary_controls(
        repository_root
        / "data/employment/raw/boundaries/osm-priority-controls-2026-08-19.geojson",
        crosswalk_path,
    )
    reaches, reach_hash = load_production_reaches(
        repository_root / "web/public/data/reach-areas.geojson",
        ANALYSIS_CRS,
    )
    reach_50 = reaches.loc[reaches["limit"] == 50, "geometry"].iloc[0]
    ordinary_area = pd.DataFrame(
        {
            "accounting_stratum_id": ordinary["accounting_stratum_id"].astype(str),
            "area_fraction_inside": np.clip(
                ordinary.geometry.intersection(reach_50).area.to_numpy(dtype=float)
                / ordinary.geometry.area.to_numpy(dtype=float),
                0.0,
                1.0,
            ),
        }
    )
    public_grid = gpd.read_parquet(
        repository_root
        / "data/employment/intermediate/employment-allocation-grid.parquet"
    )
    ordinary_rows = ordinary_area.merge(
        _ordinary_model_inside(public_grid, reach_50),
        on="accounting_stratum_id",
        how="inner",
        validate="one_to_one",
    )
    zone_sensitivity_path = (
        repository_root / "data/employment/intermediate/pudong-zone-sensitivity.csv"
    )
    zone_rows = _selected_zone_rows(pd.read_csv(zone_sensitivity_path))
    spatial = pd.concat([ordinary_rows, zone_rows], ignore_index=True)
    if len(spatial) != 116 or spatial["accounting_stratum_id"].duplicated().any():
        raise ValueError("Structural audit did not produce 116 unique spatial rows.")

    control_columns = [
        "accounting_stratum_id",
        "district",
        "official_control_name_2023",
        "control_type",
        "employment_reconciled",
        "employment_rounding_lower",
        "employment_rounding_upper_exclusive",
        "rounding_increment_people",
        "employment_universe",
        "geometry_is_approximate",
    ]
    boundary_columns = [
        "accounting_stratum_id",
        "boundary_source",
        "source_vintage",
        "source_crs",
        "analysis_crs",
        "license_or_terms",
        "redistribution_status",
    ]
    controls = (
        crosswalk[control_columns]
        .merge(spatial, on="accounting_stratum_id", validate="one_to_one")
        .merge(
            boundary[boundary_columns],
            on="accounting_stratum_id",
            validate="one_to_one",
        )
    )
    controls = controls.rename(
        columns={
            "official_control_name_2023": "control_name",
            "employment_reconciled": "official_control_employment",
        }
    )
    expected_uniform = (
        controls["official_control_employment"].to_numpy(dtype=float)
        * controls["area_fraction_inside"].to_numpy(dtype=float)
    )
    if not np.allclose(
        controls["uniform_jobs_inside"].to_numpy(dtype=float),
        expected_uniform,
        atol=1e-5,
        rtol=1e-10,
    ):
        raise AssertionError(
            "Uniform allocation does not reproduce exact support area fractions."
        )
    controls["support_classification"] = controls["area_fraction_inside"].map(
        lambda value: classify_support_fraction(value, tolerance=tolerance)
    )
    model_columns = [
        "uniform_jobs_inside",
        "building_jobs_inside",
        "ppml_jobs_inside",
    ]
    controls["model_min_jobs_inside"] = controls[model_columns].min(axis=1)
    controls["model_max_jobs_inside"] = controls[model_columns].max(axis=1)
    controls["model_max_minus_min_jobs"] = (
        controls["model_max_jobs_inside"] - controls["model_min_jobs_inside"]
    )
    controls["model_difference_shanghai_percentage_points"] = (
        controls["model_max_minus_min_jobs"] / CITY_EMPLOYMENT * 100.0
    )
    controls["official_control_share_of_shanghai_percentage"] = (
        controls["official_control_employment"] / CITY_EMPLOYMENT * 100.0
    )
    current = _read_current_50min_result(repository_root)
    controls["ppml_share_of_current_50min_numerator_percentage"] = (
        controls["ppml_jobs_inside"] / current["current_numerator"] * 100.0
    )
    controls["partial_uncertainty_rank"] = pd.Series(pd.NA, index=controls.index, dtype="Int64")
    controls["cumulative_partial_model_spread_share"] = np.nan
    controls["in_smallest_set_covering_80pct_model_spread"] = False
    partial = controls.loc[
        controls["support_classification"] == MATERIALLY_PARTIAL
    ].sort_values(
        ["model_max_minus_min_jobs", "official_control_employment", "accounting_stratum_id"],
        ascending=[False, False, True],
    )
    total_local_spread = float(partial["model_max_minus_min_jobs"].sum())
    if total_local_spread > 0:
        cumulative = partial["model_max_minus_min_jobs"].cumsum() / total_local_spread
        ranks = pd.Series(np.arange(1, len(partial) + 1), index=partial.index)
        cutoff = int(np.searchsorted(cumulative.to_numpy(), MODEL_SPREAD_COVERAGE_TARGET) + 1)
        controls.loc[partial.index, "partial_uncertainty_rank"] = ranks.astype("Int64")
        controls.loc[
            partial.index, "cumulative_partial_model_spread_share"
        ] = cumulative
        controls.loc[
            partial.index[:cutoff], "in_smallest_set_covering_80pct_model_spread"
        ] = True

    controls = controls.sort_values(
        ["support_classification", "partial_uncertainty_rank", "district", "accounting_stratum_id"],
        na_position="last",
    ).reset_index(drop=True)
    source_hashes = {
        "reach_sha256": reach_hash,
        "current_reach_employment_sha256": sha256_file(
            repository_root / "web/public/data/reach-employment.json"
        ),
        "control_crosswalk_sha256": sha256_file(crosswalk_path),
        "boundary_manifest_sha256": sha256_file(boundary_manifest_path),
        "ordinary_support_sha256": sha256_file(
            repository_root
            / "data/employment/raw/boundaries/osm-priority-controls-2026-08-19.geojson"
        ),
        "public_grid_sha256": sha256_file(
            repository_root
            / "data/employment/intermediate/employment-allocation-grid.parquet"
        ),
        "zone_sensitivity_sha256": sha256_file(zone_sensitivity_path),
    }
    return controls, current, source_hashes


def category_decomposition(
    controls: pd.DataFrame,
    *,
    current_numerator: float,
) -> pd.DataFrame:
    grouped = controls.groupby("support_classification", as_index=True).agg(
        control_count=("accounting_stratum_id", "size"),
        official_control_employment=("official_control_employment", "sum"),
        uniform_jobs_inside=("uniform_jobs_inside", "sum"),
        building_jobs_inside=("building_jobs_inside", "sum"),
        ppml_jobs_inside=("ppml_jobs_inside", "sum"),
        summed_local_model_spread_jobs=("model_max_minus_min_jobs", "sum"),
    )
    grouped = grouped.reindex(CLASSIFICATION_ORDER, fill_value=0).reset_index()
    grouped["share_of_shanghai_denominator_percentage"] = (
        grouped["official_control_employment"] / CITY_EMPLOYMENT * 100.0
    )
    grouped["ppml_share_of_current_50min_numerator_percentage"] = (
        grouped["ppml_jobs_inside"] / current_numerator * 100.0
    )
    grouped["aggregate_model_spread_jobs"] = grouped[
        ["uniform_jobs_inside", "building_jobs_inside", "ppml_jobs_inside"]
    ].max(axis=1) - grouped[
        ["uniform_jobs_inside", "building_jobs_inside", "ppml_jobs_inside"]
    ].min(axis=1)
    grouped["aggregate_model_spread_shanghai_percentage_points"] = (
        grouped["aggregate_model_spread_jobs"] / CITY_EMPLOYMENT * 100.0
    )
    return grouped


def district_decomposition(
    controls: pd.DataFrame,
    *,
    repository_root: Path,
    current_numerator: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    districts = pd.read_csv(
        repository_root / "data/employment/manifests/district-employment-2023.csv"
    )
    priority = districts.loc[
        districts["priority_district"].map(
            lambda value: value is True or str(value).strip().lower() == "true"
        ),
        ["district", "district_en", "employment"],
    ].copy()
    district_order = priority["district"].tolist()
    long = controls.groupby(
        ["district", "support_classification"], as_index=True
    ).agg(
        control_count=("accounting_stratum_id", "size"),
        official_control_employment=("official_control_employment", "sum"),
        uniform_jobs_inside=("uniform_jobs_inside", "sum"),
        building_jobs_inside=("building_jobs_inside", "sum"),
        ppml_jobs_inside=("ppml_jobs_inside", "sum"),
        summed_local_model_spread_jobs=("model_max_minus_min_jobs", "sum"),
    )
    index = pd.MultiIndex.from_product(
        [district_order, CLASSIFICATION_ORDER],
        names=["district", "support_classification"],
    )
    long = long.reindex(index, fill_value=0).reset_index()
    long = long.merge(priority, on="district", validate="many_to_one")
    long["share_of_shanghai_denominator_percentage"] = (
        long["official_control_employment"] / CITY_EMPLOYMENT * 100.0
    )
    long["share_of_district_employment_percentage"] = np.divide(
        long["official_control_employment"],
        long["employment"],
        out=np.zeros(len(long), dtype=float),
        where=long["employment"].to_numpy(dtype=float) > 0,
    ) * 100.0
    long["ppml_share_of_current_50min_numerator_percentage"] = (
        long["ppml_jobs_inside"] / current_numerator * 100.0
    )
    long = long.rename(columns={"employment": "exact_district_employment"})

    employment_pivot = long.pivot(
        index=["district", "district_en", "exact_district_employment"],
        columns="support_classification",
        values="official_control_employment",
    ).reset_index()
    count_pivot = long.pivot(
        index=["district", "district_en", "exact_district_employment"],
        columns="support_classification",
        values="control_count",
    ).reset_index()
    count_pivot = count_pivot.rename(
        columns={category: f"{category}_control_count" for category in CLASSIFICATION_ORDER}
    ).drop(columns=["district_en", "exact_district_employment"])
    bounds = employment_pivot.rename(
        columns={category: f"{category}_employment" for category in CLASSIFICATION_ORDER}
    ).merge(count_pivot, on="district", validate="one_to_one")
    fine_totals = controls.groupby("district", as_index=False).agg(
        fine_controlled_employment=("official_control_employment", "sum"),
        uniform_jobs_inside_50min=("uniform_jobs_inside", "sum"),
        building_jobs_inside_50min=("building_jobs_inside", "sum"),
        ppml_jobs_inside_50min=("ppml_jobs_inside", "sum"),
    )
    bounds = bounds.merge(fine_totals, on="district", validate="one_to_one")
    residuals = pd.read_csv(
        repository_root / "data/employment/manifests/residual-strata.csv"
    )[["district", "employment_nominal"]].rename(
        columns={"employment_nominal": "residual_employment_separate"}
    )
    current_district = pd.read_csv(
        repository_root / "data/employment/outputs/district-50min-contributions.csv"
    )[["district", "residual_central_inside_50min", "employment_inside_50min"]]
    bounds = (
        bounds.merge(residuals, on="district", validate="one_to_one")
        .merge(current_district, on="district", validate="one_to_one")
    )
    bounds["structural_lower_bound_fine_employment"] = bounds[
        f"{FULLY_INSIDE}_employment"
    ]
    bounds["structural_upper_bound_fine_employment"] = (
        bounds[f"{FULLY_INSIDE}_employment"]
        + bounds[f"{MATERIALLY_PARTIAL}_employment"]
    )
    bounds["structural_lower_bound_shanghai_percentage"] = (
        bounds["structural_lower_bound_fine_employment"] / CITY_EMPLOYMENT * 100.0
    )
    bounds["structural_upper_bound_shanghai_percentage"] = (
        bounds["structural_upper_bound_fine_employment"] / CITY_EMPLOYMENT * 100.0
    )
    district_rank = {name: rank for rank, name in enumerate(district_order)}
    long = long.sort_values(
        ["district", "support_classification"],
        key=lambda series: (
            series.map(district_rank)
            if series.name == "district"
            else series.map(
                {category: rank for rank, category in enumerate(CLASSIFICATION_ORDER)}
            )
        ),
    ).reset_index(drop=True)
    bounds = bounds.sort_values(
        "district", key=lambda series: series.map(district_rank)
    ).reset_index(drop=True)
    return long, bounds


def structural_summary(
    *,
    controls: pd.DataFrame,
    categories: pd.DataFrame,
    current: dict[str, float],
    source_hashes: dict[str, str],
    tolerance: float,
) -> dict[str, Any]:
    category = categories.set_index("support_classification")
    inside = float(category.loc[FULLY_INSIDE, "official_control_employment"])
    outside = float(category.loc[FULLY_OUTSIDE, "official_control_employment"])
    partial = float(category.loc[MATERIALLY_PARTIAL, "official_control_employment"])
    lower = inside
    upper = inside + partial
    fine_ppml = float(controls["ppml_jobs_inside"].sum())
    residual_central = current["current_numerator"] - fine_ppml
    if not np.isclose(fine_ppml, current["fine_ppml"], atol=1e-5):
        raise AssertionError("Structural PPML contributions changed the existing fine result.")
    if not np.isclose(residual_central, current["residual_central"], atol=1e-5):
        raise AssertionError("Structural decomposition changed the residual central result.")
    partial_rows = controls.loc[
        controls["support_classification"] == MATERIALLY_PARTIAL
    ].sort_values("partial_uncertainty_rank")
    selected_80 = partial_rows.loc[
        partial_rows["in_smallest_set_covering_80pct_model_spread"]
    ]
    total_local_spread = float(partial_rows["model_max_minus_min_jobs"].sum())
    aggregate_partial_model_spread = float(
        partial_rows[
            ["uniform_jobs_inside", "building_jobs_inside", "ppml_jobs_inside"]
        ].sum().max()
        - partial_rows[
            ["uniform_jobs_inside", "building_jobs_inside", "ppml_jobs_inside"]
        ].sum().min()
    )
    zones = controls.loc[controls["control_type"] == "functional_zone"]
    selected_zone_upper = float(
        zones.loc[
            zones["support_classification"].isin([FULLY_INSIDE, MATERIALLY_PARTIAL]),
            "official_control_employment",
        ].sum()
    )
    all_zone_employment = float(zones["official_control_employment"].sum())
    functional_zone_boundary_extra_upper = all_zone_employment - selected_zone_upper
    upper_with_residual = upper + NOMINAL_RESIDUAL_EMPLOYMENT
    extreme_ceiling = upper_with_residual + functional_zone_boundary_extra_upper
    required_partial_for_40 = (
        0.40 * CITY_EMPLOYMENT - inside
    ) / partial
    return {
        "schema_version": 1,
        "analysis": "50-minute structural certainty decomposition",
        "does_not_refit_calibrated_model": True,
        "current_50min_result_unchanged": {
            "employment": current["current_numerator"],
            "percentage": current["current_percentage"],
        },
        "denominator": CITY_EMPLOYMENT,
        "fine_control_employment": NOMINAL_FINE_CONTROL_EMPLOYMENT,
        "residual_employment_kept_separate": NOMINAL_RESIDUAL_EMPLOYMENT,
        "classification_tolerance": {
            "relative_support_area_fraction": tolerance,
            "percentage_of_support_area": tolerance * 100.0,
            "effectively_fully_outside_rule": f"fraction <= {tolerance}",
            "effectively_fully_inside_rule": f"fraction >= {1.0 - tolerance}",
            "partial_rule": f"{tolerance} < fraction < {1.0 - tolerance}",
            "reason": (
                "strict numerical/geometric tolerance; it is not a workplace-density "
                "assumption"
            ),
        },
        "source_hashes": source_hashes,
        "classification": categories.to_dict(orient="records"),
        "allocation_free_fine_control_bound": {
            "lower_employment": lower,
            "upper_employment": upper,
            "width_employment": upper - lower,
            "lower_shanghai_percentage": lower / CITY_EMPLOYMENT * 100.0,
            "upper_shanghai_percentage": upper / CITY_EMPLOYMENT * 100.0,
            "width_percentage_points": (upper - lower) / CITY_EMPLOYMENT * 100.0,
            "residual_workers_included": 0,
            "pudong_functional_zone_boundary_perturbation_included": False,
        },
        "current_numerator_components": {
            "fully_inside_official_controls": inside,
            "partial_controls_ppml_jobs_inside": float(
                category.loc[MATERIALLY_PARTIAL, "ppml_jobs_inside"]
            ),
            "fully_outside_controls_ppml_jobs_inside": float(
                category.loc[FULLY_OUTSIDE, "ppml_jobs_inside"]
            ),
            "central_residual_jobs_inside": residual_central,
        },
        "answers": {
            "A_official_census_determined_percentage_of_current_numerator": (
                inside / current["current_numerator"] * 100.0
            ),
            "A_official_census_determined_percentage_of_fine_control_numerator": (
                inside / fine_ppml * 100.0
            ),
            "B_partial_spatial_allocation_percentage_of_current_numerator": (
                float(category.loc[MATERIALLY_PARTIAL, "ppml_jobs_inside"])
                / current["current_numerator"]
                * 100.0
            ),
            "B_partial_spatial_allocation_percentage_of_fine_control_numerator": (
                float(category.loc[MATERIALLY_PARTIAL, "ppml_jobs_inside"])
                / fine_ppml
                * 100.0
            ),
            "central_residual_percentage_of_current_numerator": (
                residual_central / current["current_numerator"] * 100.0
            ),
            "C_selected_support_fine_bound_can_exceed_40_percent": bool(
                upper / CITY_EMPLOYMENT > 0.40
            ),
            "C_required_share_of_partial_employment_inside_for_40_percent": (
                required_partial_for_40
            ),
            "C_selected_support_fine_upper_percentage": (
                upper / CITY_EMPLOYMENT * 100.0
            ),
            "C_upper_with_all_residual_inside_percentage": (
                upper_with_residual / CITY_EMPLOYMENT * 100.0
            ),
            "C_extreme_ceiling_with_all_residual_and_pudong_zone_boundary_upper_percentage": (
                extreme_ceiling / CITY_EMPLOYMENT * 100.0
            ),
            "C_can_exceed_50_percent_under_explicit_extremes": bool(
                extreme_ceiling / CITY_EMPLOYMENT > 0.50
            ),
            "C_interpretation": (
                "The accounting/geometric bound barely permits more than 40%, but only "
                "near its adversarial upper edge; the three retained allocation models "
                "do not make more than 40% plausible. Even all residual workers and the "
                "separate functional-zone boundary upper cannot reach 50%."
            ),
        },
        "model_spread_concentration": {
            "sum_of_partial_control_max_minus_min_jobs": total_local_spread,
            "sum_of_partial_control_spreads_shanghai_percentage_points": (
                total_local_spread / CITY_EMPLOYMENT * 100.0
            ),
            "aggregate_partial_uniform_building_ppml_spread_jobs": (
                aggregate_partial_model_spread
            ),
            "aggregate_partial_spread_shanghai_percentage_points": (
                aggregate_partial_model_spread / CITY_EMPLOYMENT * 100.0
            ),
            "coverage_target": MODEL_SPREAD_COVERAGE_TARGET,
            "smallest_control_set_count": int(len(selected_80)),
            "smallest_control_set_coverage": (
                float(selected_80["model_max_minus_min_jobs"].sum())
                / total_local_spread
                if total_local_spread > 0
                else 0.0
            ),
            "smallest_control_set_ids": selected_80[
                "accounting_stratum_id"
            ].tolist(),
        },
        "separate_uncertainty_ledgers": {
            "residual_location_workers": NOMINAL_RESIDUAL_EMPLOYMENT,
            "pudong_zone_boundary_additional_upper_workers": (
                functional_zone_boundary_extra_upper
            ),
            "selected_support_structural_upper_plus_all_residual_employment": (
                upper_with_residual
            ),
            "extreme_ceiling_employment": extreme_ceiling,
            "uncertainty_sources_are_not_added_to_the_structural_bound": True,
        },
    }


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "|" + "|".join("---" for _ in headers) + "|",
            *("| " + " | ".join(row) + " |" for row in rows),
        ]
    )


def write_structural_report(
    path: Path,
    *,
    controls: pd.DataFrame,
    categories: pd.DataFrame,
    district_bounds: pd.DataFrame,
    summary: dict[str, Any],
) -> None:
    answers = summary["answers"]
    bound = summary["allocation_free_fine_control_bound"]
    current = summary["current_50min_result_unchanged"]
    residual = summary["separate_uncertainty_ledgers"]
    labels = {
        FULLY_INSIDE: "Effectively fully inside",
        FULLY_OUTSIDE: "Effectively fully outside",
        MATERIALLY_PARTIAL: "Materially partial",
    }
    category_rows: list[list[str]] = []
    for row in categories.itertuples(index=False):
        category_rows.append(
            [
                labels[row.support_classification],
                f"{row.control_count:,}",
                f"{row.official_control_employment:,.0f}",
                f"{row.share_of_shanghai_denominator_percentage:.3f}%",
                f"{row.ppml_jobs_inside:,.0f}",
                f"{row.ppml_share_of_current_50min_numerator_percentage:.3f}%",
            ]
        )
    district_rows: list[list[str]] = []
    for row in district_bounds.itertuples(index=False):
        district_rows.append(
            [
                row.district_en,
                (
                    f"{getattr(row, FULLY_INSIDE + '_control_count')}/"
                    f"{getattr(row, FULLY_OUTSIDE + '_control_count')}/"
                    f"{getattr(row, MATERIALLY_PARTIAL + '_control_count')}"
                ),
                f"{getattr(row, FULLY_INSIDE + '_employment'):,.0f}",
                f"{getattr(row, FULLY_OUTSIDE + '_employment'):,.0f}",
                f"{getattr(row, MATERIALLY_PARTIAL + '_employment'):,.0f}",
                f"{row.ppml_jobs_inside_50min:,.0f}",
                (
                    f"{row.structural_lower_bound_shanghai_percentage:.3f}%–"
                    f"{row.structural_upper_bound_shanghai_percentage:.3f}%"
                ),
                f"{row.residual_employment_separate:,.0f}",
            ]
        )
    partial_ranked = controls.loc[
        controls["support_classification"] == MATERIALLY_PARTIAL
    ].sort_values("partial_uncertainty_rank")
    selected_80 = partial_ranked.loc[
        partial_ranked["in_smallest_set_covering_80pct_model_spread"]
    ]
    concentration_rows: list[list[str]] = []
    for row in selected_80.itertuples(index=False):
        concentration_rows.append(
            [
                f"{row.partial_uncertainty_rank}",
                row.district,
                row.control_name,
                f"{row.model_max_minus_min_jobs:,.0f}",
                f"{row.model_difference_shanghai_percentage_points:.3f}",
                f"{row.cumulative_partial_model_spread_share * 100:.1f}%",
            ]
        )
    structural_priorities = partial_ranked.sort_values(
        ["official_control_employment", "model_max_minus_min_jobs"],
        ascending=[False, False],
    ).head(10)
    priority_rows: list[list[str]] = []
    for rank, row in enumerate(structural_priorities.itertuples(index=False), start=1):
        priority_rows.append(
            [
                str(rank),
                row.district,
                row.control_name,
                f"{row.official_control_employment:,.0f}",
                f"{row.area_fraction_inside * 100:.3f}%",
                f"{row.model_max_minus_min_jobs:,.0f}",
            ]
        )
    top_model_rows: list[list[str]] = []
    for row in partial_ranked.head(10).itertuples(index=False):
        top_model_rows.append(
            [
                f"{row.partial_uncertainty_rank}",
                row.district,
                row.control_name,
                f"{row.official_control_employment:,.0f}",
                f"{row.area_fraction_inside * 100:.3f}%",
                f"{row.uniform_jobs_inside:,.0f}",
                f"{row.building_jobs_inside:,.0f}",
                f"{row.ppml_jobs_inside:,.0f}",
                f"{row.model_max_minus_min_jobs:,.0f}",
            ]
        )

    text = f"""# Jinke employment benchmark — 50-minute structural-certainty report

## Scope and unchanged result

This audit decomposes the existing benchmark at the level of all 116 selected
fine accounting supports. It uses the exact pinned production 50-minute polygon
and does **not** fit, refit, or judge another global PPML specification.

The existing result remains unchanged:

**Estimated workplace employment within 50-minute reach: {current['employment'] / 1_000_000:.2f} million**

**{current['percentage']:.1f}% of Shanghai's 2023 secondary- and tertiary-sector legal-entity employment**

The denominator remains 13,099,795. Individual-business employment is excluded.

## Classification tolerance

The relative support-area tolerance is **{summary['classification_tolerance']['relative_support_area_fraction']:.0e}**,
or **{summary['classification_tolerance']['percentage_of_support_area']:.4f}%** of a
control's selected support. A control is effectively outside at or below that
fraction, effectively inside at or above
{(1-summary['classification_tolerance']['relative_support_area_fraction']) * 100:.4f}%,
and materially partial otherwise. This is a strict numerical/geometric tolerance,
not an employment-density assumption.

{_markdown_table(
    ['Support class', 'Controls', 'Official employment', 'Shanghai denominator', 'PPML jobs inside', 'Current numerator'],
    category_rows,
)}

The three rows account for all 7,114,511 fine-controlled workers. Their PPML jobs
inside sum to {current['employment'] - summary['current_numerator_components']['central_residual_jobs_inside']:,.0f};
the remaining {summary['current_numerator_components']['central_residual_jobs_inside']:,.0f}
in the current numerator is the separate central residual allocation.

## Allocation-free geometric bound

- Lower structural bound: **{bound['lower_employment']:,.0f} ({bound['lower_shanghai_percentage']:.3f}% of Shanghai)**.
- Upper structural bound: **{bound['upper_employment']:,.0f} ({bound['upper_shanghai_percentage']:.3f}% of Shanghai)**.
- Width: **{bound['width_employment']:,.0f} workers / {bound['width_percentage_points']:.3f} percentage points**.

This is a bound on fine-controlled employment only. It includes every fully-inside
control total in the lower bound and allows zero-to-all employment from every
partial control. It deliberately excludes the 526,062 residual workers and the
Pudong functional-zone boundary perturbation.

Kept separate:

- Adding the all-residual upper ledger to the selected-support upper gives
  **{residual['selected_support_structural_upper_plus_all_residual_employment']:,.0f}
  ({answers['C_upper_with_all_residual_inside_percentage']:.3f}%)**.
- Moving the separately uncertain FTZ Bonded Area support to its conservative
  upper adds {residual['pudong_zone_boundary_additional_upper_workers']:,.0f}, for
  an explicit extreme ceiling of **{residual['extreme_ceiling_employment']:,.0f}
  ({answers['C_extreme_ceiling_with_all_residual_and_pudong_zone_boundary_upper_percentage']:.3f}%)**.

These ledgers are shown together only to answer the ceiling question; they are not
collapsed into the structural bound or a confidence interval.

## Answers A–C

**A. {answers['A_official_census_determined_percentage_of_current_numerator']:.1f}% of the current 50-minute numerator is fixed directly by official fine-control totals without a within-control allocation model.**

That is {summary['current_numerator_components']['fully_inside_official_controls']:,.0f}
workers in fully-inside controls. It is
{answers['A_official_census_determined_percentage_of_fine_control_numerator']:.1f}%
of the fine-controlled numerator alone.

**B. {answers['B_partial_spatial_allocation_percentage_of_current_numerator']:.1f}% of the current numerator genuinely depends on allocation within partial controls.**

That is {summary['current_numerator_components']['partial_controls_ppml_jobs_inside']:,.0f}
PPML-allocated workers, or
{answers['B_partial_spatial_allocation_percentage_of_fine_control_numerator']:.1f}%
of the fine-controlled numerator. A further
{answers['central_residual_percentage_of_current_numerator']:.1f}% of the current
numerator is the separately treated central residual and is neither A nor B.

**C. More than 40% is mathematically permitted by the accounting/geometric bound, but it is not a plausible central result; more than 50% is ruled out by the explicit extrema.**

The selected-support fine-control ceiling is only
{answers['C_selected_support_fine_upper_percentage']:.3f}%. Reaching 40% with
residuals held separate would require
{answers['C_required_share_of_partial_employment_inside_for_40_percent'] * 100:.1f}%
of all employment in the 69 partial controls to sit inside their reach-facing
pieces—essentially the adversarial upper edge. The retained uniform/building/PPML
results are far lower. Even putting all 526,062 residual workers inside and applying
the separate conservative Pudong-zone boundary upper reaches only
{answers['C_extreme_ceiling_with_all_residual_and_pudong_zone_boundary_upper_percentage']:.3f}%,
not 50%.

## District decomposition

Counts are shown as inside/outside/partial. Bounds remain fine-control-only;
district residuals stay in the final column.

{_markdown_table(
    ['District', 'I/O/P controls', 'Inside-control emp.', 'Outside-control emp.', 'Partial-control emp.', 'PPML fine jobs inside', 'Structural Shanghai-share bound', 'Residual separate'],
    district_rows,
)}

## Partial-control model spread

For each partial control the detailed CSV reports official employment, exact support
area fraction, uniform/building/PPML jobs inside, the maximum-minus-minimum difference,
and its Shanghai percentage-point contribution. The aggregate partial totals span
{summary['model_spread_concentration']['aggregate_partial_uniform_building_ppml_spread_jobs']:,.0f}
jobs ({summary['model_spread_concentration']['aggregate_partial_spread_shanghai_percentage_points']:.3f}
percentage points). Summing control-level absolute spreads gives
{summary['model_spread_concentration']['sum_of_partial_control_max_minus_min_jobs']:,.0f}
jobs because model differences offset across controls.

Top 10 controls by local model spread:

{_markdown_table(
    ['Rank', 'District', 'Control', 'Official emp.', 'Area inside', 'Uniform', 'Building', 'PPML', 'Max−min'],
    top_model_rows,
)}

The smallest ranked set reaching at least 80% contains
**{summary['model_spread_concentration']['smallest_control_set_count']} controls** and
accounts for **{summary['model_spread_concentration']['smallest_control_set_coverage'] * 100:.2f}%**
of summed local model spread:

{_markdown_table(
    ['Rank', 'District', 'Control', 'Max−min jobs', 'Shanghai pp', 'Cumulative'],
    concentration_rows,
)}

## Top 10 fine-scale data priorities

The structural bound is still very wide. For allocation-free uncertainty, the
maximum reduction from resolving one partial stratum is its full official control
employment. These are therefore the ten highest-value controls for improved
workplace information (model spread is shown as a secondary diagnostic):

{_markdown_table(
    ['Priority', 'District', 'Control', 'Official emp.', 'Area inside', 'Model max−min'],
    priority_rows,
)}

## Review status

This report adds a structural audit only. The current 3.69 million / 28.2% result,
its failed calibrated-model gate, the GDP model and files, production reach polygons,
and Site/UI remain unchanged. Nothing is merged or deployed.
"""
    path.write_text(text, encoding="utf-8")


def run_structural_certainty(
    repository_root: Path,
    *,
    tolerance: float = AREA_FRACTION_TOLERANCE,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    controls, current, source_hashes = build_control_decomposition(
        repository_root=repository_root,
        tolerance=tolerance,
    )
    categories = category_decomposition(
        controls,
        current_numerator=current["current_numerator"],
    )
    district_long, district_bounds = district_decomposition(
        controls,
        repository_root=repository_root,
        current_numerator=current["current_numerator"],
    )
    summary = structural_summary(
        controls=controls,
        categories=categories,
        current=current,
        source_hashes=source_hashes,
        tolerance=tolerance,
    )
    outputs = repository_root / "data/employment/outputs"
    paths = {
        "controls": outputs / "structural-certainty-controls-50min.csv",
        "districts": outputs / "structural-certainty-districts-50min.csv",
        "district_bounds": outputs
        / "structural-certainty-district-bounds-50min.csv",
        "summary": outputs / "structural-certainty-summary-50min.json",
        "report": outputs / "structural-certainty-report.md",
    }
    controls.to_csv(paths["controls"], index=False)
    district_long.to_csv(paths["districts"], index=False)
    district_bounds.to_csv(paths["district_bounds"], index=False)
    write_json(paths["summary"], summary)
    write_structural_report(
        paths["report"],
        controls=controls,
        categories=categories,
        district_bounds=district_bounds,
        summary=summary,
    )
    return {
        "summary": summary,
        "paths": {key: str(value) for key, value in paths.items()},
    }
