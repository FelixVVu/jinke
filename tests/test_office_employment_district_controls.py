import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OFFICE_DATA = ROOT / "data/office_employment"


def test_selected_subgroups_reconcile_to_official_city_totals():
    allocation = pd.read_csv(
        OFFICE_DATA
        / "intermediate/district-business-services-subgroup-allocation-2023.csv",
        dtype={"industry_code": str},
    )
    assert len(allocation) == 16 * 4
    assert set(allocation["industry_code"]) == {"721", "723", "724", "725"}
    assert not allocation.duplicated(["district", "industry_code"]).any()
    assert (allocation["estimated_district_subgroup_employment"] >= 0).all()
    assert allocation["district_subgroup_is_modelled"].all()
    assert not allocation["geometry_or_spatial_allocation_used"].any()
    reconciled = allocation.groupby("industry_code").agg(
        allocated=("estimated_district_subgroup_employment", "sum"),
        official=("official_city_subgroup_employment", "first"),
    )
    assert reconciled["allocated"].equals(reconciled["official"])


def test_district_core_plus_controls_preserve_official_margins():
    controls = pd.read_csv(
        OFFICE_DATA / "outputs/district-core-plus-controls-2023.csv"
    )
    official = pd.read_csv(
        OFFICE_DATA / "outputs/district-office-employment-controls-2023.csv"
    )
    detail = pd.read_csv(
        OFFICE_DATA / "intermediate/district-industry-employment-2023.csv",
        dtype={"industry_code": str},
    )
    official_72 = detail.loc[
        detail["industry_code"] == "72",
        ["district", "district_industry_employment"],
    ].rename(columns={"district_industry_employment": "expected_72"})
    joined = controls.merge(official, on="district", validate="one_to_one").merge(
        official_72, on="district", validate="one_to_one"
    )
    assert len(joined) == 16
    assert np.array_equal(
        joined["core_office_employment_official"],
        joined["core_office_employment"],
    )
    assert np.array_equal(
        joined["business_services_72_employment_official"], joined["expected_72"]
    )
    assert np.array_equal(
        joined["broad_professional_institutional_employment_official"],
        joined["broad_office_employment"],
    )
    assert joined["core_and_full_72_are_official"].all()
    assert joined["core_plus_72_is_modelled"].all()
    assert joined["no_spatial_allocation_performed"].all()


def test_core_core_plus_broad_and_721_sensitivity_reconcile():
    controls = pd.read_csv(
        OFFICE_DATA / "outputs/district-core-plus-controls-2023.csv"
    )
    assert int(controls["core_office_employment_official"].sum()) == 2_477_585
    assert int(controls["business_services_72_employment_official"].sum()) == 1_904_322
    assert int(controls["core_plus_selected_72_employment_estimate"].sum()) == 743_125
    assert int(controls["core_plus_office_employment_estimate"].sum()) == 3_220_710
    assert int(
        controls[
            "core_plus_721_excluded_selected_72_employment_estimate"
        ].sum()
    ) == 514_837
    assert int(
        controls["core_plus_721_excluded_office_employment_estimate"].sum()
    ) == 2_992_422
    assert int(controls["core_plus_721_sensitivity_difference"].sum()) == 228_288
    assert int(
        controls["broad_professional_institutional_employment_official"].sum()
    ) == 6_374_547
    assert (
        controls["core_office_employment_official"]
        <= controls["core_plus_721_excluded_office_employment_estimate"]
    ).all()
    assert (
        controls["core_plus_721_excluded_office_employment_estimate"]
        <= controls["core_plus_office_employment_estimate"]
    ).all()
    assert (
        controls["core_plus_office_employment_estimate"]
        <= controls["broad_professional_institutional_employment_official"]
    ).all()


def test_district_control_summary_prohibits_spatial_outputs():
    summary = json.loads(
        (
            OFFICE_DATA / "outputs/district-core-plus-summary-2023.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["core_plus_office_employment"] == 3_220_710
    assert summary["core_plus_721_excluded_office_employment"] == 2_992_422
    assert summary["core_plus_721_sensitivity_employment"] == 228_288
    assert summary["district_core_and_full_72_are_official"] is True
    assert summary["district_core_plus_72_is_modelled"] is True
    assert summary["spatial_allocation_performed"] is False
    assert summary["grid_created"] is False
    assert summary["reach_percentage_calculated"] is False


def test_existing_reach_employment_and_gdp_outputs_are_unchanged():
    employment = json.loads(
        (ROOT / "web/public/data/reach-employment.json").read_text(encoding="utf-8")
    )
    result_50 = next(
        row for row in employment["results"] if int(row["limit_minutes"]) == 50
    )
    assert np.isclose(result_50["central_estimated_employment"], 3_691_257.9268553634)
    assert np.isclose(result_50["percentage_of_shanghai_employment"], 28.177982379536193)
    assert (ROOT / "web/public/data/reach-economy.json").exists()
    assert (ROOT / "web/public/data/reach-areas.geojson").exists()
