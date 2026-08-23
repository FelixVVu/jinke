"""Rule-based 100 m office-employment allocation without reach calculation.

The allocation uses exact district-by-industry census controls for Core
(I + J + M) and the already-reviewed district Core+ composition scenarios.
It deliberately does not fit PPML or another generic employment-prediction
model.  Raw JRC non-residential volume remains the primary magnitude signal;
OSM building function and office tags refine workplace type; Overture Places
is a small supplementary component.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely

from office_employment_pipeline.district_controls import (
    CORE_EMPLOYMENT,
    CORE_PLUS_EMPLOYMENT,
    CORE_PLUS_CODES,
)
from office_employment_pipeline.source_audit import (
    EMPLOYMENT_UNIVERSE,
    REFERENCE_DATE,
)


ANALYSIS_CRS = "EPSG:32651"
GRID_SIZE_METRES = 100
PRIORITY_DISTRICTS = (
    "黄浦区",
    "徐汇区",
    "长宁区",
    "静安区",
    "普陀区",
    "虹口区",
    "杨浦区",
    "浦东新区",
)
CORE_CODES = ("I", "J", "M")
SCENARIOS = ("low_office_intensity", "base", "high_office_intensity")

OSM_BUILDING_SOURCE_URL = (
    "https://download.openstreetmap.fr/extracts/asia/china/shanghai.osm.pbf"
)
OSM_BUILDING_SNAPSHOT_DATE = "2026-08-23"
OSM_BUILDING_SHA256 = (
    "3b6e8bb207db37e6d86546c8e73fcfb3a68b8b6c744f74ed1d5d645bc7873099"
)
OSM_LICENSE = "OpenStreetMap contributors, Open Database License 1.0"
OSM_ATTRIBUTION_URL = "https://www.openstreetmap.org/copyright"

GENERAL_GRID_SHA256 = (
    "12de4bd6c3f8df26c7702f1a4ff0f6aed797068d3f571a6ccabdd6b5f6f8c1b7"
)
DISTRICT_INDUSTRY_SHA256 = (
    "c791c1a8e0cea282201fd1d3303493ee5e82cfb411a627946c6c95fafa0d7cd9"
)
CORE_PLUS_SCENARIO_SHA256 = (
    "e410728f2bdbec3a5cad5c1a37e5d3af91cdfe3f8742189a9932ca5ad1217306"
)

FUNCTION_COLUMNS = (
    "office_business",
    "research_technical",
    "industrial_logistics",
    "retail_hospitality",
    "health_public",
    "other_nonres",
)

# Raw evidence is combined only after each component is normalized within the
# district hard control.  No component is logged, capped, winsorized, or
# min-max transformed, so economically meaningful upper tails are retained.
COMPONENT_SHARES = {
    "jrc_nonresidential_volume": 0.60,
    "osm_building_function_footprint": 0.25,
    "osm_office_establishments": 0.10,
    "overture_poi_supplement": 0.05,
}

FUNCTION_RELEVANCE = {
    "I": {
        "office_business": 1.00,
        "research_technical": 1.00,
        "industrial_logistics": 0.35,
        "retail_hospitality": 0.10,
        "health_public": 0.10,
        "other_nonres": 0.25,
    },
    "J": {
        "office_business": 1.00,
        "research_technical": 0.10,
        "industrial_logistics": 0.05,
        "retail_hospitality": 0.25,
        "health_public": 0.10,
        "other_nonres": 0.10,
    },
    "M": {
        "office_business": 0.70,
        "research_technical": 1.00,
        "industrial_logistics": 0.45,
        "retail_hospitality": 0.10,
        "health_public": 0.20,
        "other_nonres": 0.25,
    },
    "721": {
        "office_business": 1.00,
        "research_technical": 0.35,
        "industrial_logistics": 0.15,
        "retail_hospitality": 0.25,
        "health_public": 0.10,
        "other_nonres": 0.20,
    },
    "723": {
        "office_business": 1.00,
        "research_technical": 0.15,
        "industrial_logistics": 0.05,
        "retail_hospitality": 0.15,
        "health_public": 0.10,
        "other_nonres": 0.10,
    },
    "724": {
        "office_business": 0.90,
        "research_technical": 0.85,
        "industrial_logistics": 0.25,
        "retail_hospitality": 0.15,
        "health_public": 0.15,
        "other_nonres": 0.20,
    },
    "725": {
        "office_business": 0.90,
        "research_technical": 0.35,
        "industrial_logistics": 0.10,
        "retail_hospitality": 0.50,
        "health_public": 0.10,
        "other_nonres": 0.20,
    },
}

POI_RELEVANCE = {
    "I": {
        "poi_business_finance": 0.70,
        "poi_industry_logistics": 0.20,
        "poi_education_research": 1.00,
        "poi_retail_hospitality": 0.05,
        "poi_health_public": 0.05,
        "poi_other_economic": 0.30,
    },
    "J": {
        "poi_business_finance": 1.00,
        "poi_industry_logistics": 0.00,
        "poi_education_research": 0.05,
        "poi_retail_hospitality": 0.10,
        "poi_health_public": 0.00,
        "poi_other_economic": 0.10,
    },
    "M": {
        "poi_business_finance": 0.40,
        "poi_industry_logistics": 0.40,
        "poi_education_research": 1.00,
        "poi_retail_hospitality": 0.05,
        "poi_health_public": 0.10,
        "poi_other_economic": 0.20,
    },
    "721": {
        "poi_business_finance": 1.00,
        "poi_industry_logistics": 0.10,
        "poi_education_research": 0.20,
        "poi_retail_hospitality": 0.15,
        "poi_health_public": 0.05,
        "poi_other_economic": 0.25,
    },
    "723": {
        "poi_business_finance": 1.00,
        "poi_industry_logistics": 0.00,
        "poi_education_research": 0.10,
        "poi_retail_hospitality": 0.05,
        "poi_health_public": 0.05,
        "poi_other_economic": 0.20,
    },
    "724": {
        "poi_business_finance": 1.00,
        "poi_industry_logistics": 0.15,
        "poi_education_research": 0.50,
        "poi_retail_hospitality": 0.05,
        "poi_health_public": 0.10,
        "poi_other_economic": 0.25,
    },
    "725": {
        "poi_business_finance": 0.80,
        "poi_industry_logistics": 0.05,
        "poi_education_research": 0.20,
        "poi_retail_hospitality": 0.60,
        "poi_health_public": 0.00,
        "poi_other_economic": 0.40,
    },
}

RESIDENTIAL_BUILDINGS = {
    "apartments",
    "house",
    "residential",
    "terrace",
    "semidetached_house",
    "dormitory",
    "detached",
    "bungalow",
    "static_caravan",
    "cabin",
}
NON_WORKPLACE_BUILDINGS = {
    "roof",
    "garage",
    "garages",
    "shed",
    "carport",
    "greenhouse",
    "storage_tank",
    "construction",
    "ruins",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_hash(path: Path, expected: str, label: str) -> None:
    observed = sha256_file(path)
    if observed != expected:
        raise RuntimeError(f"{label} hash changed: {observed}; expected {expected}.")


def build_priority_cell_lattice(general_grid_path: Path) -> gpd.GeoDataFrame:
    """Dissolve audited street/town fragments to one physical 100 m cell."""

    _require_hash(general_grid_path, GENERAL_GRID_SHA256, "General employment grid")
    source = gpd.read_parquet(general_grid_path)
    if source.crs is None or source.crs.to_string() != ANALYSIS_CRS:
        raise ValueError(f"General employment grid must use {ANALYSIS_CRS}.")
    source = source.loc[
        source["control_type"].isin(["street", "town"])
        & source["geometry"].notna()
        & source["district"].isin(PRIORITY_DISTRICTS)
    ].copy()
    numeric = [
        "cell_area_m2",
        "jrc_nres_volume_m3",
        "poi_business_finance",
        "poi_industry_logistics",
        "poi_education_research",
        "poi_retail_hospitality",
        "poi_health_public",
        "poi_other_economic",
    ]
    keys = ["district", "grid_row", "grid_col"]
    aggregates = source.groupby(keys, sort=False, as_index=False)[numeric].sum()
    geometry = source[keys + ["geometry"]].dissolve(by=keys, as_index=False)
    cells = gpd.GeoDataFrame(
        aggregates.merge(geometry, on=keys, validate="one_to_one"),
        geometry="geometry",
        crs=source.crs,
    )
    cells["grid_row"] = cells["grid_row"].astype(np.int32)
    cells["grid_col"] = cells["grid_col"].astype(np.int32)
    cells["center_x"] = (cells["grid_col"].astype(float) + 0.5) * GRID_SIZE_METRES
    cells["center_y"] = (cells["grid_row"].astype(float) + 0.5) * GRID_SIZE_METRES
    cells["area_fraction"] = cells["cell_area_m2"] / float(
        GRID_SIZE_METRES**2
    )
    cells["cell_id"] = (
        cells["district"]
        + ":"
        + cells["grid_row"].astype(str)
        + ":"
        + cells["grid_col"].astype(str)
    )
    district_order = {name: index for index, name in enumerate(PRIORITY_DISTRICTS)}
    cells["_district_order"] = cells["district"].map(district_order)
    cells = cells.sort_values(
        ["_district_order", "grid_row", "grid_col"], kind="mergesort"
    ).drop(columns="_district_order")
    cells = cells.reset_index(drop=True)
    if cells["cell_id"].duplicated().any():
        raise RuntimeError("Physical 100 m cell IDs are not unique.")
    if cells.geometry.is_empty.any() or not cells.geometry.is_valid.all():
        raise RuntimeError("Physical 100 m lattice contains invalid geometry.")
    if (cells["cell_area_m2"] <= 0).any() or (
        cells["cell_area_m2"] > GRID_SIZE_METRES**2 + 1e-6
    ).any():
        raise RuntimeError("Physical cell areas fall outside 0-10,000 m2.")
    if set(cells["district"]) != set(PRIORITY_DISTRICTS):
        raise RuntimeError("Physical grid does not contain all eight priority districts.")
    return cells


def _building_function(row: pd.Series) -> str | None:
    building = row["building_norm"]
    office = row["office_norm"]
    amenity = row["amenity_norm"]
    landuse = row["landuse_norm"]
    shop = row["shop_norm"]
    tourism = row["tourism_norm"]
    if office in {"research", "educational_institution"} or building in {
        "university",
        "college",
        "school",
        "kindergarten",
    }:
        return "research_technical"
    if office or building in {"office", "commercial"}:
        return "office_business"
    if building in {"industrial", "warehouse", "hangar"} or landuse in {
        "industrial",
        "railway",
    }:
        return "industrial_logistics"
    if building in {"retail", "hotel", "kiosk", "supermarket"} or shop or tourism in {
        "hotel",
        "hostel",
        "motel",
    }:
        return "retail_hospitality"
    if building in {"hospital", "civic", "government", "public"} or amenity in {
        "hospital",
        "clinic",
        "police",
        "fire_station",
        "townhall",
        "courthouse",
    }:
        return "health_public"
    if building in RESIDENTIAL_BUILDINGS or building in NON_WORKPLACE_BUILDINGS:
        return None
    if building and building != "yes":
        return "other_nonres"
    return None


def extract_building_evidence(
    osm_pbf_path: Path,
    cells: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Aggregate OSM building function and office tags to physical 100 m cells."""

    _require_hash(osm_pbf_path, OSM_BUILDING_SHA256, "OSM building snapshot")
    bbox = tuple(float(value) for value in cells.to_crs("EPSG:4326").total_bounds)
    columns = [
        "osm_id",
        "osm_way_id",
        "name",
        "amenity",
        "building",
        "landuse",
        "office",
        "shop",
        "tourism",
        "other_tags",
    ]
    buildings = pyogrio.read_dataframe(
        osm_pbf_path,
        layer="multipolygons",
        columns=columns,
        bbox=bbox,
    )
    raw_feature_count = len(buildings)
    buildings = buildings.loc[
        buildings["building"].notna() | buildings["office"].notna()
    ].copy()
    building_candidate_count = len(buildings)
    for column in ("building", "office", "amenity", "landuse", "shop", "tourism"):
        buildings[f"{column}_norm"] = (
            buildings[column].fillna("").astype(str).str.strip().str.lower()
        )
    buildings["building_function"] = buildings.apply(_building_function, axis=1)
    buildings["office_establishment_anchor"] = buildings["office_norm"].ne("")
    levels = buildings["other_tags"].fillna("").str.extract(
        r'"building:levels"=>"([0-9]+(?:\.[0-9]+)?)"', expand=False
    )
    buildings["levels_known"] = pd.to_numeric(levels, errors="coerce").between(
        1, 100, inclusive="both"
    )
    classified = buildings.loc[buildings["building_function"].notna()].copy()
    invalid_before_repair = int(
        (~classified.geometry.is_valid | classified.geometry.is_empty).sum()
    )
    classified["geometry"] = shapely.make_valid(classified.geometry.array)
    classified = classified.loc[
        classified.geometry.notna() & ~classified.geometry.is_empty
    ].to_crs(cells.crs)

    cell_geometry = cells.set_index("cell_id")["geometry"]
    joined = gpd.sjoin(
        classified[
            [
                "osm_id",
                "osm_way_id",
                "building_function",
                "office_establishment_anchor",
                "levels_known",
                "geometry",
            ]
        ],
        cells[["cell_id", "geometry"]],
        how="inner",
        predicate="intersects",
    ).drop(columns="index_right")
    joined["cell_geometry"] = joined["cell_id"].map(cell_geometry)
    intersections = shapely.intersection(
        joined.geometry.array,
        gpd.GeoSeries(joined["cell_geometry"], crs=cells.crs).array,
    )
    joined["intersection_area_m2"] = shapely.area(intersections)
    joined = joined.loc[joined["intersection_area_m2"] > 0].copy()
    footprint = joined.pivot_table(
        index="cell_id",
        columns="building_function",
        values="intersection_area_m2",
        aggfunc="sum",
        fill_value=0.0,
    ).reindex(columns=FUNCTION_COLUMNS, fill_value=0.0)
    footprint.columns = [f"osm_{column}_footprint_m2" for column in footprint.columns]

    anchors = classified.loc[classified["office_establishment_anchor"]].copy()
    anchors["geometry"] = anchors.geometry.representative_point()
    anchor_join = gpd.sjoin(
        anchors[["osm_id", "osm_way_id", "geometry"]],
        cells[["cell_id", "geometry"]],
        how="inner",
        predicate="within",
    )
    anchor_counts = anchor_join.groupby("cell_id").size().rename(
        "osm_office_establishment_count"
    )
    evidence = pd.DataFrame(index=cells["cell_id"])
    evidence = evidence.join(footprint).join(anchor_counts).fillna(0.0)
    evidence.index.name = "cell_id"
    evidence = evidence.reset_index().merge(
        cells[["cell_id", "district", "grid_row", "grid_col"]],
        on="cell_id",
        validate="one_to_one",
    )
    evidence["osm_office_establishment_count"] = evidence[
        "osm_office_establishment_count"
    ].astype(np.int32)

    classified_in_scope = joined.drop_duplicates(["osm_id", "osm_way_id"])
    function_counts = (
        classified_in_scope.groupby("building_function")
        .size()
        .reindex(FUNCTION_COLUMNS, fill_value=0)
    )
    function_area = (
        joined.groupby("building_function")["intersection_area_m2"]
        .sum()
        .reindex(FUNCTION_COLUMNS, fill_value=0.0)
    )
    quality = {
        "raw_multipolygon_features_in_bbox": raw_feature_count,
        "building_or_office_candidates": building_candidate_count,
        "classified_workplace_buildings_before_scope_filter": int(len(classified)),
        "invalid_or_empty_classified_geometries_before_repair": invalid_before_repair,
        "invalid_or_empty_classified_geometries_after_repair": int(
            (~classified.geometry.is_valid | classified.geometry.is_empty).sum()
        ),
        "classified_workplace_buildings_in_priority_scope": int(
            len(classified_in_scope)
        ),
        "classified_building_cell_intersections": int(len(joined)),
        "cells_with_building_function_evidence": int(
            (evidence.filter(like="_footprint_m2").sum(axis=1) > 0).sum()
        ),
        "office_establishment_anchors_in_source_bbox": int(
            classified["office_establishment_anchor"].sum()
        ),
        "office_establishment_anchors_matched_to_grid": int(len(anchor_join)),
        "cells_with_office_establishment_anchors": int(
            (evidence["osm_office_establishment_count"] > 0).sum()
        ),
        "known_building_levels_share_of_classified_features": float(
            classified_in_scope["levels_known"].mean()
        ),
        "building_levels_used_in_allocation": False,
        "building_function_counts": {
            key: int(value) for key, value in function_counts.items()
        },
        "building_function_footprint_m2": {
            key: float(value) for key, value in function_area.items()
        },
        "osm_source_sha256": OSM_BUILDING_SHA256,
        "osm_source_snapshot_date": OSM_BUILDING_SNAPSHOT_DATE,
    }
    return evidence, quality


