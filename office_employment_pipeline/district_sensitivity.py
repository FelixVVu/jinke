"""Build district Core+ composition scenarios without spatial allocation.

Core remains an immutable official hard control.  The three Core+ scenarios
change only the estimated district composition of selected division-72 groups
(721, 723, 724, and 725).  Every scenario preserves each official Shanghai
subgroup total and the fixed city Core+ total of 3,220,710.

This module does not create geometry, a 100 m grid, a reach intersection, or a
reach percentage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from office_employment_pipeline.district_controls import (
    CORE_PLUS_CODES,
    CORE_PLUS_EMPLOYMENT,
)
from office_employment_pipeline.source_audit import (
    CITY_EMPLOYMENT,
    DISTRICTS,
    EMPLOYMENT_UNIVERSE,
    REFERENCE_DATE,
)


SCENARIOS = (
    "low_office_intensity",
    "base",
    "high_office_intensity",
)
SCENARIO_LABELS = {
    "low_office_intensity": "Low office intensity",
    "base": "Base",
    "high_office_intensity": "High office intensity",
}
PRIORITY_OFFICE_CENTRES = ("黄浦区", "静安区", "长宁区", "普陀区")
COMPOSITION_RISK_DISTRICT = "宝山区"
TRANSFER_FRACTION = 0.20
SELECTED_72_EMPLOYMENT = 743_125
BASE_SELECTED_72_SHARE = SELECTED_72_EMPLOYMENT / 1_904_322

SCENARIO_METHOD = (
    "subgroup-conserving targeted composition sensitivity: Base preserves the "
    "current maximum-entropy allocation; Low transfers 20% of Baoshan's Base "
    "selected-72 allocation from Huangpu/Jing'an/Changning/Putuo to Baoshan; "
    "High reverses the same transfer. Each 721/723/724/725 Shanghai total is "
    "preserved exactly."
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _largest_remainder_from_weights(
    weights: pd.Series, total: int
) -> pd.Series:
    """Allocate an integer total over positive weights deterministically."""

    weights = weights.astype(float)
    if weights.empty or (weights <= 0).any():
        raise ValueError("Largest-remainder weights must all be positive.")
    raw = weights / float(weights.sum()) * int(total)
    allocated = raw.map(math.floor).astype(int)
    remainder = int(total) - int(allocated.sum())
    order = (raw - allocated).sort_values(
        ascending=False, kind="mergesort"
    ).index
    allocated.loc[order[:remainder]] += 1
    if int(allocated.sum()) != int(total):
        raise ValueError("Largest-remainder allocation did not reconcile.")
    return allocated


def _scenario_allocation(
    base: pd.Series, scenario: str
) -> tuple[pd.Series, int]:
    """Return one subgroup scenario and its Baoshan transfer magnitude."""

    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown Core+ scenario: {scenario}")
    allocation = base.astype(int).copy()
    if scenario == "base":
        return allocation, 0

    transfer = int(
        math.floor(
            float(base.loc[COMPOSITION_RISK_DISTRICT])
            * TRANSFER_FRACTION
            + 0.5
        )
    )
    centre_distribution = _largest_remainder_from_weights(
        base.loc[list(PRIORITY_OFFICE_CENTRES)], transfer
    )
    direction = 1 if scenario == "high_office_intensity" else -1
    allocation.loc[COMPOSITION_RISK_DISTRICT] -= direction * transfer
    allocation.loc[list(PRIORITY_OFFICE_CENTRES)] += (
        direction * centre_distribution
    )
    if (allocation < 0).any():
        raise ValueError("Scenario produced negative district employment.")
    if int(allocation.sum()) != int(base.sum()):
        raise ValueError("Scenario changed an official city subgroup total.")
    return allocation, transfer


def construct_core_plus_scenarios(
    base_subgroups: pd.DataFrame,
    base_district_controls: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Construct subgroup, district, rank, and summary sensitivity artifacts."""

    subgroup = base_subgroups.copy()
    subgroup["industry_code"] = subgroup["industry_code"].astype(str)
    district = base_district_controls.copy().set_index("district").reindex(DISTRICTS)
    if district.isna().any().any():
        raise ValueError("Base district Core+ controls are incomplete.")
    if set(subgroup["industry_code"]) != set(CORE_PLUS_CODES):
        raise ValueError("Base subgroup table does not contain the four Core+ groups.")
    if subgroup.duplicated(["district", "industry_code"]).any():
        raise ValueError("Base subgroup table contains duplicate accounting rows.")

    core = district["core_office_employment_official"].astype(int)
    district_72 = district["business_services_72_employment_official"].astype(int)
    all_industry = district["official_all_industry_employment"].astype(int)
    base_selected = district[
        "core_plus_selected_72_employment_estimate"
    ].astype(int)
    base_core_plus = district["core_plus_office_employment_estimate"].astype(int)

    subgroup_records: list[dict[str, object]] = []
    scenario_selected: dict[str, pd.Series] = {}
    transfer_by_code: dict[str, int] = {}
    for scenario in SCENARIOS:
        allocations: list[pd.Series] = []
        for code in CORE_PLUS_CODES:
            rows = subgroup.loc[subgroup["industry_code"] == code].set_index(
                "district"
            ).reindex(DISTRICTS)
            if rows.isna().any().any():
                raise ValueError(f"Subgroup {code} is missing a district row.")
            base_allocation = rows[
                "estimated_district_subgroup_employment"
            ].astype(int)
            scenario_allocation, transfer = _scenario_allocation(
                base_allocation, scenario
            )
            if scenario == "high_office_intensity":
                transfer_by_code[code] = transfer
            official_total = int(rows["official_city_subgroup_employment"].iloc[0])
            if int(scenario_allocation.sum()) != official_total:
                raise ValueError(
                    f"Scenario {scenario} changed official subgroup {code}."
                )
            allocations.append(scenario_allocation)
            for district_name in DISTRICTS:
                base_value = int(base_allocation.loc[district_name])
                scenario_value = int(scenario_allocation.loc[district_name])
                role = "neutral"
                if district_name in PRIORITY_OFFICE_CENTRES:
                    role = "priority_office_centre"
                elif district_name == COMPOSITION_RISK_DISTRICT:
                    role = "composition_risk"
                subgroup_records.append(
                    {
                        "scenario": scenario,
                        "scenario_label": SCENARIO_LABELS[scenario],
                        "district": district_name,
                        "district_sensitivity_role": role,
                        "industry_code": code,
                        "industry_name": rows.loc[district_name, "industry_name"],
                        "official_city_subgroup_employment": official_total,
                        "official_district_72_employment": int(
                            district_72.loc[district_name]
                        ),
                        "base_district_subgroup_employment": base_value,
                        "scenario_district_subgroup_employment": scenario_value,
                        "difference_from_base": scenario_value - base_value,
                        "scenario_method": SCENARIO_METHOD,
                        "district_subgroup_is_modelled": True,
                        "core_is_hard_control": True,
                        "geometry_or_spatial_allocation_used": False,
                        "grid_created": False,
                        "reach_percentage_calculated": False,
                        "reference_date": REFERENCE_DATE,
                        "employment_universe": EMPLOYMENT_UNIVERSE,
                    }
                )
        scenario_selected[scenario] = sum(
            allocations,
            start=pd.Series(0, index=DISTRICTS, dtype=int),
        )

    if not scenario_selected["base"].equals(base_selected):
        raise ValueError("Base scenario no longer matches current Core+ controls.")

    district_table = pd.DataFrame(
        {
            "district": DISTRICTS,
            "official_all_industry_employment": all_industry.to_numpy(),
            "core_office_employment_hard_control": core.to_numpy(),
            "official_division_72_employment": district_72.to_numpy(),
        }
    ).set_index("district")

    rank_records: list[dict[str, object]] = []
    scenario_frames: dict[str, pd.DataFrame] = {}
    for scenario in SCENARIOS:
        selected = scenario_selected[scenario]
        core_plus = core + selected
        share = core_plus / all_industry * 100.0
        employment_rank = core_plus.rank(
            method="min", ascending=False
        ).astype(int)
        intensity_rank = share.rank(method="min", ascending=False).astype(int)
        scenario_frame = pd.DataFrame(
            {
                "selected_72": selected,
                "selected_72_share": selected / district_72 * 100.0,
                "core_plus": core_plus,
                "core_plus_share": share,
                "employment_rank": employment_rank,
                "intensity_rank": intensity_rank,
            }
        )
        scenario_frames[scenario] = scenario_frame
        prefix = scenario
        district_table[f"{prefix}_selected_72_employment"] = selected
        district_table[
            f"{prefix}_selected_72_share_of_official_division_72_percentage"
        ] = scenario_frame["selected_72_share"]
        district_table[f"{prefix}_core_plus_employment"] = core_plus
        district_table[
            f"{prefix}_core_plus_share_of_district_employment_percentage"
        ] = share
        district_table[f"{prefix}_employment_rank"] = employment_rank
        district_table[f"{prefix}_intensity_rank"] = intensity_rank

    for scenario in SCENARIOS:
        district_table[f"{scenario}_difference_from_base_employment"] = (
            scenario_frames[scenario]["core_plus"]
            - scenario_frames["base"]["core_plus"]
        )
        district_table[f"{scenario}_employment_rank_change_from_base"] = (
            scenario_frames[scenario]["employment_rank"]
            - scenario_frames["base"]["employment_rank"]
        )
        district_table[f"{scenario}_intensity_rank_change_from_base"] = (
            scenario_frames[scenario]["intensity_rank"]
            - scenario_frames["base"]["intensity_rank"]
        )
        for district_name in DISTRICTS:
            rank_records.append(
                {
                    "scenario": scenario,
                    "scenario_label": SCENARIO_LABELS[scenario],
                    "district": district_name,
                    "core_plus_employment": int(
                        scenario_frames[scenario].loc[
                            district_name, "core_plus"
                        ]
                    ),
                    "difference_from_base_employment": int(
                        district_table.loc[
                            district_name,
                            f"{scenario}_difference_from_base_employment",
                        ]
                    ),
                    "employment_rank": int(
                        scenario_frames[scenario].loc[
                            district_name, "employment_rank"
                        ]
                    ),
                    "employment_rank_change_from_base": int(
                        district_table.loc[
                            district_name,
                            f"{scenario}_employment_rank_change_from_base",
                        ]
                    ),
                    "core_plus_share_of_district_employment_percentage": float(
                        scenario_frames[scenario].loc[
                            district_name, "core_plus_share"
                        ]
                    ),
                    "intensity_rank": int(
                        scenario_frames[scenario].loc[
                            district_name, "intensity_rank"
                        ]
                    ),
                    "intensity_rank_change_from_base": int(
                        district_table.loc[
                            district_name,
                            f"{scenario}_intensity_rank_change_from_base",
                        ]
                    ),
                    "core_is_hard_control": True,
                    "core_plus_is_composition_sensitivity": True,
                    "grid_created": False,
                    "reach_percentage_calculated": False,
                }
            )

    if not scenario_frames["base"]["core_plus"].equals(base_core_plus):
        raise ValueError("Base scenario Core+ changed from current controls.")
    for scenario in SCENARIOS:
        if int(scenario_selected[scenario].sum()) != SELECTED_72_EMPLOYMENT:
            raise ValueError(f"Scenario {scenario} changed selected-72 total.")
        if int(scenario_frames[scenario]["core_plus"].sum()) != CORE_PLUS_EMPLOYMENT:
            raise ValueError(f"Scenario {scenario} changed city Core+ total.")
        if (scenario_selected[scenario] > district_72).any():
            raise ValueError(
                f"Scenario {scenario} selected-72 exceeds an official district margin."
            )
        if not (core <= scenario_frames[scenario]["core_plus"]).all():
            raise ValueError(f"Scenario {scenario} violates the Core hard control.")

    neutral_districts = set(DISTRICTS) - set(PRIORITY_OFFICE_CENTRES) - {
        COMPOSITION_RISK_DISTRICT
    }
    for district_name in neutral_districts:
        for scenario in ("low_office_intensity", "high_office_intensity"):
            if (
                district_table.loc[
                    district_name, f"{scenario}_difference_from_base_employment"
                ]
                != 0
            ):
                raise ValueError("Targeted scenario changed a neutral district.")

    district_table["district_sensitivity_role"] = "neutral"
    district_table.loc[
        list(PRIORITY_OFFICE_CENTRES), "district_sensitivity_role"
    ] = "priority_office_centre"
    district_table.loc[
        COMPOSITION_RISK_DISTRICT, "district_sensitivity_role"
    ] = "composition_risk"
    district_table["scenario_method"] = SCENARIO_METHOD
    district_table["core_is_hard_control"] = True
    district_table["core_plus_is_composition_sensitivity"] = True
    district_table["no_spatial_allocation_performed"] = True
    district_table["grid_created"] = False
    district_table["reach_percentage_calculated"] = False
    district_table["reference_date"] = REFERENCE_DATE
    district_table["employment_universe"] = EMPLOYMENT_UNIVERSE
    district_table = district_table.reset_index()

    subgroup_table = pd.DataFrame(subgroup_records)
    ranking_table = pd.DataFrame(rank_records)
    changed_rank_rows = ranking_table.loc[
        (ranking_table["employment_rank_change_from_base"] != 0)
        | (ranking_table["intensity_rank_change_from_base"] != 0)
    ]
    summary = {
        "schema_version": 1,
        "reference_date": REFERENCE_DATE,
        "employment_universe": EMPLOYMENT_UNIVERSE,
        "official_all_industry_employment": CITY_EMPLOYMENT,
        "core_is_hard_control": True,
        "core_plus_city_employment_fixed_in_all_scenarios": CORE_PLUS_EMPLOYMENT,
        "selected_72_city_employment_fixed_in_all_scenarios": SELECTED_72_EMPLOYMENT,
        "base_selected_72_share_percentage": BASE_SELECTED_72_SHARE * 100.0,
        "scenarios": list(SCENARIOS),
        "scenario_labels": SCENARIO_LABELS,
        "scenario_method": SCENARIO_METHOD,
        "transfer_fraction_of_baoshan_base_selected_72": TRANSFER_FRACTION,
        "transfer_employment_total": int(sum(transfer_by_code.values())),
        "transfer_employment_by_subgroup": transfer_by_code,
        "priority_office_centres": list(PRIORITY_OFFICE_CENTRES),
        "composition_risk_district": COMPOSITION_RISK_DISTRICT,
        "neutral_district_count": len(neutral_districts),
        "changed_rank_row_count": int(len(changed_rank_rows)),
        "maximum_absolute_district_employment_change_from_base": int(
            max(
                district_table[
                    "low_office_intensity_difference_from_base_employment"
                ].abs().max(),
                district_table[
                    "high_office_intensity_difference_from_base_employment"
                ].abs().max(),
            )
        ),
        "selected_72_share_range_by_scenario_percentage": {
            scenario: {
                "minimum": float(
                    scenario_frames[scenario]["selected_72_share"].min()
                ),
                "maximum": float(
                    scenario_frames[scenario]["selected_72_share"].max()
                ),
            }
            for scenario in SCENARIOS
        },
        "base_matches_current_core_plus_exactly": True,
        "official_subgroup_totals_preserved_in_all_scenarios": True,
        "spatial_allocation_performed": False,
        "grid_created": False,
        "reach_percentage_calculated": False,
    }
    return subgroup_table, district_table, ranking_table, summary


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    labels = [column.replace("_", " ") for column in columns]
    output = [
        "| " + " | ".join(labels) + " |",
        "|" + "|".join("---" for _ in columns) + "|",
    ]
    for _, row in frame[columns].iterrows():
        values: list[str] = []
        for column in columns:
            value = row[column]
            if isinstance(value, float):
                values.append(f"{value:.3f}")
            else:
                values.append(str(value))
        output.append("| " + " | ".join(values) + " |")
    return "\n".join(output)


