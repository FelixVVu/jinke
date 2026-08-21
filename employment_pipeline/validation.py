"""Fail-closed validation for the independent employment benchmark."""

from __future__ import annotations

from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from .config import (
    ANALYSIS_CRS,
    CITY_EMPLOYMENT,
    EMPLOYMENT_UNIVERSE,
    LIMITS,
    NOMINAL_FINE_CONTROL_EMPLOYMENT,
    NOMINAL_RESIDUAL_EMPLOYMENT,
    OSM_LICENSE,
)
from .reach import FINE_MODEL_COLUMNS, REACH_SOURCE_SHA256


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_benchmark(
    *,
    district_totals: pd.DataFrame,
    controls: pd.DataFrame,
    residuals: pd.DataFrame,
    control_geometries: gpd.GeoDataFrame,
    fine_grid: gpd.GeoDataFrame,
    residual_grid: gpd.GeoDataFrame,
    reaches: pd.DataFrame,
    reach_source_sha256: str,
    model_diagnostics: dict[str, Any],
    boundary_review: pd.DataFrame,
    tolerance: float = 1e-5,
) -> dict[str, Any]:
    checks: dict[str, Any] = {}

    _assert(len(district_totals) == 16, "Exactly 16 district totals are required.")
    _assert(district_totals["district"].is_unique, "District totals are duplicated.")
    official_sum = int(district_totals["employment"].sum())
    _assert(
        official_sum == CITY_EMPLOYMENT,
        f"District totals sum to {official_sum}, not {CITY_EMPLOYMENT}.",
    )
    _assert(
        not district_totals["individual_business_included"].astype(bool).any(),
        "Individual-business workers entered the district denominator.",
    )
    checks["district_totals"] = {
        "district_count": 16,
        "sum": official_sum,
        "expected": CITY_EMPLOYMENT,
        "individual_business_included": False,
    }

    _assert(len(controls) == 116, "Exactly 116 fine accounting strata are required.")
    _assert(
        controls["accounting_stratum_id"].is_unique,
        "An accounting stratum is counted more than once.",
    )
    fine_sum = int(controls["employment_reconciled"].sum())
    _assert(
        fine_sum == NOMINAL_FINE_CONTROL_EMPLOYMENT,
        f"Fine controls sum to {fine_sum}, not {NOMINAL_FINE_CONTROL_EMPLOYMENT}.",
    )
    residual_sum = int(residuals["employment_nominal"].sum())
    _assert(
        residual_sum == NOMINAL_RESIDUAL_EMPLOYMENT,
        f"Residuals sum to {residual_sum}, not {NOMINAL_RESIDUAL_EMPLOYMENT}.",
    )
    _assert(
        not controls["individual_business_included"].astype(bool).any(),
        "Individual-business workers entered a fine control.",
    )
    lower = controls["employment_rounding_lower"].to_numpy(dtype=float)
    upper = controls["employment_rounding_upper_exclusive"].to_numpy(dtype=float)
    central = controls["employment_reconciled"].to_numpy(dtype=float)
    exact = controls["rounding_increment_people"].to_numpy(dtype=float) == 1
    _assert(
        bool(np.all(central >= lower - tolerance)),
        "A reconciled control is below its published rounding interval.",
    )
    _assert(
        bool(np.all(exact | (central < upper + tolerance))),
        "A reconciled control is above its published rounding interval.",
    )
    pudong = controls.loc[controls["district"] == "浦东新区"]
    expected_subtotals = {
        "Pudong streets": 695_000,
        "Pudong towns": 1_099_000,
        "Pudong functional zones": 821_000,
    }
    actual_subtotals = (
        pudong.groupby("subtotal_group")["employment_reconciled"].sum().to_dict()
    )
    _assert(
        all(actual_subtotals.get(key) == value for key, value in expected_subtotals.items()),
        f"Pudong reconciled subtotals failed: {actual_subtotals}",
    )
    checks["accounting_controls"] = {
        "fine_control_count": 116,
        "fine_employment": fine_sum,
        "residual_stratum_count": int(len(residuals)),
        "residual_employment": residual_sum,
        "pudong_subtotals": actual_subtotals,
        "no_duplicate_accounting_strata": True,
        "rounding_intervals_satisfied": True,
    }

    _assert(len(control_geometries) == 116, "All 116 supports must be available locally.")
    _assert(control_geometries.crs.to_string() == ANALYSIS_CRS, "Wrong analysis CRS.")
    _assert(control_geometries.geometry.is_valid.all(), "A support geometry is invalid.")
    _assert(not control_geometries.geometry.is_empty.any(), "A support geometry is empty.")
    _assert(
        control_geometries["geometry_is_approximate"].astype(bool).all(),
        "Every support must retain the approximate-boundary disclosure.",
    )
    checks["geometry"] = {
        "analysis_crs": ANALYSIS_CRS,
        "support_count": int(len(control_geometries)),
        "all_approximate": True,
        "all_valid_nonempty": True,
    }

    _assert(fine_grid["cell_id"].is_unique, "Fine grid cell IDs are not unique.")
    _assert((fine_grid["cell_area_m2"] > 0).all(), "Fine grid has zero-area cells.")
    _assert(fine_grid.geometry.is_valid.all(), "Fine grid contains invalid cells.")
    model_errors: dict[str, float] = {}
    targets = controls.set_index("accounting_stratum_id")["employment_reconciled"].astype(
        float
    )
    for model, column in FINE_MODEL_COLUMNS.items():
        values = fine_grid[column].to_numpy(dtype=float)
        _assert(np.isfinite(values).all(), f"{model} allocation has non-finite values.")
        _assert((values >= -tolerance).all(), f"{model} allocation is negative.")
        actual = fine_grid.groupby("accounting_control")[column].sum().reindex(targets.index)
        error = actual - targets
        max_error = float(error.abs().max())
        _assert(max_error <= tolerance, f"{model} control allocation error is {max_error}.")
        model_errors[model] = max_error
    checks["control_allocation"] = {
        "grid_rows_local_full_support": int(len(fine_grid)),
        "max_abs_error_people": model_errors,
        "no_negative_employment": True,
    }

    if not residual_grid.empty:
        values = residual_grid["cell_employment_residual_central"].to_numpy(dtype=float)
        _assert(np.isfinite(values).all(), "Residual central allocation is non-finite.")
        _assert((values >= -tolerance).all(), "Residual central allocation is negative.")
        expected = residuals.loc[
            residuals["central_is_spatially_allocated"].map(
                lambda value: value is True or str(value).lower() == "true"
            )
        ].set_index("residual_id")["employment_nominal"]
        actual = residual_grid.groupby("accounting_control")[
            "cell_employment_residual_central"
        ].sum().reindex(expected.index)
        max_residual_error = float((actual - expected).abs().max())
        _assert(
            max_residual_error <= tolerance,
            f"Finance residual allocation error is {max_residual_error}.",
        )
    else:
        max_residual_error = 0.0
    checks["residual_allocation"] = {
        "centrally_located_residual_people": float(
            residual_grid.get("cell_employment_residual_central", pd.Series(dtype=float)).sum()
        ),
        "max_abs_error_people": max_residual_error,
        "unlocated_residuals_remain_in_ledger": True,
    }

    _assert(
        reach_source_sha256 == REACH_SOURCE_SHA256,
        "Production reach hash is not the pinned source hash.",
    )
    _assert(
        reaches["limit_minutes"].astype(int).tolist() == list(LIMITS),
        "Reach output limits are incomplete or unordered.",
    )
    monotonic_columns = (
        "central_estimated_employment",
        "uniform_allocation_employment",
        "building_volume_employment",
        "calibrated_workplace_model_employment",
        "residual_lower_bound_employment",
        "residual_upper_bound_employment",
    )
    for column in monotonic_columns:
        values = reaches[column].to_numpy(dtype=float)
        _assert((values >= -tolerance).all(), f"{column} is negative.")
        _assert((np.diff(values) >= -tolerance).all(), f"{column} is not monotonic.")
    _assert(
        (
            reaches["residual_lower_bound_employment"]
            <= reaches["central_estimated_employment"] + tolerance
        ).all(),
        "Residual lower bound exceeds the central estimate.",
    )
    _assert(
        (
            reaches["central_estimated_employment"]
            <= reaches["residual_upper_bound_employment"] + tolerance
        ).all(),
        "Central estimate exceeds residual upper bound.",
    )
    recomputed = (
        reaches["central_estimated_employment"] / CITY_EMPLOYMENT * 100.0
    )
    _assert(
        np.allclose(recomputed, reaches["percentage_of_shanghai_employment"], atol=1e-12),
        "Reported percentages do not use 13,099,795.",
    )
    _assert(
        reaches["denominator"].eq(CITY_EMPLOYMENT).all(),
        "A reach result uses a different denominator.",
    )
    _assert(
        reaches["employment_universe"].eq(EMPLOYMENT_UNIVERSE).all(),
        "A reach result has the wrong employment-universe label.",
    )
    _assert(
        reaches["geometry_is_approximate"].astype(bool).all(),
        "A reach result lost the approximate-boundary flag.",
    )
    checks["reach"] = {
        "source_sha256": reach_source_sha256,
        "limits": list(LIMITS),
        "monotonic": True,
        "bounds_ordered": True,
        "denominator": CITY_EMPLOYMENT,
        "partial_cell_rule": "area(cell intersection reach) / clipped cell_area_m2",
    }

    _assert(
        model_diagnostics["final_fit"]["converged"],
        "The final calibrated PPML model did not converge.",
    )
    required_metrics = {
        "mae_people",
        "mean_absolute_percentage_error",
        "weighted_absolute_percentage_error",
        "spearman_rank_correlation",
    }
    _assert(
        required_metrics <= set(model_diagnostics["all_control_metrics"]),
        "Calibrated model diagnostics are incomplete.",
    )
    checks["calibrated_model"] = {
        "cross_validation_design": model_diagnostics["cross_validation_design"],
        "all_control_metrics": model_diagnostics["all_control_metrics"],
        "top_employment_control_metrics": model_diagnostics[
            "top_employment_control_metrics"
        ],
        "high_employment_underprediction_count": len(
            model_diagnostics["obvious_high_employment_underprediction"]
        ),
        "final_fit_converged": True,
        "nonlinear_alternative": model_diagnostics["nonlinear_alternative"],
        "acceptance_gate": model_diagnostics["acceptance_gate"],
    }

    if not boundary_review.empty:
        _assert(
            boundary_review["review_status"].isin(["pass", "fail"]).all(),
            "A reach-relevant boundary lacks official-map review.",
        )
        _assert(
            boundary_review["source_map"].str.contains("tianditu", case=False).all(),
            "Boundary review lost the authoritative map source.",
        )
    checks["official_map_review"] = {
        "reviewed_controls": int(len(boundary_review)),
        "passed": int((boundary_review["review_status"] == "pass").sum()),
        "failed": int((boundary_review["review_status"] == "fail").sum()),
    }

    metadata_text = (
        str(reaches.to_dict(orient="records"))
        + str(control_geometries["boundary_source"].tolist())
    ).lower()
    _assert("openrouteservice" not in metadata_text, "Employment metadata references ORS.")
    _assert("boss直聘" not in metadata_text, "A prohibited vacancy source appears.")
    _assert("51job" not in metadata_text, "A prohibited vacancy source appears.")
    checks["prohibited_sources_absent"] = True
    checks["osm_attribution"] = OSM_LICENSE
    return {
        "status": "hard_checks_passed_model_gate_failed",
        "checks": checks,
        "interpretation": (
            "Accounting, geometry, reach, and reproducibility checks pass, but the "
            "calibrated workplace model is not accepted because high-employment "
            "spatial holdout performance remains poor."
        ),
    }