def load_building_evidence(path: Path, cells: gpd.GeoDataFrame) -> pd.DataFrame:
    evidence = pd.read_parquet(path)
    required = {
        "cell_id",
        "district",
        "grid_row",
        "grid_col",
        "osm_office_establishment_count",
        *{f"osm_{column}_footprint_m2" for column in FUNCTION_COLUMNS},
    }
    if not required.issubset(evidence.columns):
        missing = sorted(required - set(evidence.columns))
        raise ValueError(f"Building evidence is missing columns: {missing}")
    if evidence["cell_id"].duplicated().any() or len(evidence) != len(cells):
        raise ValueError("Building evidence does not have one row per physical cell.")
    if set(evidence["cell_id"]) != set(cells["cell_id"]):
        raise ValueError("Building evidence cell IDs do not match the physical grid.")
    return evidence


def attach_building_evidence(
    cells: gpd.GeoDataFrame, evidence: pd.DataFrame
) -> gpd.GeoDataFrame:
    payload = evidence.drop(columns=["district", "grid_row", "grid_col"])
    output = cells.merge(payload, on="cell_id", validate="one_to_one")
    output = gpd.GeoDataFrame(output, geometry="geometry", crs=cells.crs)
    numeric = [
        *[f"osm_{column}_footprint_m2" for column in FUNCTION_COLUMNS],
        "osm_office_establishment_count",
    ]
    if output[numeric].isna().any().any() or (output[numeric] < 0).any().any():
        raise ValueError("Building evidence contains missing or negative values.")
    return output


