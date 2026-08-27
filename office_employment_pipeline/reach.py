"""Exact production-reach accounting for committed office-employment grids.

This module never fits or regenerates an office-employment surface. Aggregate
reach totals are calculated directly from the committed, unsmoothed 100 m
physical-cell grids. Control attribution is deterministically rehydrated in
memory from the frozen control-industry matrix, evidence, and supports, and is
accepted only when it reproduces every committed industry cell exactly.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from employment_pipeline.boundaries import (
    ZONE_PLANNING_AREA_KM2,
    area_matched_planning_interpretation,
    load_restricted_zone_controls,
)
from employment_pipeline.reach import load_production_reaches, partial_cell_fractions
from employment_pipeline.sensitivity import ZONE_PLAN_SOURCES
from office_employment_pipeline.control_reconciliation import (
    CORE_CODES,
    OFFICE_CODES,
    SELECTED_72_CODES,
    construct_control_industry_matrix,
)
from office_employment_pipeline.district_controls import (
    CORE_EMPLOYMENT,
    CORE_PLUS_EMPLOYMENT,
)
from office_employment_pipeline.spatial import (
    ANALYSIS_CRS,
    COMPONENT_SHARES,
    FUNCTION_COLUMNS,
    PRIORITY_DISTRICTS,
    WEIGHTING_SCENARIOS,
    allocate_integer_control_matrix,
    attach_building_evidence,
    build_control_industry_weights,
    build_control_support_cells,
    build_priority_cell_lattice,
    load_building_evidence,
    sha256_file,
)


SOURCE_COMMIT = "7b88f7fc8d81a52daebcd19ddc68df90bee4c6c5"
LIMITS = (10, 20, 30, 40, 50)
REACH_EDGE_METRES = 100.0
EMPLOYMENT_LABEL = "2023 secondary- and tertiary-sector legal-entity workplace employment"
CLASSIFICATION = "USABLE WITH CAUTION"

SCENARIO_DEFINITIONS = {
    "core": {
        "label": "Core office-oriented employment",
        "denominator": CORE_EMPLOYMENT,
        "path": "data/office_employment/spatial/outputs/core-employment-grid-100m.parquet",
        "column": "cell_employment_core",
    },
    "core_plus_base": {
        "label": "Core+ Base",
        "denominator": CORE_PLUS_EMPLOYMENT,
        "path": "data/office_employment/spatial/outputs/core-plus-base-employment-grid-100m.parquet",
        "column": "cell_employment_core_plus_base",
    },
    "core_plus_low_office_intensity": {
        "label": "Core+ Low composition",
        "denominator": CORE_PLUS_EMPLOYMENT,
        "path": "data/office_employment/spatial/outputs/core-plus-sensitivity-grid-100m.parquet",
        "column": "cell_employment_core_plus_low_office_intensity",
    },
    "core_plus_high_office_intensity": {
        "label": "Core+ High composition",
        "denominator": CORE_PLUS_EMPLOYMENT,
        "path": "data/office_employment/spatial/outputs/core-plus-sensitivity-grid-100m.parquet",
        "column": "cell_employment_core_plus_high_office_intensity",
    },
    "core_plus_building_volume_dominant": {
        "label": "Core+ building-volume-dominant weighting",
        "denominator": CORE_PLUS_EMPLOYMENT,
        "path": "data/office_employment/spatial/outputs/core-plus-weighting-sensitivity-grid-100m.parquet",
        "column": "cell_employment_core_plus_building_volume_dominant",
    },
    "core_plus_workplace_evidence_emphasis": {
        "label": "Core+ workplace-evidence-emphasis weighting",
        "denominator": CORE_PLUS_EMPLOYMENT,
        "path": "data/office_employment/spatial/outputs/core-plus-weighting-sensitivity-grid-100m.parquet",
        "column": "cell_employment_core_plus_workplace_evidence_emphasis",
    },
}


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_committed_grids(
    repository_root: Path,
) -> tuple[gpd.GeoDataFrame, dict[str, np.ndarray], dict[str, str]]:
    spatial_root = repository_root / "data/office_employment/spatial"
    spatial_summary = _json(spatial_root / "outputs/spatial-allocation-summary.json")
    expected_hashes = spatial_summary["output_sha256"]
    hash_keys = {
        "core-employment-grid-100m.parquet": "core_grid",
        "core-plus-base-employment-grid-100m.parquet": "core_plus_base_grid",
        "core-plus-sensitivity-grid-100m.parquet": "core_plus_sensitivity_grid",
        "core-plus-weighting-sensitivity-grid-100m.parquet": (
            "core_plus_weighting_sensitivity_grid"
        ),
    }
    frames: dict[str, gpd.GeoDataFrame] = {}
    observed_hashes: dict[str, str] = {}
    for definition in SCENARIO_DEFINITIONS.values():
        relative = str(definition["path"])
        if relative in frames:
            continue
        path = repository_root / relative
        observed = sha256_file(path)
        expected = expected_hashes[hash_keys[path.name]]
        if observed != expected:
            raise RuntimeError(f"Committed office grid hash changed: {relative}")
        frame = gpd.read_parquet(path)
        if frame.crs is None or frame.crs.to_string() != ANALYSIS_CRS:
            raise ValueError(f"Office grid is not in {ANALYSIS_CRS}: {relative}")
        frames[relative] = frame
        observed_hashes[relative] = observed

    reference = frames[SCENARIO_DEFINITIONS["core"]["path"]]
    if len(reference) != 172_233 or reference["cell_id"].duplicated().any():
        raise RuntimeError("Committed office lattice is not 172,233 unique cells.")
    geometry_wkb = reference.geometry.to_wkb()
    values: dict[str, np.ndarray] = {}
    for scenario, definition in SCENARIO_DEFINITIONS.items():
        frame = frames[definition["path"]]
        if not frame["cell_id"].equals(reference["cell_id"]):
            raise RuntimeError(f"Cell order changed for {scenario}.")
        if not frame.geometry.to_wkb().equals(geometry_wkb):
            raise RuntimeError(f"Cell geometry changed for {scenario}.")
        array = frame[definition["column"]].to_numpy(dtype=float)
        if not np.isfinite(array).all() or (array < 0).any():
            raise RuntimeError(f"Invalid office employment values for {scenario}.")
        values[scenario] = array

    expected_priority_totals = {
        "core": 1_852_975,
        "core_plus_base": 2_336_384,
        "core_plus_low_office_intensity": 2_323_401,
        "core_plus_high_office_intensity": 2_349_367,
        "core_plus_building_volume_dominant": 2_336_384,
        "core_plus_workplace_evidence_emphasis": 2_336_384,
    }
    for scenario, expected in expected_priority_totals.items():
        if int(values[scenario].sum()) != expected:
            raise RuntimeError(f"Priority total changed for {scenario}.")
    return reference, values, observed_hashes


def _reach_fraction_map(
    grid: gpd.GeoDataFrame, reaches: gpd.GeoDataFrame
) -> dict[int, np.ndarray]:
    return {
        int(reach.limit): partial_cell_fractions(grid, reach.geometry)
        for reach in reaches.itertuples(index=False)
    }


def _reach_summary(
    values: dict[str, np.ndarray], fractions: dict[int, np.ndarray]
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for scenario, definition in SCENARIO_DEFINITIONS.items():
        previous = 0.0
        denominator = int(definition["denominator"])
        for limit in LIMITS:
            inside = float(np.dot(fractions[limit], values[scenario]))
            records.append(
                {
                    "scenario": scenario,
                    "scenario_label": definition["label"],
                    "limit_minutes": limit,
                    "employment_inside_reach": inside,
                    "percentage_of_exact_shanghai_denominator": (
                        inside / denominator * 100.0
                    ),
                    "incremental_employment": inside - previous,
                    "exact_shanghai_denominator": denominator,
                    "employment_universe": EMPLOYMENT_LABEL,
                    "exact_partial_cell_area_intersection": True,
                    "grid_smoothed": False,
                }
            )
            previous = inside
    result = pd.DataFrame(records)
    if not result.groupby("scenario")["employment_inside_reach"].apply(
        lambda x: x.is_monotonic_increasing
    ).all():
        raise RuntimeError("An office reach series is not monotonic.")
    return result


def _district_contributions(
    repository_root: Path,
    grid: gpd.GeoDataFrame,
    values: dict[str, np.ndarray],
    fraction_50: np.ndarray,
) -> pd.DataFrame:
    controls = pd.read_csv(
        repository_root
        / "data/office_employment/outputs/district-core-plus-controls-2023.csv"
    )[
        [
            "district",
            "official_all_industry_employment",
            "core_office_employment_official",
            "core_plus_office_employment_estimate",
        ]
    ].rename(
        columns={
            "core_office_employment_official": "district_core_employment",
            "core_plus_office_employment_estimate": "district_core_plus_base_employment",
        }
    )
    if int(controls["district_core_employment"].sum()) != CORE_EMPLOYMENT:
        raise RuntimeError("District Core controls do not equal the city denominator.")
    if int(controls["district_core_plus_base_employment"].sum()) != CORE_PLUS_EMPLOYMENT:
        raise RuntimeError("District Core+ controls do not equal the city denominator.")
    working = pd.DataFrame(
        {
            "district": grid["district"],
            "core_inside": fraction_50 * values["core"],
            "core_plus_base_inside": fraction_50 * values["core_plus_base"],
        }
    )
    inside = working.groupby("district", as_index=False).sum()
    result = controls.merge(inside, on="district", how="left", validate="one_to_one")
    result[["core_inside", "core_plus_base_inside"]] = result[
        ["core_inside", "core_plus_base_inside"]
    ].fillna(0.0)
    result["core_percentage_of_district_captured"] = (
        result["core_inside"] / result["district_core_employment"] * 100.0
    )
    result["core_plus_percentage_of_district_captured"] = (
        result["core_plus_base_inside"]
        / result["district_core_plus_base_employment"]
        * 100.0
    )
    result["core_contribution_to_reach_numerator_percentage"] = (
        result["core_inside"] / float(result["core_inside"].sum()) * 100.0
    )
    result["core_plus_contribution_to_reach_numerator_percentage"] = (
        result["core_plus_base_inside"]
        / float(result["core_plus_base_inside"].sum())
        * 100.0
    )
    result["spatial_grid_available"] = result["district"].isin(PRIORITY_DISTRICTS)
    result["minhang_technical_sliver_employment_assigned"] = 0.0
    return result


def _industry_contributions(
    repository_root: Path,
    core_grid: gpd.GeoDataFrame,
    core_plus_grid: gpd.GeoDataFrame,
    fraction_50: np.ndarray,
) -> pd.DataFrame:
    district_industry = pd.read_csv(
        repository_root
        / "data/office_employment/intermediate/district-industry-employment-2023.csv",
        dtype={"industry_code": str},
    )
    subgroup = pd.read_csv(
        repository_root
        / "data/office_employment/intermediate/district-business-services-subgroup-allocation-2023.csv",
        dtype={"industry_code": str},
    )
    names = {
        "I": "Information transmission, software and IT services",
        "J": "Financial services",
        "M": "Scientific research and technical services",
        "721": "Headquarters/organization management services",
        "723": "Consulting and investigation",
        "724": "Advertising",
        "725": "Human-resources services",
    }
    records: list[dict[str, Any]] = []
    for code in OFFICE_CODES:
        if code in CORE_CODES:
            city = int(
                district_industry.loc[
                    district_industry["industry_code"].eq(code),
                    "district_industry_employment",
                ].sum()
            )
            values = core_grid[f"cell_employment_{code}"].to_numpy(dtype=float)
            status = "official district-by-industry employment"
        else:
            city_values = subgroup.loc[subgroup["industry_code"].eq(code)]
            city = int(city_values["estimated_district_subgroup_employment"].sum())
            official_city = city_values["official_city_subgroup_employment"].unique()
            if len(official_city) != 1 or city != int(official_city[0]):
                raise RuntimeError(f"Selected-72 city total does not reconcile for {code}.")
            values = core_plus_grid[f"cell_employment_{code}"].to_numpy(dtype=float)
            status = "official city subgroup; district composition modelled"
        inside = float(np.dot(fraction_50, values))
        records.append(
            {
                "industry_code": code,
                "industry_name": names[code],
                "control_status": status,
                "exact_or_constrained_city_employment": city,
                "priority_grid_employment": int(values.sum()),
                "employment_inside_50min": inside,
                "percentage_of_city_industry_employment_captured": inside / city * 100.0,
                "contribution_to_core_plus_base_numerator_percentage": 0.0,
            }
        )
    result = pd.DataFrame(records)
    total_inside = float(result["employment_inside_50min"].sum())
    result["contribution_to_core_plus_base_numerator_percentage"] = (
        result["employment_inside_50min"] / total_inside * 100.0
    )
    if int(result["exact_or_constrained_city_employment"].sum()) != CORE_PLUS_EMPLOYMENT:
        raise RuntimeError("Industry rows do not equal the Core+ city denominator.")
    return result


def _rehydrate_control_attribution(
    repository_root: Path,
    restricted_zone_directory: Path,
    committed_core: gpd.GeoDataFrame,
    committed_core_plus: gpd.GeoDataFrame,
    fraction_50: np.ndarray,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    gpd.GeoDataFrame,
    pd.DataFrame,
    dict[str, pd.Series],
]:
    general_grid = (
        repository_root / "data/employment/intermediate/employment-allocation-grid.parquet"
    )
    physical = build_priority_cell_lattice(general_grid)
    if not physical["cell_id"].equals(committed_core["cell_id"]):
        raise RuntimeError("Rehydrated physical lattice order differs from committed grids.")
    evidence = load_building_evidence(
        repository_root
        / "data/office_employment/spatial/intermediate/building-function-evidence-100m.parquet",
        physical,
    )
    physical = attach_building_evidence(physical, evidence)
    support, _ = build_control_support_cells(
        general_grid,
        physical,
        repository_root / "data/employment/manifests/control-crosswalk-2023.csv",
        repository_root / "data/employment/manifests/residual-strata.csv",
        restricted_zone_directory,
    )
    matrix = pd.read_csv(
        repository_root
        / "data/office_employment/spatial/intermediate/control-industry-matrix-2023.csv",
        dtype={"accounting_stratum_id": str, "industry_code": str},
    )
    allocations: dict[str, pd.Series] = {}
    for code in OFFICE_CODES:
        weights, _ = build_control_industry_weights(
            support, code, WEIGHTING_SCENARIOS["base"]["shares"]
        )
        totals = matrix.loc[
            matrix["scenario"].eq("base") & matrix["industry_code"].eq(code)
        ].set_index("accounting_stratum_id")["control_industry_employment"]
        allocations[code] = allocate_integer_control_matrix(support, weights, totals)

    expected = {
        **{
            code: committed_core[f"cell_employment_{code}"].to_numpy(dtype=np.int64)
            for code in CORE_CODES
        },
        **{
            code: committed_core_plus[f"cell_employment_{code}"].to_numpy(
                dtype=np.int64
            )
            for code in SELECTED_72_CODES
        },
    }
    for code, allocation in allocations.items():
        observed = (
            pd.DataFrame(
                {
                    "cell_id": support["physical_cell_id"],
                    "employment": allocation,
                }
            )
            .groupby("cell_id")["employment"]
            .sum()
            .reindex(committed_core["cell_id"], fill_value=0)
            .to_numpy(dtype=np.int64)
        )
        if not np.array_equal(observed, expected[code]):
            raise RuntimeError(
                f"Rehydrated {code} attribution does not reproduce the committed grid."
            )

    fraction_by_cell = pd.Series(fraction_50, index=committed_core["cell_id"])
    working = support[
        [
            "district",
            "accounting_stratum_id",
            "control_name",
            "control_type",
            "official_control_total_employment",
            "physical_cell_id",
        ]
    ].copy()
    working["reach_fraction_50"] = working["physical_cell_id"].map(fraction_by_cell)
    for code, allocation in allocations.items():
        working[f"employment_{code}"] = allocation.to_numpy(dtype=np.int64)
        working[f"inside_{code}"] = (
            working["reach_fraction_50"] * working[f"employment_{code}"]
        )
    keys = [
        "district",
        "accounting_stratum_id",
        "control_name",
        "control_type",
        "official_control_total_employment",
    ]
    controls = working.groupby(keys, as_index=False)[
        [
            *[f"employment_{code}" for code in OFFICE_CODES],
            *[f"inside_{code}" for code in OFFICE_CODES],
        ]
    ].sum()
    controls["control_core_employment"] = controls[
        [f"employment_{code}" for code in CORE_CODES]
    ].sum(axis=1)
    controls["control_core_plus_base_employment"] = controls[
        [f"employment_{code}" for code in OFFICE_CODES]
    ].sum(axis=1)
    controls["core_inside_50min"] = controls[
        [f"inside_{code}" for code in CORE_CODES]
    ].sum(axis=1)
    controls["core_plus_base_inside_50min"] = controls[
        [f"inside_{code}" for code in OFFICE_CODES]
    ].sum(axis=1)
    controls["core_capture_percentage"] = np.divide(
        controls["core_inside_50min"],
        controls["control_core_employment"],
        out=np.zeros(len(controls)),
        where=controls["control_core_employment"].to_numpy() > 0,
    ) * 100.0
    controls["core_plus_capture_percentage"] = np.divide(
        controls["core_plus_base_inside_50min"],
        controls["control_core_plus_base_employment"],
        out=np.zeros(len(controls)),
        where=controls["control_core_plus_base_employment"].to_numpy() > 0,
    ) * 100.0
    total_inside = float(controls["core_plus_base_inside_50min"].sum())
    controls["contribution_to_core_plus_base_numerator_percentage"] = (
        controls["core_plus_base_inside_50min"] / total_inside * 100.0
    )
    controls = controls.sort_values(
        "core_plus_base_inside_50min", ascending=False, kind="mergesort"
    ).reset_index(drop=True)
    controls["numerator_rank"] = np.arange(1, len(controls) + 1)
    fine = controls.loc[controls["control_type"].ne("residual")].copy()
    fine["fine_control_rank"] = np.arange(1, len(fine) + 1)
    residual = controls.loc[controls["control_type"].eq("residual")].copy()
    zones = controls.loc[controls["control_type"].eq("functional_zone")].copy()
    if len(fine) != 116 or len(residual) != 8 or len(zones) != 3:
        raise RuntimeError("Control attribution row counts changed.")
    return fine, residual, zones, physical, support, allocations


def _single_zone_support(
    physical: gpd.GeoDataFrame,
    zone: Any,
    geometry: Any,
) -> pd.DataFrame:
    candidates = physical.loc[
        physical["district"].eq(zone.district)
        & physical.geometry.intersects(geometry)
    ].copy()
    intersection_area = shapely.area(
        shapely.intersection(candidates.geometry.array, geometry)
    )
    candidates = candidates.loc[intersection_area > 0].copy()
    intersection_area = intersection_area[intersection_area > 0]
    candidates["physical_cell_area_m2"] = candidates["cell_area_m2"]
    candidates["support_cell_area_m2"] = intersection_area
    candidates["support_area_share_of_physical_cell"] = (
        candidates["support_cell_area_m2"] / candidates["cell_area_m2"]
    )
    evidence = [
        "jrc_nres_volume_m3",
        "poi_business_finance",
        "poi_industry_logistics",
        "poi_education_research",
        "poi_retail_hospitality",
        "poi_health_public",
        "poi_other_economic",
        "osm_office_establishment_count",
        *[f"osm_{column}_footprint_m2" for column in FUNCTION_COLUMNS],
    ]
    for column in evidence:
        candidates[column] = (
            candidates[column].astype(float)
            * candidates["support_area_share_of_physical_cell"]
        )
    candidates["physical_cell_id"] = candidates["cell_id"]
    candidates["accounting_stratum_id"] = str(zone.accounting_stratum_id)
    candidates["control_name"] = zone.official_control_name_2023
    candidates["control_type"] = "functional_zone"
    candidates["official_control_total_employment"] = int(zone.employment_reconciled)
    candidates["support_kind"] = "reported_area_morphology_sensitivity"
    candidates["restricted_geometry"] = False
    candidates["support_cell_id"] = (
        candidates["accounting_stratum_id"] + ":" + candidates["physical_cell_id"]
    )
    return candidates


def _zone_boundary_sensitivity(
    repository_root: Path,
    restricted_zone_directory: Path,
    physical: gpd.GeoDataFrame,
    fraction_50: np.ndarray,
    central_zones: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, float]]:
    crosswalk = repository_root / "data/employment/manifests/control-crosswalk-2023.csv"
    zones = load_restricted_zone_controls(restricted_zone_directory, crosswalk)
    matrix = pd.read_csv(
        repository_root
        / "data/office_employment/spatial/intermediate/control-industry-matrix-2023.csv",
        dtype={"accounting_stratum_id": str, "industry_code": str},
    )
    fraction_by_cell = pd.Series(fraction_50, index=physical["cell_id"])
    central_index = central_zones.set_index("accounting_stratum_id")
    records: list[dict[str, Any]] = []
    for zone in zones.itertuples(index=False):
        code = str(zone.accounting_stratum_id)
        alternative_geometry = area_matched_planning_interpretation(
            zone.geometry, ZONE_PLANNING_AREA_KM2[code]
        )
        support = _single_zone_support(physical, zone, alternative_geometry)
        support_fraction = support["physical_cell_id"].map(fraction_by_cell).to_numpy(
            dtype=float
        )
        alternative_inside = 0.0
        zone_core_plus = 0
        for industry in OFFICE_CODES:
            weights, _ = build_control_industry_weights(
                support, industry, WEIGHTING_SCENARIOS["base"]["shares"]
            )
            total = int(
                matrix.loc[
                    matrix["scenario"].eq("base")
                    & matrix["accounting_stratum_id"].eq(code)
                    & matrix["industry_code"].eq(industry),
                    "control_industry_employment",
                ].iloc[0]
            )
            allocation = allocate_integer_control_matrix(
                support, weights, pd.Series({code: total})
            )
            alternative_inside += float(
                np.dot(support_fraction, allocation.to_numpy(dtype=float))
            )
            zone_core_plus += total
        central_inside = float(
            central_index.loc[code, "core_plus_base_inside_50min"]
        )
        records.append(
            {
                "accounting_stratum_id": code,
                "control_name": zone.official_control_name_2023,
                "core_plus_base_zone_employment": zone_core_plus,
                "selected_2020_support_area_km2": float(zone.geometry.area / 1_000_000),
                "selected_support_employment_inside_50min": central_inside,
                "official_reported_planning_area_km2": ZONE_PLANNING_AREA_KM2[code],
                "reported_area_morphology_employment_inside_50min": alternative_inside,
                "reported_area_morphology_delta_employment": (
                    alternative_inside - central_inside
                ),
                "official_planning_source": ZONE_PLAN_SOURCES[code],
                "conservative_lower_employment_inside": 0.0,
                "conservative_upper_employment_inside": float(zone_core_plus),
                "planning_shape_is_not_official_census_geometry": True,
                "source_geometry_redistributed": False,
            }
        )
    table = pd.DataFrame(records)
    summary = {
        "selected_inside": float(table["selected_support_employment_inside_50min"].sum()),
        "planning_inside": float(
            table["reported_area_morphology_employment_inside_50min"].sum()
        ),
        "zone_total": float(table["core_plus_base_zone_employment"].sum()),
    }
    return table, summary


def _rounding_sensitivity(
    repository_root: Path,
    all_controls: pd.DataFrame,
    support: pd.DataFrame,
    physical: gpd.GeoDataFrame,
    fraction_50: np.ndarray,
    central: float,
) -> dict[str, float | str]:
    crosswalk = pd.read_csv(
        repository_root / "data/employment/manifests/control-crosswalk-2023.csv",
        dtype={"accounting_stratum_id": str},
    )
    rows = all_controls.merge(
        crosswalk[
            [
                "accounting_stratum_id",
                "employment_reconciled",
                "employment_rounding_lower",
                "employment_rounding_upper_exclusive",
            ]
        ],
        on="accounting_stratum_id",
        how="left",
        validate="one_to_one",
    )
    selected_totals: dict[str, dict[str, int]] = {"lower": {}, "upper": {}}
    for district, district_rows in rows.groupby("district"):
        residual = district_rows.loc[district_rows["control_type"].eq("residual")]
        if len(residual) != 1:
            raise RuntimeError(f"Expected one residual row for {district}.")
        residual_row = residual.iloc[0]
        residual_total = float(residual_row["official_control_total_employment"])
        residual_coefficient = (
            float(residual_row["core_plus_base_inside_50min"]) / residual_total
            if residual_total
            else 0.0
        )
        fine = district_rows.loc[district_rows["control_type"].ne("residual")]
        residual_change = {"lower": 0.0, "upper": 0.0}
        for row in fine.itertuples(index=False):
            current = float(row.employment_reconciled)
            if float(row.employment_rounding_upper_exclusive) <= float(
                row.employment_rounding_lower
            ):
                low_change = high_change = 0.0
            else:
                low_change = float(row.employment_rounding_lower) - current
                high_change = (
                    float(row.employment_rounding_upper_exclusive) - 1.0 - current
                )
            coefficient = (
                float(row.core_plus_base_inside_50min)
                / float(row.official_control_total_employment)
                - residual_coefficient
            )
            low_effect = low_change * coefficient
            high_effect = high_change * coefficient
            if low_effect <= high_effect:
                selected_totals["lower"][str(row.accounting_stratum_id)] = int(
                    current + low_change
                )
                selected_totals["upper"][str(row.accounting_stratum_id)] = int(
                    current + high_change
                )
                residual_change["lower"] -= low_change
                residual_change["upper"] -= high_change
            else:
                selected_totals["lower"][str(row.accounting_stratum_id)] = int(
                    current + high_change
                )
                selected_totals["upper"][str(row.accounting_stratum_id)] = int(
                    current + low_change
                )
                residual_change["lower"] -= high_change
                residual_change["upper"] -= low_change
        if min(residual_total + value for value in residual_change.values()) < 0:
            raise RuntimeError(f"Rounding envelope makes {district} residual negative.")
        residual_id = str(residual_row["accounting_stratum_id"])
        for direction in ("lower", "upper"):
            selected_totals[direction][residual_id] = int(
                residual_total + residual_change[direction]
            )

    fine_source = pd.read_csv(
        repository_root / "data/employment/manifests/control-crosswalk-2023.csv",
        dtype={"accounting_stratum_id": str},
    )
    residual_source = pd.read_csv(
        repository_root / "data/employment/manifests/residual-strata.csv",
        dtype={"residual_id": str},
    )
    district_industry = pd.read_csv(
        repository_root
        / "data/office_employment/intermediate/district-industry-employment-2023.csv",
        dtype={"industry_code": str},
    )
    subgroup_scenarios = pd.read_csv(
        repository_root
        / "data/office_employment/scenarios/district-business-services-subgroup-scenarios-2023.csv",
        dtype={"industry_code": str},
    )
    if not physical["cell_id"].is_unique:
        raise RuntimeError("Physical office cells are not unique.")
    fraction_by_cell = pd.Series(fraction_50, index=physical["cell_id"])
    support_fraction = support["physical_cell_id"].map(fraction_by_cell)
    if support_fraction.isna().any():
        raise RuntimeError("Rounding support does not map to the reach-fraction lattice.")

    exact_results: dict[str, float] = {}
    weight_cache: dict[str, pd.Series] = {}
    for direction in ("lower", "upper"):
        adjusted_fine = fine_source.copy()
        adjusted_fine["employment_reconciled"] = adjusted_fine.apply(
            lambda row: selected_totals[direction].get(
                str(row["accounting_stratum_id"]), int(row["employment_reconciled"])
            ),
            axis=1,
        )
        adjusted_residual = residual_source.copy()
        adjusted_residual["employment_nominal"] = adjusted_residual.apply(
            lambda row: selected_totals[direction].get(
                str(row["residual_id"]), int(row["employment_nominal"])
            ),
            axis=1,
        )
        matrix, _ = construct_control_industry_matrix(
            adjusted_fine,
            adjusted_residual,
            district_industry,
            subgroup_scenarios,
            priority_districts=PRIORITY_DISTRICTS,
        )
        inside = 0.0
        for code in OFFICE_CODES:
            if code not in weight_cache:
                weight_cache[code], _ = build_control_industry_weights(
                    support, code, WEIGHTING_SCENARIOS["base"]["shares"]
                )
            totals = matrix.loc[
                matrix["scenario"].eq("base")
                & matrix["industry_code"].eq(code)
            ].set_index("accounting_stratum_id")["control_industry_employment"]
            allocation = allocate_integer_control_matrix(
                support, weight_cache[code], totals
            )
            inside += float(
                np.dot(
                    support_fraction.to_numpy(dtype=float),
                    allocation.to_numpy(dtype=float),
                )
            )
        exact_results[direction] = inside
    lower = min(exact_results["lower"], exact_results["upper"], central)
    upper = max(exact_results["lower"], exact_results["upper"], central)
    return {
        "lower_employment": lower,
        "central_employment": central,
        "upper_employment": upper,
        "lower_delta_employment": lower - central,
        "upper_delta_employment": upper - central,
        "method": (
            "district-total-constrained directional rounding envelope; candidate "
            "fine-row extrema are selected from current reach coefficients, offset "
            "by each district residual, and passed through exact district-industry "
            "RAS/IPF plus deterministic integer allocation; the city Core+ denominator "
            "and every district-industry margin remain fixed"
        ),
    }


def _sensitivity_table(
    central: float,
    reach_summary: pd.DataFrame,
    residuals: pd.DataFrame,
    zone_summary: dict[str, float],
    edge_inside: tuple[float, float],
    rounding: dict[str, float | str],
) -> pd.DataFrame:
    fifty = reach_summary.loc[reach_summary["limit_minutes"].eq(50)].set_index(
        "scenario"
    )["employment_inside_reach"]
    residual_inside = float(residuals["core_plus_base_inside_50min"].sum())
    residual_total = float(residuals["control_core_plus_base_employment"].sum())
    non_zone = central - zone_summary["selected_inside"]
    records = [
        {
            "uncertainty_dimension": "Core+ district-composition sensitivity",
            "lower_employment": float(
                min(
                    fifty["core_plus_low_office_intensity"],
                    fifty["core_plus_high_office_intensity"],
                )
            ),
            "central_employment": central,
            "upper_employment": float(
                max(
                    fifty["core_plus_low_office_intensity"],
                    fifty["core_plus_high_office_intensity"],
                )
            ),
            "interpretation": "Low/Base/High selected-72 district composition; city denominator fixed",
        },
        {
            "uncertainty_dimension": "Within-control weighting sensitivity",
            "lower_employment": float(
                min(
                    central,
                    fifty["core_plus_building_volume_dominant"],
                    fifty["core_plus_workplace_evidence_emphasis"],
                )
            ),
            "central_employment": central,
            "upper_employment": float(
                max(
                    central,
                    fifty["core_plus_building_volume_dominant"],
                    fifty["core_plus_workplace_evidence_emphasis"],
                )
            ),
            "interpretation": "Base 60/25/10/5 compared with two declared uncapped weight cases",
        },
        {
            "uncertainty_dimension": "Residual-location sensitivity",
            "lower_employment": central - residual_inside,
            "central_employment": central,
            "upper_employment": central - residual_inside + residual_total,
            "interpretation": "All eight residual office strata set to 0%/current/100% inside",
        },
        {
            "uncertainty_dimension": "Pudong functional-zone boundary sensitivity",
            "lower_employment": non_zone,
            "central_employment": central,
            "upper_employment": non_zone + zone_summary["zone_total"],
            "interpretation": "Three zone rows set to 0%/selected support/100% inside; reported-area morphology shown separately",
        },
        {
            "uncertainty_dimension": "Reach-edge ±100 m sensitivity",
            "lower_employment": min(edge_inside),
            "central_employment": central,
            "upper_employment": max(edge_inside),
            "interpretation": "Exact base grid intersected with 50-minute polygon buffered inward/outward by 100 m",
        },
        {
            "uncertainty_dimension": "Census rounding sensitivity",
            "lower_employment": float(rounding["lower_employment"]),
            "central_employment": central,
            "upper_employment": float(rounding["upper_employment"]),
            "interpretation": str(rounding["method"]),
        },
    ]
    result = pd.DataFrame(records)
    result["lower_percentage"] = result["lower_employment"] / CORE_PLUS_EMPLOYMENT * 100
    result["central_percentage"] = central / CORE_PLUS_EMPLOYMENT * 100
    result["upper_percentage"] = result["upper_employment"] / CORE_PLUS_EMPLOYMENT * 100
    result["minus_percentage_points"] = (
        result["lower_employment"] - central
    ) / CORE_PLUS_EMPLOYMENT * 100
    result["plus_percentage_points"] = (
        result["upper_employment"] - central
    ) / CORE_PLUS_EMPLOYMENT * 100
    result["not_a_confidence_interval"] = True
    return result


def _report(
    repository_root: Path,
    reach_summary: pd.DataFrame,
    district: pd.DataFrame,
    industry: pd.DataFrame,
    fine_controls: pd.DataFrame,
    sensitivity: pd.DataFrame,
    zone: pd.DataFrame,
) -> str:
    fifty = reach_summary.loc[reach_summary["limit_minutes"].eq(50)].set_index(
        "scenario"
    )
    core = fifty.loc["core"]
    base = fifty.loc["core_plus_base"]
    all_employment = _json(repository_root / "web/public/data/reach-employment.json")
    all_share = float(
        next(
            row["percentage_of_shanghai_employment"]
            for row in all_employment["results"]
            if int(row["limit_minutes"]) == 50
        )
    )
    gdp = _json(repository_root / "web/public/data/reach-economy.json")
    gdp_share = float(
        next(
            row["percentage_of_shanghai_gdp"]
            for row in gdp
            if int(row["limit_minutes"]) == 50
        )
    )
    lines = [
        "# Jinke office-employment reach benchmark",
        "",
        "## Primary result",
        "",
        f"**Core office employment within 50 minutes: {core.employment_inside_reach:,.0f} ({core.percentage_of_exact_shanghai_denominator:.2f}%)**",
        "",
        f"**Core+ Base office employment within 50 minutes: {base.employment_inside_reach:,.0f} ({base.percentage_of_exact_shanghai_denominator:.2f}%)**",
        "",
        f"Core denominator: **{CORE_EMPLOYMENT:,}**. Core+ denominator: **{CORE_PLUS_EMPLOYMENT:,}**. Both cover {EMPLOYMENT_LABEL}; individual-business employment is excluded.",
        "",
        "The calculation uses the exact committed production polygons and exact clipped-cell intersection area divided by clipped cell area. It does not read the heatmap, smooth the grid, fit a model, or target a prior expectation.",
        "",
        "## Results by reach and scenario",
        "",
        "| Scenario | Minutes | Employment inside | Shanghai share | Increment |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in reach_summary.itertuples(index=False):
        lines.append(
            f"| {row.scenario_label} | {row.limit_minutes} | {row.employment_inside_reach:,.0f} | {row.percentage_of_exact_shanghai_denominator:.3f}% | {row.incremental_employment:,.0f} |"
        )
    lines += [
        "",
        "## Separate 50-minute sensitivities",
        "",
        "These dimensions are not added and are not a statistical confidence interval.",
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
        "The Pudong reported-area morphology interpretation changes the selected-support result by "
        f"{(zone.reported_area_morphology_delta_employment.sum() / CORE_PLUS_EMPLOYMENT * 100):+.3f} percentage points. This is a morphology diagnostic, not an official census-zone boundary.",
        "",
        "## 50-minute district contribution",
        "",
        "| District | Core inside | Core captured | Core+ inside | Core+ captured | Core+ numerator contribution |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in district.itertuples(index=False):
        lines.append(
            f"| {row.district} | {row.core_inside:,.0f} | {row.core_percentage_of_district_captured:.2f}% | {row.core_plus_base_inside:,.0f} | {row.core_plus_percentage_of_district_captured:.2f}% | {row.core_plus_contribution_to_reach_numerator_percentage:.2f}% |"
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
        "| Rank | District | Control | Type | Core+ control | Inside | Captured | Numerator contribution |",
        "|---:|---|---|---|---:|---:|---:|---:|",
    ]
    for row in fine_controls.head(20).itertuples(index=False):
        lines.append(
            f"| {row.fine_control_rank} | {row.district} | {row.control_name} | {row.control_type} | {row.control_core_plus_base_employment:,.0f} | {row.core_plus_base_inside_50min:,.0f} | {row.core_plus_capture_percentage:.2f}% | {row.contribution_to_core_plus_base_numerator_percentage:.2f}% |"
        )
    lines += [
        "",
        "## Comparison with existing benchmarks",
        "",
        f"- Core+ Base office share: **{base.percentage_of_exact_shanghai_denominator:.3f}%**",
        f"- Existing all-employment share: **{all_share:.3f}%**",
        f"- Existing GDP share: **{gdp_share:.3f}%**",
        f"- Office share / all-employment share: **{base.percentage_of_exact_shanghai_denominator / all_share:.3f}×**",
        f"- Office share / GDP share: **{base.percentage_of_exact_shanghai_denominator / gdp_share:.3f}×**",
        "",
        "The larger office share is consistent with office-oriented industries being more spatially concentrated in the central and major business/technology clusters than total legal-entity employment. It does not validate either benchmark through comparison alone.",
        "",
        "## Decision classification",
        "",
        f"**{CLASSIFICATION}**",
        "",
        "The benchmark has exact city denominators, exact district-industry controls, hard fine-geographic totals, deterministic within-control allocation, exact partial-cell geometry, and stable declared weighting alternatives. Caution remains necessary because control×industry composition is synthetic, selected division-72 district composition is partly modelled, ordinary boundaries are approximate, residual locations are not directly observed, and Pudong functional-zone scopes remain uncertain.",
        "",
        "No Site, GDP, all-employment, or production-reach output was modified. This report does not constitute a confidence interval.",
    ]
    return "\n".join(lines) + "\n"


def run_office_reach_analysis(
    repository_root: Path,
    restricted_zone_directory: Path,
) -> dict[str, Path]:
    repository_root = repository_root.resolve()
    restricted_zone_directory = restricted_zone_directory.resolve()
    output = repository_root / "data/office_employment/reach"
    output.mkdir(parents=True, exist_ok=True)

    protected = [
        "web/public/data/reach-areas.geojson",
        "web/public/data/reach-employment.json",
        "web/public/data/employment-methodology.json",
        "web/public/data/reach-economy.json",
        "web/public/data/gdp-methodology.json",
        "data/employment/intermediate/employment-allocation-grid.parquet",
    ]
    protected_before = {
        path: sha256_file(repository_root / path) for path in protected
    }

    grid, values, grid_hashes = _load_committed_grids(repository_root)
    reaches, reach_hash = load_production_reaches(
        repository_root / "web/public/data/reach-areas.geojson", grid.crs
    )
    fractions = _reach_fraction_map(grid, reaches)
    reach_summary = _reach_summary(values, fractions)

    core_grid = gpd.read_parquet(
        repository_root / SCENARIO_DEFINITIONS["core"]["path"]
    )
    core_plus_grid = gpd.read_parquet(
        repository_root / SCENARIO_DEFINITIONS["core_plus_base"]["path"]
    )
    district = _district_contributions(
        repository_root, grid, values, fractions[50]
    )
    industry = _industry_contributions(
        repository_root, core_grid, core_plus_grid, fractions[50]
    )
    fine, residuals, zones, physical, support, _ = _rehydrate_control_attribution(
        repository_root,
        restricted_zone_directory,
        core_grid,
        core_plus_grid,
        fractions[50],
    )
    central = float(
        reach_summary.loc[
            reach_summary["scenario"].eq("core_plus_base")
            & reach_summary["limit_minutes"].eq(50),
            "employment_inside_reach",
        ].iloc[0]
    )
    if not math.isclose(
        float(fine["core_plus_base_inside_50min"].sum())
        + float(residuals["core_plus_base_inside_50min"].sum()),
        central,
        abs_tol=1e-6,
    ):
        raise RuntimeError("Control attribution does not reconcile to the 50-minute total.")

    zone_table, zone_summary = _zone_boundary_sensitivity(
        repository_root,
        restricted_zone_directory,
        physical,
        fractions[50],
        zones,
    )
    reach_50 = reaches.loc[reaches["limit"].eq(50), "geometry"].iloc[0]
    inward = reach_50.buffer(-REACH_EDGE_METRES)
    outward = reach_50.buffer(REACH_EDGE_METRES)
    inward_fraction = (
        np.zeros(len(grid))
        if inward.is_empty
        else partial_cell_fractions(grid, inward)
    )
    outward_fraction = partial_cell_fractions(grid, outward)
    edge = (
        float(np.dot(inward_fraction, values["core_plus_base"])),
        float(np.dot(outward_fraction, values["core_plus_base"])),
    )
    all_controls = pd.concat([fine, residuals], ignore_index=True)
    rounding = _rounding_sensitivity(
        repository_root,
        all_controls,
        support,
        physical,
        fractions[50],
        central,
    )
    sensitivity = _sensitivity_table(
        central, reach_summary, residuals, zone_summary, edge, rounding
    )

    paths = {
        "reach_summary": output / "office-reach-summary.csv",
        "district": output / "office-50min-district-contributions.csv",
        "industry": output / "office-50min-industry-contributions.csv",
        "controls": output / "office-50min-fine-control-contributions.csv",
        "residuals": output / "office-50min-residual-contributions.csv",
        "zones": output / "office-50min-pudong-zone-boundary-sensitivity.csv",
        "sensitivity": output / "office-50min-uncertainty-decomposition.csv",
        "methodology": output / "office-reach-methodology.json",
        "report": output / "office-reach-report.md",
        "checksums": output / "checksums.sha256",
    }
    reach_summary.to_csv(paths["reach_summary"], index=False)
    district.to_csv(paths["district"], index=False)
    industry.to_csv(paths["industry"], index=False)
    fine.to_csv(paths["controls"], index=False)
    residuals.to_csv(paths["residuals"], index=False)
    zone_table.to_csv(paths["zones"], index=False)
    sensitivity.to_csv(paths["sensitivity"], index=False)

    all_employment = _json(repository_root / "web/public/data/reach-employment.json")
    all_share = float(
        next(
            row["percentage_of_shanghai_employment"]
            for row in all_employment["results"]
            if int(row["limit_minutes"]) == 50
        )
    )
    gdp = _json(repository_root / "web/public/data/reach-economy.json")
    gdp_share = float(
        next(
            row["percentage_of_shanghai_gdp"]
            for row in gdp
            if int(row["limit_minutes"]) == 50
        )
    )
    methodology = {
        "schema_version": 1,
        "source_commit": SOURCE_COMMIT,
        "reference_date": "2023-12-31",
        "employment_universe": EMPLOYMENT_LABEL,
        "individual_business_employment_included": False,
        "denominators": {
            "core": CORE_EMPLOYMENT,
            "core_plus_each_scenario": CORE_PLUS_EMPLOYMENT,
        },
        "analysis": {
            "crs": ANALYSIS_CRS,
            "grid_metres": 100,
            "grid_smoothed": False,
            "partial_cell_method": "area(cell intersection reach) / clipped cell_area_m2",
            "rendered_heatmap_used": False,
            "spatial_model_refit": False,
            "spatial_grids_regenerated": False,
            "control_attribution_rehydrated_in_memory": True,
            "control_attribution_reproduced_committed_industry_cells_exactly": True,
            "production_reach_modified": False,
            "reach_sha256": reach_hash,
        },
        "committed_grid_sha256": grid_hashes,
        "uncertainty_dimensions_are_separate": True,
        "uncertainty_is_statistical_confidence_interval": False,
        "rounding_method": rounding["method"],
        "pudong_functional_zones": {
            "selected_support": "hash-pinned approximate 2020 statistical polygons",
            "reported_area_sensitivity": "area-matched morphology; not official census geometry",
            "source_geometry_redistributed": False,
        },
        "comparators": {
            "all_employment_50min_percentage": all_share,
            "gdp_50min_percentage": gdp_share,
        },
        "classification": CLASSIFICATION,
        "site_modified": False,
        "gdp_modified": False,
        "existing_all_employment_outputs_modified": False,
    }
    _write_json(paths["methodology"], methodology)
    paths["report"].write_text(
        _report(
            repository_root,
            reach_summary,
            district,
            industry,
            fine,
            sensitivity,
            zone_table,
        ),
        encoding="utf-8",
    )

    protected_after = {
        path: sha256_file(repository_root / path) for path in protected
    }
    if protected_after != protected_before:
        raise RuntimeError("A protected GDP, reach, or all-employment file changed.")
    checksum_paths = [path for key, path in paths.items() if key != "checksums"]
    paths["checksums"].write_text(
        "".join(
            f"{sha256_file(path)}  {path.relative_to(repository_root)}\n"
            for path in sorted(checksum_paths)
        ),
        encoding="utf-8",
    )
    return paths
