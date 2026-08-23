import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OFFICE_DATA = ROOT / "data/office_employment"
SCENARIO_DATA = OFFICE_DATA / "scenarios"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_scenarios_preserve_core_city_totals_and_subgroup_totals():
    district = pd.read_csv(
        SCENARIO_DATA / "district-core-plus-scenarios-2023.csv"
    )
    subgroup = pd.read_csv(
        SCENARIO_DATA
        / "district-business-services-subgroup-scenarios-2023.csv",
        dtype={"industry_code": str},
    )
    assert len(district) == 16
    assert len(subgroup) == 16 * 4 * 3
    assert not subgroup.duplicated(
        ["scenario", "district", "industry_code"]
    ).any()
    assert int(district["core_office_employment_hard_control"].sum()) == 2_477_585
    for scenario in [
        "low_office_intensity",
        "base",
        "high_office_intensity",
    ]:
        assert int(district[f"{scenario}_selected_72_employment"].sum()) == 743_125
        assert int(district[f"{scenario}_core_plus_employment"].sum()) == 3_220_710
        scenario_subgroups = subgroup.loc[subgroup["scenario"] == scenario]
        totals = scenario_subgroups.groupby("industry_code").agg(
            allocated=("scenario_district_subgroup_employment", "sum"),
            official=("official_city_subgroup_employment", "first"),
        )
        assert totals["allocated"].equals(totals["official"])
    assert (subgroup["scenario_district_subgroup_employment"] >= 0).all()
    assert subgroup["core_is_hard_control"].all()
    assert not subgroup["geometry_or_spatial_allocation_used"].any()
    for scenario in [
        "low_office_intensity",
        "base",
        "high_office_intensity",
    ]:
        share = district[
            f"{scenario}_selected_72_share_of_official_division_72_percentage"
        ]
        assert share.between(0.0, 100.0).all()


def test_base_scenario_exactly_matches_current_core_plus_controls():
    scenario = pd.read_csv(
        SCENARIO_DATA / "district-core-plus-scenarios-2023.csv"
    )
    current = pd.read_csv(
        OFFICE_DATA / "outputs/district-core-plus-controls-2023.csv"
    )
    joined = scenario.merge(current, on="district", validate="one_to_one")
    assert joined["base_selected_72_employment"].equals(
        joined["core_plus_selected_72_employment_estimate"]
    )
    assert joined["base_core_plus_employment"].equals(
        joined["core_plus_office_employment_estimate"]
    )
    assert (joined["base_difference_from_base_employment"] == 0).all()
    assert joined[
        "base_selected_72_share_of_official_division_72_percentage"
    ].between(39.020, 39.025).all()


def test_targeted_sensitivity_changes_only_five_priority_districts():
    district = pd.read_csv(
        SCENARIO_DATA / "district-core-plus-scenarios-2023.csv"
    ).set_index("district")
    office_centres = {"黄浦区", "静安区", "长宁区", "普陀区"}
    risk_district = "宝山区"
    changed = set(
        district.index[
            (district["low_office_intensity_difference_from_base_employment"] != 0)
            | (
                district[
                    "high_office_intensity_difference_from_base_employment"
                ]
                != 0
            )
        ]
    )
    assert changed == office_centres | {risk_district}
    assert (
        district.loc[
            list(office_centres),
            "low_office_intensity_difference_from_base_employment",
        ]
        < 0
    ).all()
    assert (
        district.loc[
            list(office_centres),
            "high_office_intensity_difference_from_base_employment",
        ]
        > 0
    ).all()
    assert (
        district.loc[
            risk_district,
            "low_office_intensity_difference_from_base_employment",
        ]
        == 12_983
    )
    assert (
        district.loc[
            risk_district,
            "high_office_intensity_difference_from_base_employment",
        ]
        == -12_983
    )


def test_scenario_rank_changes_are_bounded_and_reconciled():
    ranking = pd.read_csv(
        SCENARIO_DATA / "district-core-plus-ranking-changes-2023.csv"
    )
    assert len(ranking) == 16 * 3
    assert ranking["employment_rank"].between(1, 16).all()
    assert ranking["intensity_rank"].between(1, 16).all()
    assert (
        ranking.loc[
            ranking["scenario"] == "base",
            [
                "difference_from_base_employment",
                "employment_rank_change_from_base",
                "intensity_rank_change_from_base",
            ],
        ]
        == 0
    ).all().all()
    assert ranking["employment_rank_change_from_base"].abs().max() <= 2
    assert ranking["intensity_rank_change_from_base"].abs().max() <= 2


def test_sensitivity_outputs_prohibit_grid_and_reach_calculation():
    summary = json.loads(
        (
            SCENARIO_DATA / "core-plus-sensitivity-summary-2023.json"
        ).read_text(encoding="utf-8")
    )
    district = pd.read_csv(
        SCENARIO_DATA / "district-core-plus-scenarios-2023.csv"
    )
    assert summary["spatial_allocation_performed"] is False
    assert summary["grid_created"] is False
    assert summary["reach_percentage_calculated"] is False
    assert district["no_spatial_allocation_performed"].all()
    assert not district["grid_created"].any()
    assert not district["reach_percentage_calculated"].any()


def test_frozen_office_and_production_outputs_remain_unchanged():
    expected = {
        "data/office_employment/outputs/district-core-plus-controls-2023.csv": "ba20d46e2afe336d334513c8ff12686027f3362d23f2a7a488072345d7023eb2",
        "data/office_employment/intermediate/district-business-services-subgroup-allocation-2023.csv": "9a045cf0f655a268b35d63d0379fed02b1982964d53c07d31d87e6876cdc4a66",
        "data/office_employment/outputs/district-core-plus-summary-2023.json": "407b14c09e2b4d779bc96b9785d1d60eb7b1ae2d5a11becc4bdfaca57a1e23b5",
        "web/public/data/reach-employment.json": "7f4a7447e52f70c595e3be9d0b38e1fc3ec06e9c8c3e3350a095b997cc87b105",
        "web/public/data/reach-economy.json": "4054f47f07afa1e53612b50d965b3094161f43d94e8420a96911d6ac3c5731ca",
        "web/public/data/reach-areas.geojson": "6f039b0661f63c1017a2c4a3bc8f5c4d8fdef207ca10afe987f160642fb5656b",
    }
    assert {path: _sha256(ROOT / path) for path in expected} == expected