def _raw_components(frame: pd.DataFrame, industry_code: str) -> pd.DataFrame:
    if industry_code not in FUNCTION_RELEVANCE:
        raise ValueError(f"No building-function rules for industry {industry_code}.")
    function = sum(
        frame[f"osm_{name}_footprint_m2"].astype(float) * relevance
        for name, relevance in FUNCTION_RELEVANCE[industry_code].items()
    )
    poi = sum(
        frame[name].astype(float) * relevance
        for name, relevance in POI_RELEVANCE[industry_code].items()
    )
    return pd.DataFrame(
        {
            "jrc_nonresidential_volume": frame["jrc_nres_volume_m3"].astype(float),
            "osm_building_function_footprint": function,
            "osm_office_establishments": frame[
                "osm_office_establishment_count"
            ].astype(float),
            "overture_poi_supplement": poi,
        },
        index=frame.index,
    )


def build_industry_weights(
    frame: pd.DataFrame, industry_code: str
) -> tuple[pd.Series, dict[str, dict[str, float]]]:
    """Create a linear, uncapped evidence mixture normalized by district."""

    raw = _raw_components(frame, industry_code)
    weights = pd.Series(0.0, index=frame.index, dtype=float)
    realized: dict[str, dict[str, float]] = {}
    for district in PRIORITY_DISTRICTS:
        index = frame.index[frame["district"] == district]
        district_raw = raw.loc[index]
        available = {
            component: float(district_raw[component].sum()) > 0
            for component in COMPONENT_SHARES
        }
        if not available["jrc_nonresidential_volume"]:
            raise RuntimeError(f"District {district} has no JRC non-residential volume.")
        available_share = sum(
            share for component, share in COMPONENT_SHARES.items() if available[component]
        )
        realized[district] = {}
        district_weight = pd.Series(0.0, index=index, dtype=float)
        for component, requested_share in COMPONENT_SHARES.items():
            realized_share = (
                requested_share / available_share if available[component] else 0.0
            )
            realized[district][component] = float(realized_share)
            if realized_share:
                district_weight += (
                    district_raw[component]
                    / float(district_raw[component].sum())
                    * realized_share
                )
        if not math.isclose(float(district_weight.sum()), 1.0, abs_tol=1e-12):
            raise RuntimeError(
                f"Industry {industry_code} weights do not sum to one in {district}."
            )
        weights.loc[index] = district_weight
    return weights, realized


