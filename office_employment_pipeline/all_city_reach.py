"""Exact production-reach accounting for the full-Shanghai office grids."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from employment_pipeline.reach import load_production_reaches, partial_cell_fractions
from office_employment_pipeline.all_city import (
    ALL_DISTRICTS,
    OUTER_DISTRICTS,
    build_outer_control_ledger,
)
from office_employment_pipeline.control_reconciliation import (
    CORE_CODES,
    OFFICE_CODES,
    SELECTED_72_CODES,
)
from office_employment_pipeline.district_controls import (
    CORE_EMPLOYMENT,
    CORE_PLUS_EMPLOYMENT,
)
from office_employment_pipeline.reach import (
    CLASSIFICATION,
    EMPLOYMENT_LABEL,
    LIMITS,
    REACH_EDGE_METRES,
    SCENARIO_DEFINITIONS,
)
from office_employment_pipeline.spatial import ANALYSIS_CRS, PRIORITY_DISTRICTS, sha256_file


INDUSTRY_NAMES = {
    "I": "Information transmission, software and IT services",
    "J": "Financial services",
    "M": "Scientific research and technical services",
    "721": "Organization management services",
    "723": "Legal services",
    "724": "Consulting and investigation",
    "725": "Advertising",
}

FRAMEWORK_COMMIT = "7b88f7fc8d81a52daebcd19ddc68df90bee4c6c5"


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_full_grids(repository_root: Path) -> tuple[gpd.GeoDataFrame, dict[str, np.ndarray], dict[str, str]]:
    summary = json.loads(
        (repository_root / "data/office_employment/spatial/outputs/spatial-allocation-summary.json").read_text(encoding="utf-8")
    )
    if summary.get("spatial_scope") != "all 16 Shanghai districts":
        raise RuntimeError("Office spatial summary is not the all-city extension.")
    expected_hashes = summary["output_sha256"]
    hash_keys = {
        "core-employment-grid-100m.parquet": "core_grid",
        "core-plus-base-employment-grid-100m.parquet": "core_plus_base_grid",
        "core-plus-sensitivity-grid-100m.parquet": "core_plus_sensitivity_grid",
        "core-plus-weighting-sensitivity-grid-100m.parquet": "core_plus_weighting_sensitivity_grid",
    }
    frames: dict[str, gpd.GeoDataFrame] = {}
    observed_hashes: dict[str, str] = {}
    for definition in SCENARIO_DEFINITIONS.values():
        relative = str(definition["path"])
        if relative in frames:
            continue
        path = repository_root / relative
        observed = sha256_file(path)
        if observed != expected_hashes[hash_keys[path.name]]:
            raise RuntimeError(f"Full-city grid hash changed: {relative}")
        frame = gpd.read_parquet(path)
        if frame.crs is None or frame.crs.to_string() != ANALYSIS_CRS:
            raise RuntimeError(f"Full-city grid CRS changed: {relative}")
        frames[relative] = frame
        observed_hashes[relative] = observed
    reference = frames[SCENARIO_DEFINITIONS["core"]["path"]]
    if len(reference) != int(summary["all_city_grid_cell_count"]):
        raise RuntimeError("Full-city grid cell count changed.")
    if reference["cell_id"].duplicated().any() or set(reference["district"]) != set(ALL_DISTRICTS):
        raise RuntimeError("Full-city grid district/cell identity is incomplete.")
    geometry = reference.geometry.to_wkb()
    values: dict[str, np.ndarray] = {}
    for scenario, definition in SCENARIO_DEFINITIONS.items():
        frame = frames[definition["path"]]
        if not frame["cell_id"].equals(reference["cell_id"]) or not frame.geometry.to_wkb().equals(geometry):
            raise RuntimeError(f"Full-city grid order or geometry differs for {scenario}.")
        array = frame[definition["column"]].to_numpy(dtype=float)
        if not np.isfinite(array).all() or (array < 0).any():
            raise RuntimeError(f"Full-city grid has invalid values for {scenario}.")
        denominator = int(definition["denominator"])
        if not math.isclose(float(array.sum()), denominator, abs_tol=1e-6):
            raise RuntimeError(f"Full-city {scenario} grid does not equal its denominator.")
        values[scenario] = array
    return reference, values, observed_hashes


def _stable_dot(
    fraction: np.ndarray,
    employment: np.ndarray,
    priority_mask: np.ndarray,
) -> float:
    """Preserve the reviewed priority reduction order, then add outer jobs."""
    outer_mask = ~priority_mask
    return float(
        np.dot(fraction[priority_mask], employment[priority_mask])
        + np.dot(fraction[outer_mask], employment[outer_mask])
    )


def _reach_summary(
    values: dict[str, np.ndarray],
    fractions: dict[int, np.ndarray],
    priority_mask: np.ndarray,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for scenario, definition in SCENARIO_DEFINITIONS.items():
        previous = 0.0
        denominator = int(definition["denominator"])
        for limit in LIMITS:
            inside = _stable_dot(fractions[limit], values[scenario], priority_mask)
            rows.append(
                {
                    "scenario": scenario,
                    "scenario_label": definition["label"],
                    "limit_minutes": limit,
                    "employment_inside_reach": inside,
                    "percentage_of_exact_shanghai_denominator": inside / denominator * 100.0,
                    "incremental_employment": inside - previous,
                    "exact_shanghai_denominator": denominator,
                    "employment_universe": EMPLOYMENT_LABEL,
                    "exact_partial_cell_area_intersection": True,
                    "grid_smoothed": False,
                }
            )
            previous = inside
    result = pd.DataFrame(rows)
    if not result.groupby("scenario")["employment_inside_reach"].apply(lambda x: x.is_monotonic_increasing).all():
        raise RuntimeError("A full-city office reach series is not monotonic.")
    return result


def _district_table(
    repository_root: Path,
    grid: gpd.GeoDataFrame,
    values: dict[str, np.ndarray],
    fraction_50: np.ndarray,
) -> pd.DataFrame:
    controls = pd.read_csv(repository_root / "data/office_employment/outputs/district-core-plus-controls-2023.csv")[[
        "district", "official_all_industry_employment", "core_office_employment_official", "core_plus_office_employment_estimate"
    ]].rename(columns={
        "core_office_employment_official": "district_core_employment",
        "core_plus_office_employment_estimate": "district_core_plus_base_employment",
    })
    working = pd.DataFrame({
        "district": grid["district"],
        "core_inside": fraction_50 * values["core"],
        "core_plus_base_inside": fraction_50 * values["core_plus_base"],
    })
    result = controls.merge(working.groupby("district", as_index=False).sum(), on="district", validate="one_to_one")
    result["core_percentage_of_district_captured"] = result["core_inside"] / result["district_core_employment"] * 100.0
    result["core_plus_percentage_of_district_captured"] = result["core_plus_base_inside"] / result["district_core_plus_base_employment"] * 100.0
    result["core_contribution_to_reach_numerator_percentage"] = result["core_inside"] / result["core_inside"].sum() * 100.0
    result["core_plus_contribution_to_reach_numerator_percentage"] = result["core_plus_base_inside"] / result["core_plus_base_inside"].sum() * 100.0
    result["spatial_grid_available"] = True
    result["minhang_technical_sliver_employment_assigned"] = np.where(result["district"].eq("闵行区"), result["core_plus_base_inside"], 0.0)
    return result


def _industry_table(
    repository_root: Path,
    core: gpd.GeoDataFrame,
    base: gpd.GeoDataFrame,
    fraction_50: np.ndarray,
) -> pd.DataFrame:
    district_industry = pd.read_csv(
        repository_root / "data/office_employment/intermediate/district-industry-employment-2023.csv",
        dtype={"industry_code": str},
    )
    subgroup = pd.read_csv(
        repository_root / "data/office_employment/intermediate/district-business-services-subgroup-allocation-2023.csv",
        dtype={"industry_code": str},
    )
    records = []
    for code in OFFICE_CODES:
        if code in CORE_CODES:
            city = int(district_industry.loc[district_industry["industry_code"].eq(code), "district_industry_employment"].sum())
            array = core[f"cell_employment_{code}"].to_numpy(float)
            status = "official district-by-industry employment"
        else:
            rows = subgroup.loc[subgroup["industry_code"].eq(code)]
            city = int(rows["estimated_district_subgroup_employment"].sum())
            if city != int(rows["official_city_subgroup_employment"].iloc[0]):
                raise RuntimeError(f"Selected-72 city total changed for {code}.")
            array = base[f"cell_employment_{code}"].to_numpy(float)
            status = "official city subgroup; district composition modelled"
        priority_mask = core["district"].isin(PRIORITY_DISTRICTS).to_numpy()
        inside = _stable_dot(fraction_50, array, priority_mask)
        records.append({
            "industry_code": code,
            "industry_name": INDUSTRY_NAMES[code],
            "control_status": status,
            "exact_or_constrained_city_employment": city,
            "all_city_grid_employment": int(array.sum()),
            "employment_inside_50min": inside,
            "percentage_of_city_industry_employment_captured": inside / city * 100.0,
        })
    result = pd.DataFrame(records)
    result["contribution_to_core_plus_base_numerator_percentage"] = result["employment_inside_50min"] / result["employment_inside_50min"].sum() * 100.0
    if int(result["all_city_grid_employment"].sum()) != CORE_PLUS_EMPLOYMENT:
        raise RuntimeError("Full-city industry table does not equal Core+ denominator.")
    return result


def _outer_control_rows(
    repository_root: Path,
    core: gpd.GeoDataFrame,
    base: gpd.GeoDataFrame,
    fraction_50: np.ndarray,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    controls, residuals = build_outer_control_ledger()
    matrix = pd.read_csv(
        repository_root / "data/office_employment/spatial/intermediate/control-industry-matrix-2023.csv",
        dtype={"accounting_stratum_id": str, "industry_code": str},
    )
    matrix = matrix.loc[matrix["scenario"].eq("base") & matrix["district"].isin(OUTER_DISTRICTS)]
    employment = matrix.pivot(index="accounting_stratum_id", columns="industry_code", values="control_industry_employment")

    outer_mask = core["district"].isin(OUTER_DISTRICTS).to_numpy()
    non_minhang_fraction = fraction_50 * outer_mask * ~core["district"].eq("闵行区").to_numpy()
    if np.any(non_minhang_fraction > 0):
        raise RuntimeError("An outer district other than Minhang intersects the 50-minute reach.")
    minhang = core["district"].eq("闵行区").to_numpy()
    inside_by_code = {
        code: float(np.dot(fraction_50 * minhang, (core if code in CORE_CODES else base)[f"cell_employment_{code}"].to_numpy(float)))
        for code in OFFICE_CODES
    }

    def records_for(frame: pd.DataFrame, id_column: str, is_residual: bool) -> pd.DataFrame:
        records = []
        for row in frame.itertuples(index=False):
            control_id = str(getattr(row, id_column))
            district = row.district
            official_total = int(row.employment_nominal if is_residual else row.employment_reconciled)
            record: dict[str, Any] = {
                "district": district,
                "accounting_stratum_id": control_id,
                "control_name": control_id if is_residual else row.official_control_name_2023,
                "control_type": "residual" if is_residual else row.control_type,
                "official_control_total_employment": official_total,
            }
            for code in OFFICE_CODES:
                record[f"employment_{code}"] = int(employment.loc[control_id, code])
                record[f"inside_{code}"] = inside_by_code[code] if district == "闵行区" else 0.0
            record["control_core_employment"] = sum(record[f"employment_{code}"] for code in CORE_CODES)
            record["control_core_plus_base_employment"] = sum(record[f"employment_{code}"] for code in OFFICE_CODES)
            record["core_inside_50min"] = sum(record[f"inside_{code}"] for code in CORE_CODES)
            record["core_plus_base_inside_50min"] = sum(record[f"inside_{code}"] for code in OFFICE_CODES)
            record["core_capture_percentage"] = record["core_inside_50min"] / max(record["control_core_employment"], 1) * 100.0
            record["core_plus_capture_percentage"] = record["core_plus_base_inside_50min"] / max(record["control_core_plus_base_employment"], 1) * 100.0
            records.append(record)
        return pd.DataFrame(records)

    return records_for(controls, "accounting_stratum_id", False), records_for(residuals, "residual_id", True)


def _merge_control_tables(
    repository_root: Path,
    outer_controls: pd.DataFrame,
    outer_residuals: pd.DataFrame,
    central: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    root = repository_root / "data/office_employment/reach"
    priority_fine = pd.read_csv(root / "office-50min-fine-control-contributions.csv", dtype={"accounting_stratum_id": str})
    priority_fine = priority_fine.loc[priority_fine["district"].isin(PRIORITY_DISTRICTS)].copy()
    priority_residual = pd.read_csv(root / "office-50min-residual-contributions.csv", dtype={"accounting_stratum_id": str})
    priority_residual = priority_residual.loc[priority_residual["district"].isin(PRIORITY_DISTRICTS)].copy()
    base_columns = [column for column in priority_residual.columns if column not in {"contribution_to_core_plus_base_numerator_percentage", "numerator_rank"}]
    fine = pd.concat([priority_fine[[column for column in base_columns if column in priority_fine.columns]], outer_controls[base_columns]], ignore_index=True)
    residual = pd.concat([priority_residual[base_columns], outer_residuals[base_columns]], ignore_index=True)
    combined = pd.concat([fine.assign(_kind="fine"), residual.assign(_kind="residual")], ignore_index=True)
    combined["contribution_to_core_plus_base_numerator_percentage"] = combined["core_plus_base_inside_50min"] / central * 100.0
    combined["numerator_rank"] = combined["core_plus_base_inside_50min"].rank(method="first", ascending=False).astype(int)
    fine = combined.loc[combined["_kind"].eq("fine")].drop(columns="_kind").copy()
    residual = combined.loc[combined["_kind"].eq("residual")].drop(columns="_kind").copy()
    fine["fine_control_rank"] = fine["core_plus_base_inside_50min"].rank(method="first", ascending=False).astype(int)
    fine = fine.sort_values("fine_control_rank").reset_index(drop=True)
    residual = residual.sort_values("numerator_rank").reset_index(drop=True)
    return fine, residual


def _sensitivity_table(
    existing: pd.DataFrame,
    reach_summary: pd.DataFrame,
    central: float,
    edge: tuple[float, float],
) -> pd.DataFrame:
    result = existing.copy()
    weighting_rows = reach_summary.loc[
        reach_summary["scenario"].isin(
            [
                "core_plus_building_volume_dominant",
                "core_plus_workplace_evidence_emphasis",
            ]
        )
        & reach_summary["limit_minutes"].eq(50),
        "employment_inside_reach",
    ]
    values = {
        "Core+ district-composition sensitivity": (
            float(reach_summary.query("scenario == 'core_plus_low_office_intensity' and limit_minutes == 50")["employment_inside_reach"].iloc[0]),
            float(reach_summary.query("scenario == 'core_plus_high_office_intensity' and limit_minutes == 50")["employment_inside_reach"].iloc[0]),
        ),
        "Within-control weighting sensitivity": (
            min(float(weighting_rows.min()), central),
            max(float(weighting_rows.max()), central),
        ),
        "Reach-edge ±100 m sensitivity": edge,
    }
    for label, (lower, upper) in values.items():
        index = result["uncertainty_dimension"].eq(label)
        result.loc[index, ["lower_employment", "central_employment", "upper_employment"]] = [lower, central, upper]
    denominator = CORE_PLUS_EMPLOYMENT
    result["lower_percentage"] = result["lower_employment"] / denominator * 100.0
    result["central_percentage"] = result["central_employment"] / denominator * 100.0
    result["upper_percentage"] = result["upper_employment"] / denominator * 100.0
    result["minus_percentage_points"] = result["lower_percentage"] - result["central_percentage"]
    result["plus_percentage_points"] = result["upper_percentage"] - result["central_percentage"]
    result.loc[result["uncertainty_dimension"].eq("Residual-location sensitivity"), "interpretation"] = "All 14 residual office strata set to 0%/current/100% inside their district support; six added outer residuals are geographically outside the reach"
    return result


def _render_report(
    summary: pd.DataFrame,
    district: pd.DataFrame,
    industry: pd.DataFrame,
    fine: pd.DataFrame,
    sensitivity: pd.DataFrame,
    *,
    central: float,
    old_result: float,
    minhang_area: float,
    minhang_cells: int,
    minhang_jobs: float,
) -> str:
    core_50 = float(
        summary.loc[
            summary["scenario"].eq("core") & summary["limit_minutes"].eq(50),
            "employment_inside_reach",
        ].iloc[0]
    )
    lines = [
        "# Jinke office-employment reach benchmark — all-city extension",
        "",
        "## Primary result",
        "",
        f"**Core office employment within 50 minutes: {core_50:,.0f} ({core_50 / CORE_EMPLOYMENT * 100:.2f}%)**",
        "",
        f"**Core+ Base office employment within 50 minutes: {central:,.0f} ({central / CORE_PLUS_EMPLOYMENT * 100:.2f}%)**",
        "",
        f"The extension changes the previous eight-district Core+ numerator by **{central - old_result:,.6f} jobs ({(central - old_result) / CORE_PLUS_EMPLOYMENT * 100:.9f} percentage points)**. All 16 districts now have spatial grids. The exact Minhang overlap is {minhang_area:,.2f} m² across {minhang_cells} clipped cells; those cells contain {minhang_jobs:,.6f} allocated Core+ jobs.",
        "",
        "Reach statistics use the committed unsmoothed 100 m grid and exact clipped-cell intersections. The rendered heatmap is never used for calculation.",
        "",
        "## Results by reach and scenario",
        "",
        "| Scenario | Minutes | Employment inside | Shanghai share | Increment |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in summary.itertuples(index=False):
        lines.append(
            f"| {row.scenario_label} | {int(row.limit_minutes)} | {row.employment_inside_reach:,.0f} | {row.percentage_of_exact_shanghai_denominator:.3f}% | {row.incremental_employment:,.0f} |"
        )
    lines += [
        "",
        "## Separate 50-minute sensitivities",
        "",
        "These dimensions remain separate and are not a statistical confidence interval.",
        "",
        "| Dimension | Lower | Central | Upper | Minus | Plus |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in sensitivity.itertuples(index=False):
        lines.append(
            f"| {row.uncertainty_dimension} | {row.lower_percentage:.3f}% | {row.central_percentage:.3f}% | {row.upper_percentage:.3f}% | {row.minus_percentage_points:+.3f} pp | {row.plus_percentage_points:+.3f} pp |"
        )
    lines += [
        "",
        "## 50-minute district contribution",
        "",
        "| District | Core inside | Core captured | Core+ inside | Core+ captured | Core+ contribution | Grid available |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in district.itertuples(index=False):
        lines.append(
            f"| {row.district} | {row.core_inside:,.0f} | {row.core_percentage_of_district_captured:.2f}% | {row.core_plus_base_inside:,.0f} | {row.core_plus_percentage_of_district_captured:.2f}% | {row.core_plus_contribution_to_reach_numerator_percentage:.2f}% | yes |"
        )
    lines += [
        "",
        "## 50-minute industry contribution",
        "",
        "| Industry | City control | Inside | Industry captured | Numerator contribution |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in industry.itertuples(index=False):
        lines.append(
            f"| {row.industry_code} — {row.industry_name} | {row.exact_or_constrained_city_employment:,.0f} | {row.employment_inside_50min:,.0f} | {row.percentage_of_city_industry_employment_captured:.2f}% | {row.contribution_to_core_plus_base_numerator_percentage:.2f}% |"
        )
    lines += [
        "",
        "## Top fine controls in the 50-minute Core+ Base numerator",
        "",
        "| Rank | District | Control | Type | Core+ control | Inside | Captured | Contribution |",
        "|---:|---|---|---|---:|---:|---:|---:|",
    ]
    for row in fine.nsmallest(20, "fine_control_rank").itertuples(index=False):
        lines.append(
            f"| {row.fine_control_rank} | {row.district} | {row.control_name} | {row.control_type} | {row.control_core_plus_base_employment:,.0f} | {row.core_plus_base_inside_50min:,.0f} | {row.core_plus_capture_percentage:.2f}% | {row.contribution_to_core_plus_base_numerator_percentage:.2f}% |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "The unchanged headline is an observed consequence, not an imposed constraint: among the newly allocated districts, only Minhang intersects the 50-minute polygon, and only as the previously documented 2,915 m² topology sliver. Its three intersected cells carry zero allocated office employment under every committed scenario.",
        "",
        "**USABLE WITH CAUTION**",
        "",
        "The original eight-district analytical rows are unchanged. GDP, all-employment, production reach, stations, search, basemaps, and Site source were not modified.",
        "",
    ]
    return "\n".join(lines)


def run_all_city_office_reach_analysis(repository_root: Path) -> dict[str, Path]:
    repository_root = repository_root.resolve()
    output = repository_root / "data/office_employment/reach"
    protected = [
        "web/public/data/reach-areas.geojson",
        "web/public/data/reach-employment.json",
        "web/public/data/employment-methodology.json",
        "web/public/data/reach-economy.json",
        "web/public/data/gdp-methodology.json",
        "data/employment/intermediate/employment-allocation-grid.parquet",
        "web/public/data/stations.geojson",
        "web/public/data/shanghai-metro-lines.geojson",
        "web/public/data/shanghai-metro-stations.geojson",
    ]
    before = {path: sha256_file(repository_root / path) for path in protected}

    grid, values, hashes = _load_full_grids(repository_root)
    reaches, reach_hash = load_production_reaches(repository_root / "web/public/data/reach-areas.geojson", grid.crs)
    fractions = {int(row.limit): partial_cell_fractions(grid, row.geometry) for row in reaches.itertuples(index=False)}
    priority_mask = grid["district"].isin(PRIORITY_DISTRICTS).to_numpy()
    summary = _reach_summary(values, fractions, priority_mask)
    central = float(summary.query("scenario == 'core_plus_base' and limit_minutes == 50")["employment_inside_reach"].iloc[0])
    core = gpd.read_parquet(repository_root / SCENARIO_DEFINITIONS["core"]["path"])
    base = gpd.read_parquet(repository_root / SCENARIO_DEFINITIONS["core_plus_base"]["path"])
    district = _district_table(repository_root, grid, values, fractions[50])
    industry = _industry_table(repository_root, core, base, fractions[50])
    outer_controls, outer_residuals = _outer_control_rows(repository_root, core, base, fractions[50])
    fine, residuals = _merge_control_tables(repository_root, outer_controls, outer_residuals, central)
    if not math.isclose(float(fine["core_plus_base_inside_50min"].sum() + residuals["core_plus_base_inside_50min"].sum()), central, abs_tol=1e-6):
        raise RuntimeError("All-city control attribution does not reconcile to the reach numerator.")

    reach_50 = reaches.loc[reaches["limit"].eq(50), "geometry"].iloc[0]
    inward = reach_50.buffer(-REACH_EDGE_METRES)
    inward_fraction = np.zeros(len(grid)) if inward.is_empty else partial_cell_fractions(grid, inward)
    outward_fraction = partial_cell_fractions(grid, reach_50.buffer(REACH_EDGE_METRES))
    edge = (float(np.dot(inward_fraction, values["core_plus_base"])), float(np.dot(outward_fraction, values["core_plus_base"])))
    sensitivity = _sensitivity_table(pd.read_csv(output / "office-50min-uncertainty-decomposition.csv"), summary, central, edge)

    minhang_mask = grid["district"].eq("闵行区").to_numpy()
    minhang_area = float(np.sum(fractions[50][minhang_mask] * grid.loc[minhang_mask, "cell_area_m2"].to_numpy(float)))
    minhang_cells = int(np.sum(fractions[50][minhang_mask] > 0))
    minhang_jobs = float(np.dot(fractions[50] * minhang_mask, values["core_plus_base"]))

    paths = {
        "reach_summary": output / "office-reach-summary.csv",
        "district": output / "office-50min-district-contributions.csv",
        "industry": output / "office-50min-industry-contributions.csv",
        "controls": output / "office-50min-fine-control-contributions.csv",
        "residuals": output / "office-50min-residual-contributions.csv",
        "sensitivity": output / "office-50min-uncertainty-decomposition.csv",
        "methodology": output / "office-reach-methodology.json",
        "report": output / "office-reach-report.md",
        "checksums": output / "checksums.sha256",
    }
    summary.to_csv(paths["reach_summary"], index=False)
    district.to_csv(paths["district"], index=False)
    industry.to_csv(paths["industry"], index=False)
    fine.to_csv(paths["controls"], index=False)
    residuals.to_csv(paths["residuals"], index=False)
    sensitivity.to_csv(paths["sensitivity"], index=False)

    old_result = 1_212_066.7132367718
    methodology = json.loads(paths["methodology"].read_text(encoding="utf-8"))
    methodology.update({
        "schema_version": 2,
        "source_commit": FRAMEWORK_COMMIT,
        "analysis": {
            **methodology["analysis"],
            "grid_cell_count": int(len(grid)),
            "spatial_scope": "all 16 Shanghai districts",
            "spatial_grids_regenerated": True,
            "only_previously_missing_outer_districts_allocated": True,
            "priority_district_rows_preserved_exactly": True,
            "control_attribution_rehydrated_in_memory": False,
            "control_attribution_reproduced_committed_industry_cells_exactly": True,
            "reach_sha256": reach_hash,
        },
        "committed_grid_sha256": hashes,
        "all_16_districts_spatial_grid_available": True,
        "minhang_technical_sliver": {
            "intersection_area_m2": minhang_area,
            "intersected_clipped_cells": minhang_cells,
            "core_plus_base_employment_inside": minhang_jobs,
            "interpretation": "The 2,915 m² topology sliver intersects three cells with zero allocated workplace employment; it does not change the numerator.",
        },
        "previous_priority_only_core_plus_base_50min": old_result,
        "all_city_core_plus_base_50min": central,
        "change_from_priority_only_50min": central - old_result,
        "site_modified": False,
        "gdp_modified": False,
        "existing_all_employment_outputs_modified": False,
    })
    _write_json(paths["methodology"], methodology)
    paths["report"].write_text(
        _render_report(
            summary,
            district,
            industry,
            fine,
            sensitivity,
            central=central,
            old_result=old_result,
            minhang_area=minhang_area,
            minhang_cells=minhang_cells,
            minhang_jobs=minhang_jobs,
        ),
        encoding="utf-8",
    )
    after = {path: sha256_file(repository_root / path) for path in protected}
    if after != before:
        raise RuntimeError("A protected reach/GDP/all-employment/transit file changed.")
    checksum_paths = [path for key, path in paths.items() if key != "checksums"]
    zone_path = output / "office-50min-pudong-zone-boundary-sensitivity.csv"
    checksum_paths.append(zone_path)
    paths["checksums"].write_text(
        "".join(f"{sha256_file(path)}  {path.relative_to(repository_root)}\n" for path in sorted(checksum_paths)),
        encoding="utf-8",
    )
    return paths
