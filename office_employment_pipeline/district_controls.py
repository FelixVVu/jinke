"""Construct district-level Core+ controls without spatial allocation.

The official census publishes exact district totals for division 72 and exact
Shanghai totals for three-digit groups 721-729, but not their cross-tabulation.
This module applies the maximum-entropy independence solution and controlled
integer rounding to the four Core+ groups. It creates district controls only;
it does not create a grid or intersect any reach polygon.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from office_employment_pipeline.source_audit import (
    CITY_EMPLOYMENT,
    DISTRICTS,
    EMPLOYMENT_UNIVERSE,
    REFERENCE_DATE,
)


DIVISION_72_EMPLOYMENT = 1_904_322
CORE_EMPLOYMENT = 2_477_585
CORE_PLUS_EMPLOYMENT = 3_220_710
CORE_PLUS_EXCLUDING_721_EMPLOYMENT = 2_992_422
BROAD_EMPLOYMENT = 6_374_547
CORE_PLUS_CODES = ("721", "723", "724", "725")
CORE_PLUS_EXCLUDING_721_CODES = ("723", "724", "725")
ALLOCATION_METHOD = (
    "maximum-entropy independence allocation proportional to official district "
    "division-72 employment, with largest-remainder reconciliation to each "
    "official Shanghai subgroup total"
)


def _largest_remainder_allocation(
    district_72: pd.Series, subgroup_total: int
) -> pd.Series:
    """Allocate one official subgroup total across fixed district-72 margins."""

    raw = district_72.astype(float) * subgroup_total / DIVISION_72_EMPLOYMENT
    allocated = raw.astype(int)
    remainder = subgroup_total - int(allocated.sum())
    order = (raw - allocated).sort_values(
        ascending=False, kind="mergesort"
    ).index
    allocated.loc[order[:remainder]] += 1
    if int(allocated.sum()) != subgroup_total:
        raise ValueError("Controlled rounding failed to preserve subgroup total.")
    if (allocated < 0).any():
        raise ValueError("Negative district subgroup employment is not allowed.")
    return allocated


def construct_district_core_plus_controls(
    district_industry: pd.DataFrame,
    business_subindustries: pd.DataFrame,
    official_controls: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Return subgroup estimates, district controls, and reconciliation summary."""

    detail = district_industry.copy()
    detail["industry_code"] = detail["industry_code"].astype(str)
    subindustries = business_subindustries.copy()
    subindustries["industry_code"] = subindustries["industry_code"].astype(str)
    controls = official_controls.copy().set_index("district").reindex(DISTRICTS)
    if controls.index.isna().any() or controls.isna().any().any():
        raise ValueError("Official district controls are incomplete.")

    district_72_rows = detail.loc[detail["industry_code"] == "72"]
    if len(district_72_rows) != len(DISTRICTS):
        raise ValueError("Expected one official division-72 row per district.")
    district_72 = (
        district_72_rows.set_index("district")["district_industry_employment"]
        .reindex(DISTRICTS)
        .astype(int)
    )
    if int(district_72.sum()) != DIVISION_72_EMPLOYMENT:
        raise ValueError("Official district division-72 totals do not reconcile.")
    if int(controls["core_office_employment"].sum()) != CORE_EMPLOYMENT:
        raise ValueError("Official district Core totals changed.")
    if int(controls["broad_office_employment"].sum()) != BROAD_EMPLOYMENT:
        raise ValueError("Official district Broad totals changed.")

    selected = subindustries.loc[
        subindustries["industry_code"].isin(CORE_PLUS_CODES)
    ].set_index("industry_code")
    if set(selected.index) != set(CORE_PLUS_CODES):
        raise ValueError("Core+ business-service subgroup evidence is incomplete.")

    subgroup_records: list[dict[str, object]] = []
    allocations: dict[str, pd.Series] = {}
    for code in CORE_PLUS_CODES:
        subgroup_total = int(selected.loc[code, "official_city_employment"])
        allocation = _largest_remainder_allocation(district_72, subgroup_total)
        allocations[code] = allocation
        for district in DISTRICTS:
            subgroup_records.append(
                {
                    "district": district,
                    "industry_code": code,
                    "industry_name": selected.loc[code, "industry_name"],
                    "official_city_subgroup_employment": subgroup_total,
                    "official_district_72_employment": int(
                        district_72.loc[district]
                    ),
                    "estimated_district_subgroup_employment": int(
                        allocation.loc[district]
                    ),
                    "allocation_method": ALLOCATION_METHOD,
                    "district_subgroup_is_modelled": True,
                    "geometry_or_spatial_allocation_used": False,
                    "reference_date": REFERENCE_DATE,
                    "employment_universe": EMPLOYMENT_UNIVERSE,
                }
            )
    subgroup_table = pd.DataFrame(subgroup_records)

    selected_including_721 = sum(
        (allocations[code] for code in CORE_PLUS_CODES),
        start=pd.Series(0, index=DISTRICTS, dtype=int),
    )
    selected_excluding_721 = sum(
        (allocations[code] for code in CORE_PLUS_EXCLUDING_721_CODES),
        start=pd.Series(0, index=DISTRICTS, dtype=int),
    )
    core = controls["core_office_employment"].astype(int)
    broad = controls["broad_office_employment"].astype(int)
    all_industry = controls["official_all_industry_employment"].astype(int)
    core_plus = core + selected_including_721
    core_plus_excluding_721 = core + selected_excluding_721

    district_table = pd.DataFrame(
        {
            "district": DISTRICTS,
            "official_all_industry_employment": all_industry.to_numpy(),
            "core_office_employment_official": core.to_numpy(),
            "business_services_72_employment_official": district_72.to_numpy(),
            "core_plus_selected_72_employment_estimate": selected_including_721.to_numpy(),
            "core_plus_office_employment_estimate": core_plus.to_numpy(),
            "core_plus_721_excluded_selected_72_employment_estimate": selected_excluding_721.to_numpy(),
            "core_plus_721_excluded_office_employment_estimate": core_plus_excluding_721.to_numpy(),
            "core_plus_721_sensitivity_difference": (
                selected_including_721 - selected_excluding_721
            ).to_numpy(),
            "broad_professional_institutional_employment_official": broad.to_numpy(),
        }
    )
    district_table["core_plus_share_of_district_employment_percentage"] = (
        district_table["core_plus_office_employment_estimate"]
        / district_table["official_all_industry_employment"]
        * 100.0
    )
    district_table[
        "core_plus_721_excluded_share_of_district_employment_percentage"
    ] = (
        district_table["core_plus_721_excluded_office_employment_estimate"]
        / district_table["official_all_industry_employment"]
        * 100.0
    )
    district_table["allocation_method"] = ALLOCATION_METHOD
    district_table["core_and_full_72_are_official"] = True
    district_table["core_plus_72_is_modelled"] = True
    district_table["no_spatial_allocation_performed"] = True
    district_table["reference_date"] = REFERENCE_DATE
    district_table["employment_universe"] = EMPLOYMENT_UNIVERSE

    if int(selected_including_721.sum()) != 743_125:
        raise ValueError("Selected 721/723/724/725 controls do not reconcile.")
    if int(selected_excluding_721.sum()) != 514_837:
        raise ValueError("Selected 723/724/725 sensitivity does not reconcile.")
    if int(core_plus.sum()) != CORE_PLUS_EMPLOYMENT:
        raise ValueError("District Core+ controls do not reconcile to 3,220,710.")
    if int(core_plus_excluding_721.sum()) != CORE_PLUS_EXCLUDING_721_EMPLOYMENT:
        raise ValueError("721-excluded sensitivity does not reconcile.")
    if int((selected_including_721 - selected_excluding_721).sum()) != 228_288:
        raise ValueError("721 sensitivity does not reconcile to its official total.")
    if (selected_including_721 > district_72).any():
        raise ValueError("A selected district subtotal exceeds official division 72.")
    if not (core <= core_plus).all() or not (core_plus <= broad).all():
        raise ValueError("District Core/Core+/Broad nesting failed.")

    summary = {
        "schema_version": 1,
        "reference_date": REFERENCE_DATE,
        "employment_universe": EMPLOYMENT_UNIVERSE,
        "official_all_industry_employment": CITY_EMPLOYMENT,
        "core_office_employment_official": CORE_EMPLOYMENT,
        "core_share_of_shanghai_all_industry_percentage": CORE_EMPLOYMENT
        / CITY_EMPLOYMENT
        * 100.0,
        "core_plus_office_employment": CORE_PLUS_EMPLOYMENT,
        "core_plus_share_of_shanghai_all_industry_percentage": CORE_PLUS_EMPLOYMENT
        / CITY_EMPLOYMENT
        * 100.0,
        "core_plus_selected_72_employment": 743_125,
        "core_plus_selected_72_codes": list(CORE_PLUS_CODES),
        "core_plus_721_excluded_office_employment": CORE_PLUS_EXCLUDING_721_EMPLOYMENT,
        "core_plus_721_excluded_share_of_shanghai_all_industry_percentage": CORE_PLUS_EXCLUDING_721_EMPLOYMENT
        / CITY_EMPLOYMENT
        * 100.0,
        "core_plus_721_excluded_selected_72_employment": 514_837,
        "core_plus_721_sensitivity_employment": 228_288,
        "core_plus_721_sensitivity_shanghai_percentage_points": 228_288
        / CITY_EMPLOYMENT
        * 100.0,
        "broad_professional_institutional_employment_official": BROAD_EMPLOYMENT,
        "broad_share_of_shanghai_all_industry_percentage": BROAD_EMPLOYMENT
        / CITY_EMPLOYMENT
        * 100.0,
        "district_count": len(DISTRICTS),
        "allocation_method": ALLOCATION_METHOD,
        "district_core_and_full_72_are_official": True,
        "district_core_plus_72_is_modelled": True,
        "spatial_allocation_performed": False,
        "grid_created": False,
        "reach_percentage_calculated": False,
    }
    return subgroup_table, district_table, summary


def write_outputs(repository_root: Path) -> None:
    office_data = repository_root / "data/office_employment"
    district_industry = pd.read_csv(
        office_data / "intermediate/district-industry-employment-2023.csv",
        dtype={"industry_code": str},
    )
    business_subindustries = pd.read_csv(
        office_data / "intermediate/business-services-subindustry-employment-2023.csv",
        dtype={"industry_code": str},
    )
    official_controls = pd.read_csv(
        office_data / "outputs/district-office-employment-controls-2023.csv"
    )
    subgroup_table, district_table, summary = construct_district_core_plus_controls(
        district_industry, business_subindustries, official_controls
    )
    subgroup_table.to_csv(
        office_data
        / "intermediate/district-business-services-subgroup-allocation-2023.csv",
        index=False,
    )
    district_table.to_csv(
        office_data / "outputs/district-core-plus-controls-2023.csv", index=False
    )
    (office_data / "outputs/district-core-plus-summary-2023.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    write_outputs(args.repository_root.resolve())


if __name__ == "__main__":
    main()