def allocate_integer_controls(
    frame: pd.DataFrame,
    weights: pd.Series,
    totals: pd.Series,
) -> pd.Series:
    """Allocate integer people by largest remainder, exactly preserving controls."""

    allocation = pd.Series(0, index=frame.index, dtype=np.int64)
    for district in PRIORITY_DISTRICTS:
        index = frame.index[frame["district"] == district]
        district_weights = weights.loc[index]
        if not math.isclose(float(district_weights.sum()), 1.0, abs_tol=1e-12):
            raise RuntimeError(f"Weights are not normalized in {district}.")
        total = int(totals.loc[district])
        raw = district_weights * total
        assigned = np.floor(raw).astype(np.int64)
        remainder = total - int(assigned.sum())
        order = pd.DataFrame(
            {
                "fraction": raw - assigned,
                "cell_id": frame.loc[index, "cell_id"],
            },
            index=index,
        ).sort_values(["fraction", "cell_id"], ascending=[False, True], kind="mergesort")
        if remainder:
            assigned.loc[order.index[:remainder]] += 1
        if int(assigned.sum()) != total:
            raise RuntimeError(f"Integer reconciliation failed for {district}.")
        allocation.loc[index] = assigned
    return allocation


def _gini(values: pd.Series) -> float:
    array = np.sort(values.to_numpy(dtype=float))
    total = float(array.sum())
    if total == 0:
        return 0.0
    n = len(array)
    ranks = np.arange(1, n + 1, dtype=float)
    return float(np.sum((2 * ranks - n - 1) * array) / (n * total))