def _write_report(
    path: Path, district: pd.DataFrame, ranking: pd.DataFrame, summary: dict[str, object]
) -> None:
    district_display = district[
        [
            "district",
            "core_office_employment_hard_control",
            "low_office_intensity_core_plus_employment",
            "base_core_plus_employment",
            "high_office_intensity_core_plus_employment",
            "low_office_intensity_difference_from_base_employment",
            "high_office_intensity_difference_from_base_employment",
        ]
    ]
    rank_changes = ranking.loc[
        (ranking["employment_rank_change_from_base"] != 0)
        | (ranking["intensity_rank_change_from_base"] != 0),
        [
            "scenario_label",
            "district",
            "employment_rank",
            "employment_rank_change_from_base",
            "intensity_rank",
            "intensity_rank_change_from_base",
        ],
    ]
    report = f"""# Jinke district Core+ composition sensitivity

**Scope:** district controls only; no 100 m grid, spatial allocation, reach intersection, or reach percentage.

## Validated construction

- Core remains an immutable official hard control.
- Every scenario preserves 743,125 selected division-72 workers and total city Core+ employment of 3,220,710.
- Base exactly reproduces the current maximum-entropy district Core+ table.
- Low and High are targeted composition stresses, not estimates or confidence bounds.
- The transfer is {summary['transfer_employment_total']:,} workers, equal to 20% of Baoshan's Base selected-72 allocation, preserved subgroup by subgroup.
- The other 11 districts remain exactly at Base.
- Selected-72 shares stay within official division-72 margins: 36.909%-46.828% in Low, 39.021%-39.024% in Base after integer reconciliation, and 31.218%-41.137% in High.

## Scenario definitions

- **Low office intensity:** lower selected-72 concentration in Huangpu, Jing'an, Changning and Putuo; the conserved amount moves to Baoshan.
- **Base:** current 39.023% maximum-entropy selected-72 share.
- **High office intensity:** higher selected-72 concentration in those four central districts; the same conserved amount moves out of Baoshan.

## District scenario table

{_markdown_table(district_display, list(district_display.columns))}

## Ranking changes

Positive rank change means a district moves down relative to Base; negative means it moves up.

{_markdown_table(rank_changes, list(rank_changes.columns))}

## Validation assessment

**READY FOR FRAMEWORK REVIEW WITH CAVEATS.** The accounting constraints and targeted sensitivity behave as designed. The 20% transfer is a transparent stress amplitude, not an empirically estimated district composition interval. Core is ready as a hard control. Core+ must continue to carry scenario labels when later spatial allocation is implemented.

**STOP BEFORE 100 M GRID OR REACH CALCULATION**
"""
    path.write_text(report, encoding="utf-8")


