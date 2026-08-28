import json
from pathlib import Path

import numpy as np
import pandas as pd

from employment_pipeline.config import (
    CITY_EMPLOYMENT,
    NOMINAL_FINE_CONTROL_EMPLOYMENT,
    NOMINAL_RESIDUAL_EMPLOYMENT,
)
from employment_pipeline.structural import (
    AREA_FRACTION_TOLERANCE,
    FULLY_INSIDE,
    FULLY_OUTSIDE,
    MATERIALLY_PARTIAL,
    classify_support_fraction,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "data/employment/outputs"


def test_structural_support_classification_tolerance_is_explicit_and_strict():
    tolerance = AREA_FRACTION_TOLERANCE
    assert tolerance == 1e-6
    assert classify_support_fraction(0.0) == FULLY_OUTSIDE
    assert classify_support_fraction(tolerance) == FULLY_OUTSIDE
    assert classify_support_fraction(np.nextafter(tolerance, 1.0)) == MATERIALLY_PARTIAL
    assert classify_support_fraction(np.nextafter(1.0 - tolerance, 0.0)) == (
        MATERIALLY_PARTIAL
    )
    assert classify_support_fraction(1.0 - tolerance) == FULLY_INSIDE
    assert classify_support_fraction(1.0) == FULLY_INSIDE


def test_all_116_controls_reconcile_to_structural_categories_and_models():
    controls = pd.read_csv(
        OUTPUTS / "structural-certainty-controls-50min.csv",
        dtype={"accounting_stratum_id": "string"},
    )
    assert len(controls) == 116
    assert controls["accounting_stratum_id"].is_unique
    assert controls["geometry_is_approximate"].astype(bool).all()
    assert controls["support_classification"].value_counts().to_dict() == {
        MATERIALLY_PARTIAL: 69,
        FULLY_OUTSIDE: 34,
        FULLY_INSIDE: 13,
    }
    employment = controls.groupby("support_classification")[
        "official_control_employment"
    ].sum()
    assert employment.to_dict() == {
        FULLY_INSIDE: 959_621,
        FULLY_OUTSIDE: 1_786_761,
        MATERIALLY_PARTIAL: 4_368_129,
    }
    assert int(employment.sum()) == NOMINAL_FINE_CONTROL_EMPLOYMENT
    assert controls["area_fraction_inside"].between(0.0, 1.0).all()
    assert np.allclose(
        controls["uniform_jobs_inside"],
        controls["official_control_employment"]
        * controls["area_fraction_inside"],
        atol=1e-5,
    )
    model_columns = [
        "uniform_jobs_inside",
        "building_jobs_inside",
        "ppml_jobs_inside",
    ]
    assert np.allclose(
        controls["model_max_minus_min_jobs"],
        controls[model_columns].max(axis=1) - controls[model_columns].min(axis=1),
    )
    partial = controls.loc[
        controls["support_classification"] == MATERIALLY_PARTIAL
    ].sort_values("partial_uncertainty_rank")
    selected = partial.loc[
        partial["in_smallest_set_covering_80pct_model_spread"].astype(bool)
    ]
    assert len(selected) == 28
    coverage = (
        selected["model_max_minus_min_jobs"].sum()
        / partial["model_max_minus_min_jobs"].sum()
    )
    assert coverage >= 0.80
    assert (
        selected.iloc[:-1]["model_max_minus_min_jobs"].sum()
        / partial["model_max_minus_min_jobs"].sum()
    ) < 0.80


def test_structural_bounds_answers_and_separate_ledgers_are_reconciled():
    summary = json.loads(
        (OUTPUTS / "structural-certainty-summary-50min.json").read_text()
    )
    bound = summary["allocation_free_fine_control_bound"]
    assert bound["lower_employment"] == 959_621
    assert bound["upper_employment"] == 5_327_750
    assert bound["width_employment"] == 4_368_129
    assert bound["residual_workers_included"] == 0
    assert bound["pudong_functional_zone_boundary_perturbation_included"] is False
    assert np.isclose(
        bound["upper_shanghai_percentage"],
        bound["upper_employment"] / CITY_EMPLOYMENT * 100.0,
    )
    current = summary["current_50min_result_unchanged"]
    assert np.isclose(current["employment"], 3_691_257.9268553634)
    assert np.isclose(current["percentage"], 28.177982379536193)
    components = summary["current_numerator_components"]
    assert np.isclose(sum(components.values()), current["employment"])
    answers = summary["answers"]
    assert np.isclose(
        answers["A_official_census_determined_percentage_of_current_numerator"],
        25.997126698147454,
    )
    assert np.isclose(
        answers["B_partial_spatial_allocation_percentage_of_current_numerator"],
        70.40589208124548,
    )
    assert answers["C_selected_support_fine_bound_can_exceed_40_percent"] is True
    assert answers["C_can_exceed_50_percent_under_explicit_extremes"] is False
    ledgers = summary["separate_uncertainty_ledgers"]
    assert ledgers["residual_location_workers"] == NOMINAL_RESIDUAL_EMPLOYMENT
    assert ledgers["pudong_zone_boundary_additional_upper_workers"] == 149_000
    assert np.isclose(
        ledgers["extreme_ceiling_employment"] / CITY_EMPLOYMENT * 100.0,
        answers[
            "C_extreme_ceiling_with_all_residual_and_pudong_zone_boundary_upper_percentage"
        ],
    )
    assert answers[
        "C_extreme_ceiling_with_all_residual_and_pudong_zone_boundary_upper_percentage"
    ] < 50.0


def test_district_structural_decomposition_is_complete_and_additive():
    long = pd.read_csv(OUTPUTS / "structural-certainty-districts-50min.csv")
    bounds = pd.read_csv(
        OUTPUTS / "structural-certainty-district-bounds-50min.csv"
    )
    assert len(long) == 24
    assert len(bounds) == 8
    assert long.groupby("district")["support_classification"].nunique().eq(3).all()
    assert int(long["official_control_employment"].sum()) == (
        NOMINAL_FINE_CONTROL_EMPLOYMENT
    )
    assert int(bounds["fine_controlled_employment"].sum()) == (
        NOMINAL_FINE_CONTROL_EMPLOYMENT
    )
    assert int(bounds["residual_employment_separate"].sum()) == (
        NOMINAL_RESIDUAL_EMPLOYMENT
    )
    assert int(bounds["structural_lower_bound_fine_employment"].sum()) == 959_621
    assert int(bounds["structural_upper_bound_fine_employment"].sum()) == 5_327_750
    assert np.isclose(
        bounds["ppml_jobs_inside_50min"].sum(),
        3_558_484.0724222064,
    )