def _diagnostic_record(
    frame: pd.DataFrame,
    allocation: pd.Series,
    weights: pd.Series,
    realized: dict[str, dict[str, float]],
    totals: pd.Series,
    *,
    industry_code: str,
    scenario: str,
    control_status: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for district in PRIORITY_DISTRICTS:
        index = frame.index[frame["district"] == district]
        values = allocation.loc[index]
        top_count = max(1, math.ceil(len(values) * 0.01))
        records.append(
            {
                "scenario": scenario,
                "district": district,
                "industry_code": industry_code,
                "control_status": control_status,
                "assigned_employment": int(totals.loc[district]),
                "allocated_employment": int(values.sum()),
                "reconciliation_difference": int(values.sum())
                - int(totals.loc[district]),
                "cell_count": int(len(values)),
                "positive_weight_cells": int((weights.loc[index] > 0).sum()),
                "positive_employment_cells": int((values > 0).sum()),
                "top_1_percent_cell_employment_share": float(
                    values.nlargest(top_count).sum() / max(int(values.sum()), 1)
                ),
                "gini_cell_employment": _gini(values),
                "maximum_cell_employment": int(values.max()),
                **{
                    f"realized_{component}_share": realized[district][component]
                    for component in COMPONENT_SHARES
                },
                "no_log_cap_winsorize_or_minmax": True,
                "generic_ppml_fitted": False,
                "uniform_allocation_used_as_main": False,
            }
        )
    return records


def _load_controls(
    district_industry_path: Path,
    subgroup_scenario_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    _require_hash(
        district_industry_path, DISTRICT_INDUSTRY_SHA256, "District-industry controls"
    )
    _require_hash(
        subgroup_scenario_path,
        CORE_PLUS_SCENARIO_SHA256,
        "Core+ district scenarios",
    )
    industry = pd.read_csv(district_industry_path, dtype={"industry_code": str})
    industry = industry.loc[
        industry["district"].isin(PRIORITY_DISTRICTS)
        & industry["industry_code"].isin(CORE_CODES)
    ].copy()
    if industry.duplicated(["district", "industry_code"]).any() or len(industry) != 24:
        raise ValueError("Expected 24 priority district-by-Core-industry controls.")
    subgroup = pd.read_csv(subgroup_scenario_path, dtype={"industry_code": str})
    subgroup = subgroup.loc[
        subgroup["district"].isin(PRIORITY_DISTRICTS)
        & subgroup["industry_code"].isin(CORE_PLUS_CODES)
        & subgroup["scenario"].isin(SCENARIOS)
    ].copy()
    if subgroup.duplicated(["scenario", "district", "industry_code"]).any() or len(
        subgroup
    ) != 96:
        raise ValueError("Expected 96 priority Core+ subgroup scenario controls.")
    return industry, subgroup


def construct_spatial_allocations(
    cells_with_evidence: gpd.GeoDataFrame,
    district_industry_path: Path,
    subgroup_scenario_path: Path,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame, pd.DataFrame, dict[str, Any]]:
    """Construct Core, Core+ Base, and Low/Base/High cell allocations."""

    frame = cells_with_evidence.copy().reset_index(drop=True)
    industry, subgroup = _load_controls(
        district_industry_path, subgroup_scenario_path
    )
    diagnostics: list[dict[str, Any]] = []
    weights_by_code: dict[str, pd.Series] = {}
    realized_by_code: dict[str, dict[str, dict[str, float]]] = {}
    for code in (*CORE_CODES, *CORE_PLUS_CODES):
        weights, realized = build_industry_weights(frame, code)
        weights_by_code[code] = weights
        realized_by_code[code] = realized

    core = frame.copy()
    core_total = pd.Series(0, index=frame.index, dtype=np.int64)
    for code in CORE_CODES:
        totals = (
            industry.loc[industry["industry_code"] == code]
            .set_index("district")["district_industry_employment"]
            .reindex(PRIORITY_DISTRICTS)
            .astype(int)
        )
        allocation = allocate_integer_controls(frame, weights_by_code[code], totals)
        core[f"allocation_weight_{code}"] = weights_by_code[code]
        core[f"cell_employment_{code}"] = allocation
        core_total += allocation
        diagnostics.extend(
            _diagnostic_record(
                frame,
                allocation,
                weights_by_code[code],
                realized_by_code[code],
                totals,
                industry_code=code,
                scenario="core_hard_control",
                control_status="official district-by-industry hard control",
            )
        )
    core["cell_employment_core"] = core_total
    core["employment_definition"] = "Core office-oriented employment: I + J + M"
    core["control_grain"] = "official district by industry"
    core["geometry_is_approximate"] = True
    core["boundary_source"] = (
        "OSM 2026-08-19 street/town union inherited from employment grid"
    )
    core["employment_universe"] = EMPLOYMENT_UNIVERSE
    core["reference_date"] = REFERENCE_DATE
    core["reach_intersection_calculated"] = False

    scenario_allocations: dict[tuple[str, str], pd.Series] = {}
    for scenario in SCENARIOS:
        for code in CORE_PLUS_CODES:
            totals = (
                subgroup.loc[
                    (subgroup["scenario"] == scenario)
                    & (subgroup["industry_code"] == code)
                ]
                .set_index("district")["scenario_district_subgroup_employment"]
                .reindex(PRIORITY_DISTRICTS)
                .astype(int)
            )
            allocation = allocate_integer_controls(frame, weights_by_code[code], totals)
            scenario_allocations[(scenario, code)] = allocation
            diagnostics.extend(
                _diagnostic_record(
                    frame,
                    allocation,
                    weights_by_code[code],
                    realized_by_code[code],
                    totals,
                    industry_code=code,
                    scenario=scenario,
                    control_status=(
                        "district subgroup composition modelled; official Shanghai subgroup total"
                    ),
                )
            )

    base_columns = [
        "district",
        "cell_id",
        "grid_row",
        "grid_col",
        "center_x",
        "center_y",
        "cell_area_m2",
        "area_fraction",
        "cell_employment_core",
        "geometry",
    ]
    core_plus_base = core[base_columns].copy()
    base_selected = pd.Series(0, index=frame.index, dtype=np.int64)
    for code in CORE_PLUS_CODES:
        core_plus_base[f"allocation_weight_{code}"] = weights_by_code[code]
        allocation = scenario_allocations[("base", code)]
        core_plus_base[f"cell_employment_{code}"] = allocation
        base_selected += allocation
    core_plus_base["cell_employment_selected_72_base"] = base_selected
    core_plus_base["cell_employment_core_plus_base"] = core_total + base_selected
    core_plus_base["employment_definition"] = (
        "Core+ Base office-oriented employment: Core I+J+M plus selected 721/723/724/725"
    )
    core_plus_base["core_is_hard_control"] = True
    core_plus_base["selected_72_district_composition_is_modelled"] = True
    core_plus_base["geometry_is_approximate"] = True
    core_plus_base["boundary_source"] = core["boundary_source"]
    core_plus_base["employment_universe"] = EMPLOYMENT_UNIVERSE
    core_plus_base["reference_date"] = REFERENCE_DATE
    core_plus_base["reach_intersection_calculated"] = False
    core_plus_base = gpd.GeoDataFrame(
        core_plus_base, geometry="geometry", crs=frame.crs
    )

    sensitivity = core[base_columns].copy()
    for scenario in SCENARIOS:
        selected = pd.Series(0, index=frame.index, dtype=np.int64)
        for code in CORE_PLUS_CODES:
            allocation = scenario_allocations[(scenario, code)]
            sensitivity[f"cell_employment_{code}_{scenario}"] = allocation
            selected += allocation
        sensitivity[f"cell_employment_selected_72_{scenario}"] = selected
        sensitivity[f"cell_employment_core_plus_{scenario}"] = core_total + selected
    sensitivity["cell_employment_core_plus_low_minus_base"] = (
        sensitivity["cell_employment_core_plus_low_office_intensity"]
        - sensitivity["cell_employment_core_plus_base"]
    )
    sensitivity["cell_employment_core_plus_high_minus_base"] = (
        sensitivity["cell_employment_core_plus_high_office_intensity"]
        - sensitivity["cell_employment_core_plus_base"]
    )
    sensitivity["core_is_hard_control"] = True
    sensitivity["selected_72_district_composition_is_modelled"] = True
    sensitivity["geometry_is_approximate"] = True
    sensitivity["boundary_source"] = core["boundary_source"]
    sensitivity["employment_universe"] = EMPLOYMENT_UNIVERSE
    sensitivity["reference_date"] = REFERENCE_DATE
    sensitivity["reach_intersection_calculated"] = False
    sensitivity = gpd.GeoDataFrame(sensitivity, geometry="geometry", crs=frame.crs)

    diagnostic_table = pd.DataFrame(diagnostics)
    if (diagnostic_table["reconciliation_difference"] != 0).any():
        raise RuntimeError("At least one district-industry allocation failed identity.")

    city_core_from_controls = int(
        pd.read_csv(district_industry_path, dtype={"industry_code": str})
        .loc[lambda x: x["industry_code"].isin(CORE_CODES), "district_industry_employment"]
        .sum()
    )
    city_scenarios = pd.read_csv(
        subgroup_scenario_path, dtype={"industry_code": str}
    )
    city_core_plus = {
        scenario: CORE_EMPLOYMENT
        + int(
            city_scenarios.loc[
                city_scenarios["scenario"] == scenario,
                "scenario_district_subgroup_employment",
            ].sum()
        )
        for scenario in SCENARIOS
    }
    if city_core_from_controls != CORE_EMPLOYMENT:
        raise RuntimeError("City Core hard controls changed.")
    if set(city_core_plus.values()) != {CORE_PLUS_EMPLOYMENT}:
        raise RuntimeError("City Core+ scenario denominator changed.")

    summary = {
        "schema_version": 1,
        "reference_date": REFERENCE_DATE,
        "employment_universe": EMPLOYMENT_UNIVERSE,
        "spatial_scope": "eight audited reach-relevant districts",
        "spatial_scope_districts": list(PRIORITY_DISTRICTS),
        "city_core_hard_control": CORE_EMPLOYMENT,
        "city_core_plus_control_each_scenario": CORE_PLUS_EMPLOYMENT,
        "priority_grid_cell_count": int(len(frame)),
        "priority_core_allocated_employment": int(core_total.sum()),
        "priority_core_plus_allocated_employment": {
            scenario: int(
                sensitivity[f"cell_employment_core_plus_{scenario}"].sum()
            )
            for scenario in SCENARIOS
        },
        "component_shares": COMPONENT_SHARES,
        "building_function_relevance": FUNCTION_RELEVANCE,
        "poi_relevance": POI_RELEVANCE,
        "allocation_method": (
            "uncapped linear evidence mixture normalized within district-industry controls, "
            "then deterministic largest-remainder integer reconciliation"
        ),
        "core_is_hard_control": True,
        "core_plus_base_is_central_case": True,
        "low_and_high_core_plus_retained": True,
        "uniform_allocation_used_as_main": False,
        "generic_ppml_fitted": False,
        "spatial_smoothing_or_winsorization_used": False,
        "grid_created": True,
        "reach_intersection_calculated": False,
        "reach_percentage_calculated": False,
        "production_outputs_modified": False,
        "geometry_is_approximate": True,
        "approximate_boundary_disclosure": (
            "The physical lattice is inherited from the audited OSM street/town supports; "
            "it is not an official 2023 accounting-boundary layer."
        ),
    }
    return core, core_plus_base, sensitivity, diagnostic_table, summary


def write_source_manifest(
    path: Path,
    *,
    repository_root: Path,
    building_evidence_path: Path,
    general_grid_path: Path,
    district_industry_path: Path,
    subgroup_scenario_path: Path,
) -> None:
    rows = [
        {
            "source_id": "office-spatial-general-employment-grid",
            "source_type": "derived frozen 100 m analytical input",
            "publisher": "Jinke employment benchmark v1",
            "year_or_release": "2023 controls; 2020 JRC; 2026-07-22 Overture",
            "url": "repository asset",
            "repository_or_cache_path": str(general_grid_path.relative_to(repository_root)),
            "sha256": sha256_file(general_grid_path),
            "derived_sha256": "",
            "license_or_reuse": "inherits JRC reuse and Overture per-source attribution",
            "used_for": "physical cell lattice, JRC non-residential volume, supplementary POIs",
            "reproducible": True,
        },
        {
            "source_id": "osm-building-function-2026-08-23",
            "source_type": "open building footprint/function and office-establishment tags",
            "publisher": "OpenStreetMap contributors; extract by download.openstreetmap.fr",
            "year_or_release": OSM_BUILDING_SNAPSHOT_DATE,
            "url": OSM_BUILDING_SOURCE_URL,
            "repository_or_cache_path": (
                "raw PBF outside git; derived 100 m evidence committed at "
                + str(building_evidence_path.relative_to(repository_root))
            ),
            "sha256": OSM_BUILDING_SHA256,
            "derived_sha256": sha256_file(building_evidence_path),
            "license_or_reuse": f"{OSM_LICENSE}; attribution {OSM_ATTRIBUTION_URL}",
            "used_for": "building function footprint and office-establishment anchors",
            "reproducible": (
                "derived evidence is frozen in repository; raw URL is rolling and rerun requires the hash-pinned snapshot"
            ),
        },
        {
            "source_id": "official-district-industry-controls-2023",
            "source_type": "official Fifth Economic Census district-by-industry employment",
            "publisher": "Shanghai Municipal Statistics Bureau",
            "year_or_release": REFERENCE_DATE,
            "url": "https://tjj.sh.gov.cn/tjnj/jjpcnj2023/zk/html/A1-09.xls",
            "repository_or_cache_path": str(district_industry_path.relative_to(repository_root)),
            "sha256": sha256_file(district_industry_path),
            "derived_sha256": "",
            "license_or_reuse": "official statistical publication",
            "used_for": "Core I/J/M district hard controls",
            "reproducible": True,
        },
        {
            "source_id": "core-plus-composition-scenarios-2023",
            "source_type": "reviewed constrained district composition sensitivity",
            "publisher": "Jinke office-employment audit",
            "year_or_release": REFERENCE_DATE,
            "url": "repository asset",
            "repository_or_cache_path": str(subgroup_scenario_path.relative_to(repository_root)),
            "sha256": sha256_file(subgroup_scenario_path),
            "derived_sha256": "",
            "license_or_reuse": "derived from official statistical tables",
            "used_for": "Low/Base/High selected-72 district controls",
            "reproducible": True,
        },
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def write_spatial_outputs(
    repository_root: Path,
    *,
    osm_pbf_path: Path | None = None,
) -> dict[str, Path]:
    """Build or reuse evidence and write new office-spatial artifacts only."""

    repository_root = repository_root.resolve()
    spatial_root = repository_root / "data/office_employment/spatial"
    intermediate = spatial_root / "intermediate"
    outputs = spatial_root / "outputs"
    manifests = spatial_root / "manifests"
    maps = spatial_root / "maps"
    for directory in (intermediate, outputs, manifests, maps):
        directory.mkdir(parents=True, exist_ok=True)

    general_grid = (
        repository_root
        / "data/employment/intermediate/employment-allocation-grid.parquet"
    )
    district_industry = (
        repository_root
        / "data/office_employment/intermediate/district-industry-employment-2023.csv"
    )
    subgroup_scenarios = (
        repository_root
        / "data/office_employment/scenarios/district-business-services-subgroup-scenarios-2023.csv"
    )
    evidence_path = intermediate / "building-function-evidence-100m.parquet"
    quality_path = intermediate / "building-evidence-quality.json"
    cells = build_priority_cell_lattice(general_grid)
    if osm_pbf_path is not None:
        evidence, quality = extract_building_evidence(osm_pbf_path.resolve(), cells)
        evidence.to_parquet(evidence_path, index=False, compression="zstd")
        quality_path.write_text(
            json.dumps(quality, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        if not evidence_path.is_file() or not quality_path.is_file():
            raise FileNotFoundError(
                "Provide --osm-pbf for the first run or retain the frozen derived evidence."
            )
        evidence = load_building_evidence(evidence_path, cells)
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
    cells = attach_building_evidence(cells, evidence)
    poi_columns = [
        "poi_business_finance",
        "poi_industry_logistics",
        "poi_education_research",
        "poi_retail_hospitality",
        "poi_health_public",
        "poi_other_economic",
    ]
    quality.update(
        {
            "priority_grid_cell_count": int(len(cells)),
            "cells_with_positive_jrc_nonresidential_volume": int(
                (cells["jrc_nres_volume_m3"] > 0).sum()
            ),
            "positive_jrc_cell_share": float(
                (cells["jrc_nres_volume_m3"] > 0).mean()
            ),
            "total_jrc_nonresidential_volume_m3": float(
                cells["jrc_nres_volume_m3"].sum()
            ),
            "cells_with_any_overture_workplace_poi": int(
                (cells[poi_columns].sum(axis=1) > 0).sum()
            ),
            "positive_overture_cell_share": float(
                (cells[poi_columns].sum(axis=1) > 0).mean()
            ),
            "total_overture_workplace_intensity": float(
                cells[poi_columns].sum().sum()
            ),
        }
    )
    quality_path.write_text(
        json.dumps(quality, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    core, core_plus, sensitivity, diagnostics, summary = construct_spatial_allocations(
        cells, district_industry, subgroup_scenarios
    )
    summary["source_quality"] = quality
    summary["input_sha256"] = {
        "general_employment_grid": sha256_file(general_grid),
        "building_function_evidence": sha256_file(evidence_path),
        "district_industry_controls": sha256_file(district_industry),
        "core_plus_scenarios": sha256_file(subgroup_scenarios),
    }

    core_path = outputs / "core-employment-grid-100m.parquet"
    core_plus_path = outputs / "core-plus-base-employment-grid-100m.parquet"
    sensitivity_path = outputs / "core-plus-sensitivity-grid-100m.parquet"
    diagnostics_path = outputs / "allocation-diagnostics.csv"
    summary_path = outputs / "spatial-allocation-summary.json"
    source_manifest_path = manifests / "source-manifest.csv"
    core.to_parquet(core_path, index=False, compression="zstd")
    core_plus.to_parquet(core_plus_path, index=False, compression="zstd")
    sensitivity.to_parquet(sensitivity_path, index=False, compression="zstd")
    diagnostics.to_csv(diagnostics_path, index=False)
    summary["output_sha256"] = {
        "core_grid": sha256_file(core_path),
        "core_plus_base_grid": sha256_file(core_plus_path),
        "core_plus_sensitivity_grid": sha256_file(sensitivity_path),
        "allocation_diagnostics": sha256_file(diagnostics_path),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_source_manifest(
        source_manifest_path,
        repository_root=repository_root,
        building_evidence_path=evidence_path,
        general_grid_path=general_grid,
        district_industry_path=district_industry,
        subgroup_scenario_path=subgroup_scenarios,
    )
    return {
        "spatial_root": spatial_root,
        "maps": maps,
        "core": core_path,
        "core_plus": core_plus_path,
        "sensitivity": sensitivity_path,
        "diagnostics": diagnostics_path,
        "summary": summary_path,
        "source_manifest": source_manifest_path,
        "building_evidence": evidence_path,
        "building_quality": quality_path,
    }