def write_outputs(repository_root: Path) -> None:
    office_data = repository_root / "data/office_employment"
    base_subgroup_path = (
        office_data
        / "intermediate/district-business-services-subgroup-allocation-2023.csv"
    )
    base_district_path = office_data / "outputs/district-core-plus-controls-2023.csv"
    base_subgroups = pd.read_csv(base_subgroup_path, dtype={"industry_code": str})
    base_district = pd.read_csv(base_district_path)
    before_hashes = {
        str(base_subgroup_path.relative_to(repository_root)): _sha256(
            base_subgroup_path
        ),
        str(base_district_path.relative_to(repository_root)): _sha256(
            base_district_path
        ),
    }
    subgroup, district, ranking, summary = construct_core_plus_scenarios(
        base_subgroups, base_district
    )
    scenario_dir = office_data / "scenarios"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    subgroup.to_csv(
        scenario_dir / "district-business-services-subgroup-scenarios-2023.csv",
        index=False,
    )
    district.to_csv(
        scenario_dir / "district-core-plus-scenarios-2023.csv", index=False
    )
    ranking.to_csv(
        scenario_dir / "district-core-plus-ranking-changes-2023.csv", index=False
    )
    summary["unchanged_input_sha256"] = before_hashes
    (scenario_dir / "core-plus-sensitivity-summary-2023.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_report(
        scenario_dir / "core-plus-sensitivity-report.md",
        district,
        ranking,
        summary,
    )
    after_hashes = {
        str(base_subgroup_path.relative_to(repository_root)): _sha256(
            base_subgroup_path
        ),
        str(base_district_path.relative_to(repository_root)): _sha256(
            base_district_path
        ),
    }
    if before_hashes != after_hashes:
        raise RuntimeError("Scenario generation modified a frozen Core+ input.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    write_outputs(args.repository_root.resolve())


if __name__ == "__main__":
    main()
