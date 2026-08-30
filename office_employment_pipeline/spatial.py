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

from employment_pipeline.boundaries import load_restricted_zone_controls
from office_employment_pipeline.control_reconciliation import (
    CORE_CODES,
    OFFICE_CODES,
    SCENARIOS,
    SELECTED_72_CODES,
    construct_control_industry_matrix,
)
from office_employment_pipeline.district_controls import (
    CORE_EMPLOYMENT,
    CORE_PLUS_EMPLOYMENT,
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
CONTROL_CROSSWALK_SHA256 = (
    "154e1d50ba04e31c17aa63a62eb69e54c9c6f7d7334a7b8574ff86242d783a59"
)
RESIDUAL_STRATA_SHA256 = (
    "c86a35140b291f5eeba828f7375759d447c2680e69fbb326fa10094c44212ea2"
)
DISTRICT_DIRECT_BASELINE_SHA256 = (
    "8faed83a6e6e60bdd66c39dfede17c35dc8e05e5705986823ed9c488143caca1"
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
WEIGHTING_SCENARIOS = {
    "base": {
        "label": "Base 60/25/10/5",
        "shares": {
            "jrc_nonresidential_volume": 0.60,
            "osm_building_function_footprint": 0.25,
            "osm_office_establishments": 0.10,
            "overture_poi_supplement": 0.05,
        },
        "interpretation": "balanced building-magnitude and workplace-function evidence",
    },
    "building_volume_dominant": {
        "label": "Building-volume dominant 75/15/7.5/2.5",
        "shares": {
            "jrc_nonresidential_volume": 0.75,
            "osm_building_function_footprint": 0.15,
            "osm_office_establishments": 0.075,
            "overture_poi_supplement": 0.025,
        },
        "interpretation": "tests stronger reliance on complete built-volume magnitude",
    },
    "workplace_evidence_emphasis": {
        "label": "Workplace-evidence emphasis 45/30/15/10",
        "shares": {
            "jrc_nonresidential_volume": 0.45,
            "osm_building_function_footprint": 0.30,
            "osm_office_establishments": 0.15,
            "overture_poi_supplement": 0.10,
        },
        "interpretation": "tests stronger reliance on function and establishment evidence",
    },
}
COMPONENT_SHARES = WEIGHTING_SCENARIOS["base"]["shares"]

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
    *,
    expected_sha256: str = OSM_BUILDING_SHA256,
    source_snapshot_date: str = OSM_BUILDING_SNAPSHOT_DATE,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Aggregate OSM building function and office tags to physical 100 m cells."""

    _require_hash(osm_pbf_path, expected_sha256, "OSM building snapshot")
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
        "osm_source_sha256": expected_sha256,
        "osm_source_snapshot_date": source_snapshot_date,
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


def build_control_support_cells(
    general_grid_path: Path,
    physical_cells: gpd.GeoDataFrame,
    control_crosswalk_path: Path,
    residual_strata_path: Path,
    restricted_zone_directory: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Build temporary control-specific supports without publishing zone shapes."""

    _require_hash(general_grid_path, GENERAL_GRID_SHA256, "General employment grid")
    _require_hash(
        control_crosswalk_path, CONTROL_CROSSWALK_SHA256, "Fine control crosswalk"
    )
    _require_hash(residual_strata_path, RESIDUAL_STRATA_SHA256, "Residual strata")
    source = gpd.read_parquet(general_grid_path)
    ordinary = source.loc[
        source["district"].isin(PRIORITY_DISTRICTS)
        & source["control_type"].isin(["street", "town"])
        & source.geometry.notna()
    ].copy()
    ordinary["grid_row"] = ordinary["grid_row"].astype(np.int32)
    ordinary["grid_col"] = ordinary["grid_col"].astype(np.int32)
    ordinary["physical_cell_id"] = (
        ordinary["district"]
        + ":"
        + ordinary["grid_row"].astype(str)
        + ":"
        + ordinary["grid_col"].astype(str)
    )
    evidence_columns = [
        *[f"osm_{column}_footprint_m2" for column in FUNCTION_COLUMNS],
        "osm_office_establishment_count",
    ]
    physical_payload = physical_cells[
        ["cell_id", "cell_area_m2", *evidence_columns]
    ].rename(
        columns={
            "cell_id": "physical_cell_id",
            "cell_area_m2": "physical_cell_area_m2",
        }
    )
    ordinary = ordinary.merge(
        physical_payload, on="physical_cell_id", validate="many_to_one"
    )
    ordinary["support_cell_area_m2"] = ordinary["cell_area_m2"].astype(float)
    ordinary["support_area_share_of_physical_cell"] = (
        ordinary["support_cell_area_m2"] / ordinary["physical_cell_area_m2"]
    )
    for column in evidence_columns:
        ordinary[column] = (
            ordinary[column].astype(float)
            * ordinary["support_area_share_of_physical_cell"]
        )
    ordinary = ordinary.rename(
        columns={
            "accounting_control": "accounting_stratum_id",
            "control_employment": "official_control_total_employment",
        }
    )
    ordinary["support_kind"] = "official_fine_control"
    ordinary["restricted_geometry"] = False

    zones = load_restricted_zone_controls(
        restricted_zone_directory, control_crosswalk_path
    )
    zone_frames: list[pd.DataFrame] = []
    for zone in zones.itertuples(index=False):
        candidates = physical_cells.loc[
            physical_cells["district"].eq(zone.district)
            & physical_cells.geometry.intersects(zone.geometry)
        ].copy()
        intersections = shapely.intersection(candidates.geometry.array, zone.geometry)
        area = shapely.area(intersections)
        candidates = candidates.loc[area > 0].copy()
        area = area[area > 0]
        candidates["physical_cell_area_m2"] = candidates["cell_area_m2"]
        candidates["support_cell_area_m2"] = area
        candidates["support_area_share_of_physical_cell"] = (
            candidates["support_cell_area_m2"] / candidates["cell_area_m2"]
        )
        for column in (
            "jrc_nres_volume_m3",
            "poi_business_finance",
            "poi_industry_logistics",
            "poi_education_research",
            "poi_retail_hospitality",
            "poi_health_public",
            "poi_other_economic",
            *evidence_columns,
        ):
            candidates[column] = (
                candidates[column].astype(float)
                * candidates["support_area_share_of_physical_cell"]
            )
        candidates["physical_cell_id"] = candidates["cell_id"]
        candidates["accounting_stratum_id"] = str(zone.accounting_stratum_id)
        candidates["control_name"] = zone.official_control_name_2023
        candidates["control_type"] = "functional_zone"
        candidates["official_control_total_employment"] = int(
            zone.employment_reconciled
        )
        candidates["support_kind"] = "restricted_functional_zone"
        candidates["restricted_geometry"] = True
        zone_frames.append(candidates)

    residuals = pd.read_csv(residual_strata_path, dtype={"residual_id": str})
    residuals = residuals.loc[residuals["district"].isin(PRIORITY_DISTRICTS)]
    residual_frames: list[pd.DataFrame] = []
    for residual in residuals.itertuples(index=False):
        district_cells = physical_cells.loc[
            physical_cells["district"].eq(residual.district)
        ].copy()
        district_cells["physical_cell_id"] = district_cells["cell_id"]
        district_cells["support_cell_area_m2"] = district_cells["cell_area_m2"]
        district_cells["physical_cell_area_m2"] = district_cells["cell_area_m2"]
        district_cells["support_area_share_of_physical_cell"] = 1.0
        district_cells["accounting_stratum_id"] = str(residual.residual_id)
        district_cells["control_name"] = str(residual.residual_id)
        district_cells["control_type"] = "residual"
        district_cells["official_control_total_employment"] = int(
            residual.employment_nominal
        )
        district_cells["support_kind"] = "district_residual_overlay"
        district_cells["restricted_geometry"] = False
        residual_frames.append(district_cells)

    support_columns = [
        "district",
        "physical_cell_id",
        "grid_row",
        "grid_col",
        "accounting_stratum_id",
        "control_name",
        "control_type",
        "official_control_total_employment",
        "support_kind",
        "restricted_geometry",
        "support_cell_area_m2",
        "physical_cell_area_m2",
        "support_area_share_of_physical_cell",
        "jrc_nres_volume_m3",
        "poi_business_finance",
        "poi_industry_logistics",
        "poi_education_research",
        "poi_retail_hospitality",
        "poi_health_public",
        "poi_other_economic",
        *evidence_columns,
    ]
    ordinary["control_name"] = ordinary["control_name"].astype(str)
    support = pd.concat(
        [ordinary[support_columns], *[frame[support_columns] for frame in zone_frames],
         *[frame[support_columns] for frame in residual_frames]],
        ignore_index=True,
    )
    support["accounting_stratum_id"] = support["accounting_stratum_id"].astype(str)
    support["support_cell_id"] = (
        support["accounting_stratum_id"] + ":" + support["physical_cell_id"]
    )
    if support["support_cell_id"].duplicated().any():
        raise RuntimeError("A control support contains a duplicate physical cell.")
    counts = support.groupby("control_type")["accounting_stratum_id"].nunique()
    if int(counts.get("street", 0) + counts.get("town", 0)) != 113:
        raise RuntimeError("Expected 113 ordinary fine-control supports.")
    if int(counts.get("functional_zone", 0)) != 3:
        raise RuntimeError("Expected three separate Pudong functional-zone supports.")
    if int(counts.get("residual", 0)) != 8:
        raise RuntimeError("Expected eight district residual supports.")
    quality = {
        "official_fine_control_count": 116,
        "ordinary_control_count": 113,
        "functional_zone_count": 3,
        "residual_overlay_count": 8,
        "support_record_count": int(len(support)),
        "functional_zone_support_records": int(
            support["control_type"].eq("functional_zone").sum()
        ),
        "restricted_zone_source_geometry_committed": False,
        "functional_zone_output_is_aggregated_with_other_strata": True,
    }
    return support, quality


def build_control_industry_weights(
    support: pd.DataFrame,
    industry_code: str,
    component_shares: dict[str, float],
) -> tuple[pd.Series, dict[str, dict[str, Any]]]:
    """Create uncapped evidence weights normalized within each accounting stratum."""

    if not math.isclose(sum(component_shares.values()), 1.0, abs_tol=1e-12):
        raise ValueError("Weighting-scenario component shares must sum to one.")
    raw = _raw_components(support, industry_code)
    weights = pd.Series(0.0, index=support.index, dtype=float)
    realized: dict[str, dict[str, Any]] = {}
    for control, index in support.groupby("accounting_stratum_id", sort=False).groups.items():
        control_raw = raw.loc[index]
        available = {
            component: float(control_raw[component].sum()) > 0
            for component in component_shares
        }
        available_share = sum(
            share for component, share in component_shares.items() if available[component]
        )
        control_weight = pd.Series(0.0, index=index, dtype=float)
        realized[str(control)] = {"uniform_fallback_used": available_share == 0}
        if available_share == 0:
            area = support.loc[index, "support_cell_area_m2"].astype(float)
            control_weight = area / float(area.sum())
            for component in component_shares:
                realized[str(control)][component] = 0.0
        else:
            for component, requested_share in component_shares.items():
                realized_share = (
                    requested_share / available_share if available[component] else 0.0
                )
                realized[str(control)][component] = float(realized_share)
                if realized_share:
                    control_weight += (
                        control_raw[component]
                        / float(control_raw[component].sum())
                        * realized_share
                    )
        if not math.isclose(float(control_weight.sum()), 1.0, abs_tol=1e-12):
            raise RuntimeError(
                f"Industry {industry_code} weights do not sum to one in {control}."
            )
        weights.loc[index] = control_weight
    return weights, realized


def allocate_integer_control_matrix(
    support: pd.DataFrame,
    weights: pd.Series,
    totals: pd.Series,
) -> pd.Series:
    """Allocate integer people within each control by deterministic remainder."""

    totals.index = totals.index.astype(str)
    support_controls = set(support["accounting_stratum_id"].astype(str))
    if set(totals.index) != support_controls:
        raise RuntimeError("Matrix controls and spatial supports do not match exactly.")
    allocation = pd.Series(0, index=support.index, dtype=np.int64)
    for control, index in support.groupby("accounting_stratum_id", sort=False).groups.items():
        control_weights = weights.loc[index]
        if not math.isclose(float(control_weights.sum()), 1.0, abs_tol=1e-12):
            raise RuntimeError(f"Weights are not normalized within {control}.")
        total = int(totals.loc[str(control)])
        raw = control_weights * total
        assigned = np.floor(raw).astype(np.int64)
        remainder = total - int(assigned.sum())
        order = pd.DataFrame(
            {
                "fraction": raw - assigned,
                "support_cell_id": support.loc[index, "support_cell_id"],
            },
            index=index,
        ).sort_values(
            ["fraction", "support_cell_id"],
            ascending=[False, True],
            kind="mergesort",
        )
        if remainder:
            assigned.loc[order.index[:remainder]] += 1
        if int(assigned.sum()) != total:
            raise RuntimeError(f"Integer allocation failed for {control}.")
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


def _control_diagnostic_records(
    support: pd.DataFrame,
    allocation: pd.Series,
    weights: pd.Series,
    realized: dict[str, dict[str, Any]],
    totals: pd.Series,
    *,
    industry_code: str,
    scenario: str,
    weighting_scenario: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    metadata = support.groupby("accounting_stratum_id", sort=False).first()
    for control, index in support.groupby("accounting_stratum_id", sort=False).groups.items():
        control = str(control)
        values = allocation.loc[index]
        top_count = max(1, math.ceil(len(values) * 0.01))
        records.append(
            {
                "scenario": scenario,
                "weighting_scenario": weighting_scenario,
                "district": metadata.loc[control, "district"],
                "accounting_stratum_id": control,
                "control_name": metadata.loc[control, "control_name"],
                "control_type": metadata.loc[control, "control_type"],
                "industry_code": industry_code,
                "assigned_employment": int(totals.loc[control]),
                "allocated_employment": int(values.sum()),
                "reconciliation_difference": int(values.sum())
                - int(totals.loc[control]),
                "cell_count": int(len(values)),
                "positive_weight_cells": int((weights.loc[index] > 0).sum()),
                "positive_employment_cells": int((values > 0).sum()),
                "top_1_percent_cell_employment_share": float(
                    values.nlargest(top_count).sum() / max(int(values.sum()), 1)
                ),
                "gini_cell_employment": _gini(values),
                "maximum_cell_employment": int(values.max()),
                **{
                    f"realized_{component}_share": realized[control][component]
                    for component in COMPONENT_SHARES
                },
                "uniform_fallback_used": bool(
                    realized[control]["uniform_fallback_used"]
                ),
                "no_log_cap_winsorize_or_minmax": True,
                "generic_ppml_fitted": False,
                "uniform_allocation_used_as_main": False,
            }
        )
    return records


def _matrix_totals(
    matrix: pd.DataFrame, scenario: str, industry_code: str
) -> pd.Series:
    totals = matrix.loc[
        matrix["scenario"].eq(scenario)
        & matrix["industry_code"].eq(industry_code)
    ].set_index("accounting_stratum_id")["control_industry_employment"]
    if totals.index.duplicated().any():
        raise RuntimeError("Control-industry matrix contains duplicate totals.")
    return totals.astype(np.int64)


def _aggregate_to_physical_cells(
    physical_cells: gpd.GeoDataFrame,
    support: pd.DataFrame,
    allocations: dict[str, pd.Series],
) -> gpd.GeoDataFrame:
    payload = pd.DataFrame({"physical_cell_id": support["physical_cell_id"]})
    for column, values in allocations.items():
        payload[column] = values.astype(np.int64)
    aggregated = payload.groupby("physical_cell_id", as_index=False).sum()
    output = physical_cells.merge(
        aggregated,
        left_on="cell_id",
        right_on="physical_cell_id",
        how="left",
        validate="one_to_one",
    ).drop(columns="physical_cell_id")
    for column in allocations:
        output[column] = output[column].fillna(0).astype(np.int64)
    return gpd.GeoDataFrame(output, geometry="geometry", crs=physical_cells.crs)


def _grid_metadata(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    columns = [
        "district",
        "cell_id",
        "grid_row",
        "grid_col",
        "center_x",
        "center_y",
        "cell_area_m2",
        "area_fraction",
        "geometry",
    ]
    return gpd.GeoDataFrame(frame[columns].copy(), geometry="geometry", crs=frame.crs)


def _concentration_record(label: str, values: pd.Series) -> dict[str, Any]:
    values = values.astype(float)
    total = float(values.sum())
    top_count = max(1, math.ceil(len(values) * 0.01))
    shares = values / total if total else values
    return {
        "allocation_architecture": label,
        "employment": int(total),
        "cell_count": int(len(values)),
        "positive_cell_count": int((values > 0).sum()),
        "gini_cell_employment": _gini(values),
        "top_1_percent_cell_employment_share": float(
            values.nlargest(top_count).sum() / total if total else 0.0
        ),
        "maximum_cell_employment": int(values.max()),
        "cell_hhi": float(np.square(shares).sum()),
    }


def _build_control_shift_comparison(
    support: pd.DataFrame,
    matrix: pd.DataFrame,
    legacy_core: gpd.GeoDataFrame,
    legacy_core_plus: gpd.GeoDataFrame,
    revised_core: gpd.GeoDataFrame,
    revised_core_plus: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    ordinary = support.loc[support["control_type"].isin(["street", "town"])].copy()
    ordinary_total_area = ordinary.groupby("physical_cell_id")[
        "support_cell_area_m2"
    ].transform("sum")
    ordinary["membership_share"] = (
        ordinary["support_cell_area_m2"] / ordinary_total_area
    )
    series = {
        "district_direct_core": legacy_core.set_index("cell_id")[
            "cell_employment_core"
        ],
        "revised_core": revised_core.set_index("cell_id")["cell_employment_core"],
        "district_direct_core_plus_base": legacy_core_plus.set_index("cell_id")[
            "cell_employment_core_plus_base"
        ],
        "revised_core_plus_base": revised_core_plus.set_index("cell_id")[
            "cell_employment_core_plus_base"
        ],
    }
    for name, values in series.items():
        ordinary[name] = (
            ordinary["physical_cell_id"].map(values).astype(float)
            * ordinary["membership_share"]
        )
    comparison = ordinary.groupby(
        ["district", "accounting_stratum_id", "control_name", "control_type"],
        as_index=False,
    )[list(series)].sum()
    comparison["core_shift_from_district_direct"] = (
        comparison["revised_core"] - comparison["district_direct_core"]
    )
    comparison["core_plus_base_shift_from_district_direct"] = (
        comparison["revised_core_plus_base"]
        - comparison["district_direct_core_plus_base"]
    )
    accounting = (
        matrix.loc[
            matrix["scenario"].eq("base")
            & matrix["industry_code"].isin(OFFICE_CODES)
            & matrix["row_is_official_fine_control"]
        ]
        .groupby("accounting_stratum_id", as_index=False)[
            "control_industry_employment"
        ]
        .sum()
        .rename(
            columns={
                "control_industry_employment": "synthetic_control_core_plus_base_employment"
            }
        )
    )
    comparison = comparison.merge(
        accounting, on="accounting_stratum_id", how="left", validate="one_to_one"
    )
    summary = {
        "ordinary_control_count": int(len(comparison)),
        "core_gross_jobs_shifted_between_ordinary_controls": float(
            comparison["core_shift_from_district_direct"].abs().sum() / 2.0
        ),
        "core_plus_base_gross_jobs_shifted_between_ordinary_controls": float(
            comparison["core_plus_base_shift_from_district_direct"].abs().sum()
            / 2.0
        ),
        "core_controls_gaining_employment": int(
            (comparison["core_shift_from_district_direct"] > 0).sum()
        ),
        "core_controls_losing_employment": int(
            (comparison["core_shift_from_district_direct"] < 0).sum()
        ),
        "core_plus_controls_gaining_employment": int(
            (comparison["core_plus_base_shift_from_district_direct"] > 0).sum()
        ),
        "core_plus_controls_losing_employment": int(
            (comparison["core_plus_base_shift_from_district_direct"] < 0).sum()
        ),
    }
    return comparison, summary


def construct_spatial_allocations(
    cells_with_evidence: gpd.GeoDataFrame,
    support: pd.DataFrame,
    control_industry_matrix: pd.DataFrame,
    legacy_core: gpd.GeoDataFrame,
    legacy_core_plus: gpd.GeoDataFrame,
) -> tuple[
    gpd.GeoDataFrame,
    gpd.GeoDataFrame,
    gpd.GeoDataFrame,
    gpd.GeoDataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, Any],
]:
    """Allocate reconciled control-industry totals within each control support."""

    frame = cells_with_evidence.copy().reset_index(drop=True)
    diagnostics: list[dict[str, Any]] = []
    weight_cache: dict[tuple[str, str], tuple[pd.Series, dict[str, dict[str, Any]]]] = {}

    def weights_for(weighting: str, code: str):
        key = (weighting, code)
        if key not in weight_cache:
            weight_cache[key] = build_control_industry_weights(
                support,
                code,
                WEIGHTING_SCENARIOS[weighting]["shares"],
            )
        return weight_cache[key]

    def allocate(scenario: str, weighting: str, code: str) -> pd.Series:
        weights, realized = weights_for(weighting, code)
        totals = _matrix_totals(control_industry_matrix, scenario, code)
        values = allocate_integer_control_matrix(support, weights, totals)
        diagnostics.extend(
            _control_diagnostic_records(
                support,
                values,
                weights,
                realized,
                totals,
                industry_code=code,
                scenario=scenario,
                weighting_scenario=weighting,
            )
        )
        return values

    support_base = {
        code: allocate("base", "base", code) for code in OFFICE_CODES
    }
    base_physical = _aggregate_to_physical_cells(
        frame,
        support,
        {f"cell_employment_{code}": values for code, values in support_base.items()},
    )
    core = _grid_metadata(base_physical)
    for code in CORE_CODES:
        core[f"cell_employment_{code}"] = base_physical[f"cell_employment_{code}"]
    core["cell_employment_core"] = core[
        [f"cell_employment_{code}" for code in CORE_CODES]
    ].sum(axis=1)
    core["employment_definition"] = "Core office-oriented employment: I + J + M"
    core["control_grain"] = (
        "official fine control by synthetic industry; separate residual overlays"
    )
    core["weighting_scenario"] = "base"
    core["geometry_is_approximate"] = True
    core["boundary_source"] = (
        "OSM 2026-08-19 ordinary controls; restricted 2020 Pudong zone supports"
    )
    core["employment_universe"] = EMPLOYMENT_UNIVERSE
    core["reference_date"] = REFERENCE_DATE
    core["reach_intersection_calculated"] = False

    core_plus_base = _grid_metadata(base_physical)
    core_plus_base["cell_employment_core"] = core["cell_employment_core"]
    for code in SELECTED_72_CODES:
        core_plus_base[f"cell_employment_{code}"] = base_physical[
            f"cell_employment_{code}"
        ]
    core_plus_base["cell_employment_selected_72_base"] = core_plus_base[
        [f"cell_employment_{code}" for code in SELECTED_72_CODES]
    ].sum(axis=1)
    core_plus_base["cell_employment_core_plus_base"] = (
        core_plus_base["cell_employment_core"]
        + core_plus_base["cell_employment_selected_72_base"]
    )
    core_plus_base["employment_definition"] = (
        "Core+ Base: Core I+J+M plus selected 721/723/724/725"
    )
    core_plus_base["control_grain"] = core["control_grain"]
    core_plus_base["weighting_scenario"] = "base"
    core_plus_base["core_is_hard_control"] = True
    core_plus_base["selected_72_district_composition_is_modelled"] = True
    core_plus_base["geometry_is_approximate"] = True
    core_plus_base["boundary_source"] = core["boundary_source"]
    core_plus_base["employment_universe"] = EMPLOYMENT_UNIVERSE
    core_plus_base["reference_date"] = REFERENCE_DATE
    core_plus_base["reach_intersection_calculated"] = False

    composition = _grid_metadata(base_physical)
    composition["cell_employment_core"] = core["cell_employment_core"]
    for scenario in SCENARIOS:
        selected_physical: dict[str, pd.Series] = {}
        for code in SELECTED_72_CODES:
            support_values = (
                support_base[code]
                if scenario == "base"
                else allocate(scenario, "base", code)
            )
            selected_physical[code] = _aggregate_to_physical_cells(
                frame,
                support,
                {"value": support_values},
            )["value"]
            composition[f"cell_employment_{code}_{scenario}"] = selected_physical[
                code
            ]
        composition[f"cell_employment_selected_72_{scenario}"] = composition[
            [f"cell_employment_{code}_{scenario}" for code in SELECTED_72_CODES]
        ].sum(axis=1)
        composition[f"cell_employment_core_plus_{scenario}"] = (
            composition["cell_employment_core"]
            + composition[f"cell_employment_selected_72_{scenario}"]
        )
    composition["cell_employment_core_plus_low_minus_base"] = (
        composition["cell_employment_core_plus_low_office_intensity"]
        - composition["cell_employment_core_plus_base"]
    )
    composition["cell_employment_core_plus_high_minus_base"] = (
        composition["cell_employment_core_plus_high_office_intensity"]
        - composition["cell_employment_core_plus_base"]
    )
    composition["core_is_hard_control"] = True
    composition["selected_72_district_composition_is_modelled"] = True
    composition["control_grain"] = core["control_grain"]
    composition["geometry_is_approximate"] = True
    composition["boundary_source"] = core["boundary_source"]
    composition["employment_universe"] = EMPLOYMENT_UNIVERSE
    composition["reference_date"] = REFERENCE_DATE
    composition["reach_intersection_calculated"] = False

    weighting = _grid_metadata(base_physical)
    for weighting_scenario in WEIGHTING_SCENARIOS:
        if weighting_scenario == "base":
            physical = base_physical
        else:
            support_values = {
                code: allocate("base", weighting_scenario, code)
                for code in OFFICE_CODES
            }
            physical = _aggregate_to_physical_cells(
                frame,
                support,
                {
                    f"cell_employment_{code}": values
                    for code, values in support_values.items()
                },
            )
        weighting[f"cell_employment_core_plus_{weighting_scenario}"] = physical[
            [f"cell_employment_{code}" for code in OFFICE_CODES]
        ].sum(axis=1)
    weighting["cell_employment_building_volume_dominant_minus_base"] = (
        weighting["cell_employment_core_plus_building_volume_dominant"]
        - weighting["cell_employment_core_plus_base"]
    )
    weighting["cell_employment_workplace_evidence_emphasis_minus_base"] = (
        weighting["cell_employment_core_plus_workplace_evidence_emphasis"]
        - weighting["cell_employment_core_plus_base"]
    )
    weighting["control_grain"] = core["control_grain"]
    weighting["geometry_is_approximate"] = True
    weighting["employment_universe"] = EMPLOYMENT_UNIVERSE
    weighting["reference_date"] = REFERENCE_DATE
    weighting["reach_intersection_calculated"] = False

    diagnostic_table = pd.DataFrame(diagnostics)
    if (diagnostic_table["reconciliation_difference"] != 0).any():
        raise RuntimeError("At least one control-industry cell allocation failed identity.")
    if diagnostic_table["uniform_fallback_used"].any():
        raise RuntimeError("At least one control lacked all workplace evidence components.")

    control_shift, shift_summary = _build_control_shift_comparison(
        support,
        control_industry_matrix,
        legacy_core,
        legacy_core_plus,
        core,
        core_plus_base,
    )
    concentration = pd.DataFrame(
        [
            _concentration_record(
                "district_direct_base",
                legacy_core_plus["cell_employment_core_plus_base"],
            ),
            _concentration_record(
                "fine_control_base",
                core_plus_base["cell_employment_core_plus_base"],
            ),
            *[
                _concentration_record(
                    f"fine_control_{scenario}",
                    weighting[f"cell_employment_core_plus_{scenario}"],
                )
                for scenario in WEIGHTING_SCENARIOS
                if scenario != "base"
            ],
        ]
    )
    base_concentration = concentration.loc[
        concentration["allocation_architecture"].eq("district_direct_base")
    ].iloc[0]
    for column in (
        "gini_cell_employment",
        "top_1_percent_cell_employment_share",
        "maximum_cell_employment",
        "cell_hhi",
    ):
        concentration[f"change_from_district_direct_{column}"] = (
            concentration[column] - base_concentration[column]
        )

    summary = {
        "schema_version": 2,
        "reference_date": REFERENCE_DATE,
        "employment_universe": EMPLOYMENT_UNIVERSE,
        "spatial_scope": "eight audited reach-relevant districts",
        "spatial_scope_districts": list(PRIORITY_DISTRICTS),
        "city_core_hard_control": CORE_EMPLOYMENT,
        "city_core_plus_control_each_scenario": CORE_PLUS_EMPLOYMENT,
        "priority_grid_cell_count": int(len(frame)),
        "fine_accounting_control_count": 116,
        "ordinary_control_count": 113,
        "pudong_functional_zone_count": 3,
        "district_residual_overlay_count": 8,
        "priority_core_allocated_employment": int(core["cell_employment_core"].sum()),
        "priority_core_plus_allocated_employment": {
            scenario: int(
                composition[f"cell_employment_core_plus_{scenario}"].sum()
            )
            for scenario in SCENARIOS
        },
        "priority_core_plus_weighting_sensitivity": {
            scenario: int(weighting[f"cell_employment_core_plus_{scenario}"].sum())
            for scenario in WEIGHTING_SCENARIOS
        },
        "weighting_sensitivity_jobs_relocated_from_base": {
            scenario: float(
                (
                    weighting[f"cell_employment_core_plus_{scenario}"]
                    - weighting["cell_employment_core_plus_base"]
                ).abs().sum()
                / 2.0
            )
            for scenario in WEIGHTING_SCENARIOS
            if scenario != "base"
        },
        "composition_sensitivity_jobs_relocated_from_base": {
            scenario: float(
                (
                    composition[f"cell_employment_core_plus_{scenario}"]
                    - composition["cell_employment_core_plus_base"]
                ).abs().sum()
                / 2.0
            )
            for scenario in SCENARIOS
            if scenario != "base"
        },
        "component_shares": COMPONENT_SHARES,
        "weighting_scenarios": WEIGHTING_SCENARIOS,
        "building_function_relevance": FUNCTION_RELEVANCE,
        "poi_relevance": POI_RELEVANCE,
        "allocation_method": (
            "official fine-control totals crossed with district industries by maximum-"
            "entropy RAS/IPF and exact controlled rounding; uncapped evidence mixtures "
            "then normalized within each accounting control"
        ),
        "control_industry_matrix_method": (
            "maximum-entropy independence prior, bulletin-compatible finance residual "
            "constraints, RAS/IPF, deterministic integer margin reconciliation"
        ),
        "fine_controls_are_hard_geographic_controls": True,
        "pudong_functional_zones_counted_once_as_separate_strata": True,
        "restricted_zone_geometry_redistributed": False,
        "control_shift_from_district_direct": shift_summary,
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
            "Ordinary supports inherit audited approximate OSM street/town boundaries; "
            "three Pudong census-zone supports use restricted approximate 2020 statistical "
            "polygons and are published only as combined non-reconstructive cell totals."
        ),
    }
    return (
        core,
        core_plus_base,
        composition,
        weighting,
        diagnostic_table,
        control_shift,
        concentration,
        summary,
    )


def write_source_manifest(
    path: Path,
    *,
    repository_root: Path,
    building_evidence_path: Path,
    general_grid_path: Path,
    district_industry_path: Path,
    subgroup_scenario_path: Path,
    control_crosswalk_path: Path,
    residual_strata_path: Path,
    control_industry_matrix_path: Path,
    district_direct_baseline_path: Path,
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
        {
            "source_id": "official-fine-geographic-controls-2023",
            "source_type": "audited Fifth Economic Census street/town and zone totals",
            "publisher": "Shanghai district statistical authorities",
            "year_or_release": REFERENCE_DATE,
            "url": "per-row publication URLs in the repository crosswalk",
            "repository_or_cache_path": str(
                control_crosswalk_path.relative_to(repository_root)
            ),
            "sha256": sha256_file(control_crosswalk_path),
            "derived_sha256": sha256_file(control_industry_matrix_path),
            "license_or_reuse": "official statistical publications",
            "used_for": "116 exact fine-control row margins in the synthetic industry matrix",
            "reproducible": True,
        },
        {
            "source_id": "audited-district-residual-strata-2023",
            "source_type": "district employment not represented in published fine rows",
            "publisher": "Jinke Gate 1 census reconciliation",
            "year_or_release": REFERENCE_DATE,
            "url": "repository asset with per-district reasons",
            "repository_or_cache_path": str(
                residual_strata_path.relative_to(repository_root)
            ),
            "sha256": sha256_file(residual_strata_path),
            "derived_sha256": "",
            "license_or_reuse": "derived from official statistical publications",
            "used_for": "separate residual rows; prevents excluded finance from being silently forced into fine rows",
            "reproducible": True,
        },
        {
            "source_id": "district-direct-office-allocation-baseline",
            "source_type": "frozen pre-revision comparison baseline",
            "publisher": "Jinke office-employment spatial framework",
            "year_or_release": REFERENCE_DATE,
            "url": "repository asset",
            "repository_or_cache_path": str(
                district_direct_baseline_path.relative_to(repository_root)
            ),
            "sha256": sha256_file(district_direct_baseline_path),
            "derived_sha256": "",
            "license_or_reuse": "derived analytical comparison artifact",
            "used_for": "idempotent comparison against the reviewed district-direct architecture",
            "reproducible": True,
        },
        {
            "source_id": "pudong-zone-statistical-polygons-2020",
            "source_type": "restricted approximate statistical-zone supports",
            "publisher": "Ruiduobao",
            "year_or_release": "approximately 2020",
            "url": "https://map.ruiduobao.com/getGsonDB",
            "repository_or_cache_path": (
                "not committed; reacquire codes 310115501000-310115503000 "
                "using employment_pipeline.sources.acquire_restricted_zone_supports"
            ),
            "sha256": (
                "per-code hashes enforced by employment_pipeline.boundaries"
            ),
            "derived_sha256": "",
            "license_or_reuse": (
                "academic/education reference only; commercial use prohibited; "
                "source geometry not redistributed"
            ),
            "used_for": (
                "temporary within-zone allocation; only combined non-reconstructive "
                "physical-cell employment totals are committed"
            ),
            "reproducible": "reproducible acquisition subject to provider availability",
        },
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def write_spatial_outputs(
    repository_root: Path,
    *,
    osm_pbf_path: Path | None = None,
    restricted_zone_directory: Path | None = None,
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
    control_crosswalk = (
        repository_root / "data/employment/manifests/control-crosswalk-2023.csv"
    )
    residual_strata = (
        repository_root / "data/employment/manifests/residual-strata.csv"
    )
    evidence_path = intermediate / "building-function-evidence-100m.parquet"
    quality_path = intermediate / "building-evidence-quality.json"
    district_direct_baseline_path = (
        intermediate / "district-direct-baseline-100m.parquet"
    )
    _require_hash(
        district_direct_baseline_path,
        DISTRICT_DIRECT_BASELINE_SHA256,
        "District-direct office allocation baseline",
    )
    if restricted_zone_directory is None:
        raise FileNotFoundError(
            "Provide --restricted-zone-directory with the three hash-pinned Pudong "
            "zone supports; source geometry will not be committed."
        )
    restricted_zone_directory = restricted_zone_directory.resolve()
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
    district_direct = pd.read_parquet(district_direct_baseline_path)
    if district_direct["cell_id"].duplicated().any() or set(
        district_direct["cell_id"]
    ) != set(cells["cell_id"]):
        raise RuntimeError("District-direct baseline does not match the physical lattice.")
    legacy_metadata = _grid_metadata(cells)
    legacy_core = legacy_metadata.merge(
        district_direct[["cell_id", "cell_employment_core"]],
        on="cell_id",
        validate="one_to_one",
    )
    legacy_core_plus = legacy_metadata.merge(
        district_direct[["cell_id", "cell_employment_core_plus_base"]],
        on="cell_id",
        validate="one_to_one",
    )
    legacy_core = gpd.GeoDataFrame(legacy_core, geometry="geometry", crs=cells.crs)
    legacy_core_plus = gpd.GeoDataFrame(
        legacy_core_plus, geometry="geometry", crs=cells.crs
    )
    from office_employment_pipeline.validation_maps import evaluate_clusters

    legacy_cluster_path = intermediate / "district-direct-cluster-validation.csv"
    evaluate_clusters(
        legacy_core_plus,
        allocation_architecture="district_direct_base",
    ).to_csv(legacy_cluster_path, index=False)
    _require_hash(
        district_industry, DISTRICT_INDUSTRY_SHA256, "District-industry controls"
    )
    _require_hash(
        subgroup_scenarios, CORE_PLUS_SCENARIO_SHA256, "Core+ district scenarios"
    )
    district_industry_frame = pd.read_csv(
        district_industry, dtype={"industry_code": str}
    )
    subgroup_scenario_frame = pd.read_csv(
        subgroup_scenarios, dtype={"industry_code": str}
    )
    city_core = int(
        district_industry_frame.loc[
            district_industry_frame["industry_code"].isin(CORE_CODES),
            "district_industry_employment",
        ].sum()
    )
    city_core_plus = {
        scenario: city_core
        + int(
            subgroup_scenario_frame.loc[
                subgroup_scenario_frame["scenario"].eq(scenario),
                "scenario_district_subgroup_employment",
            ].sum()
        )
        for scenario in SCENARIOS
    }
    if city_core != CORE_EMPLOYMENT or set(city_core_plus.values()) != {
        CORE_PLUS_EMPLOYMENT
    }:
        raise RuntimeError("City Core or Core+ controls changed.")
    fine_controls_frame = pd.read_csv(
        control_crosswalk,
        dtype={"accounting_stratum_id": str, "official_control_code_2023": str},
    )
    residual_frame = pd.read_csv(residual_strata, dtype={"residual_id": str})
    control_matrix, matrix_diagnostics = construct_control_industry_matrix(
        fine_controls_frame,
        residual_frame,
        district_industry_frame,
        subgroup_scenario_frame,
        priority_districts=PRIORITY_DISTRICTS,
    )
    support, support_quality = build_control_support_cells(
        general_grid,
        cells,
        control_crosswalk,
        residual_strata,
        restricted_zone_directory,
    )
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
            **support_quality,
        }
    )
    quality_path.write_text(
        json.dumps(quality, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (
        core,
        core_plus,
        sensitivity,
        weighting_sensitivity,
        diagnostics,
        control_shift,
        concentration,
        summary,
    ) = construct_spatial_allocations(
        cells,
        support,
        control_matrix,
        legacy_core,
        legacy_core_plus,
    )
    summary["source_quality"] = quality
    summary["input_sha256"] = {
        "general_employment_grid": sha256_file(general_grid),
        "building_function_evidence": sha256_file(evidence_path),
        "district_industry_controls": sha256_file(district_industry),
        "core_plus_scenarios": sha256_file(subgroup_scenarios),
        "fine_control_crosswalk": sha256_file(control_crosswalk),
        "residual_strata": sha256_file(residual_strata),
        "district_direct_office_baseline": sha256_file(
            district_direct_baseline_path
        ),
    }

    core_path = outputs / "core-employment-grid-100m.parquet"
    core_plus_path = outputs / "core-plus-base-employment-grid-100m.parquet"
    sensitivity_path = outputs / "core-plus-sensitivity-grid-100m.parquet"
    weighting_sensitivity_path = (
        outputs / "core-plus-weighting-sensitivity-grid-100m.parquet"
    )
    diagnostics_path = outputs / "allocation-diagnostics.csv"
    control_shift_path = outputs / "control-shift-comparison.csv"
    concentration_path = outputs / "concentration-comparison.csv"
    control_matrix_path = intermediate / "control-industry-matrix-2023.csv"
    matrix_diagnostics_path = intermediate / "control-industry-reconciliation.csv"
    summary_path = outputs / "spatial-allocation-summary.json"
    source_manifest_path = manifests / "source-manifest.csv"
    core.to_parquet(core_path, index=False, compression="zstd")
    core_plus.to_parquet(core_plus_path, index=False, compression="zstd")
    sensitivity.to_parquet(sensitivity_path, index=False, compression="zstd")
    weighting_sensitivity.to_parquet(
        weighting_sensitivity_path, index=False, compression="zstd"
    )
    diagnostics.to_csv(diagnostics_path, index=False)
    control_shift.to_csv(control_shift_path, index=False)
    concentration.to_csv(concentration_path, index=False)
    control_matrix.to_csv(control_matrix_path, index=False)
    matrix_diagnostics.to_csv(matrix_diagnostics_path, index=False)
    summary["output_sha256"] = {
        "core_grid": sha256_file(core_path),
        "core_plus_base_grid": sha256_file(core_plus_path),
        "core_plus_sensitivity_grid": sha256_file(sensitivity_path),
        "core_plus_weighting_sensitivity_grid": sha256_file(
            weighting_sensitivity_path
        ),
        "allocation_diagnostics": sha256_file(diagnostics_path),
        "control_shift_comparison": sha256_file(control_shift_path),
        "concentration_comparison": sha256_file(concentration_path),
        "control_industry_matrix": sha256_file(control_matrix_path),
        "control_industry_reconciliation": sha256_file(matrix_diagnostics_path),
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
        control_crosswalk_path=control_crosswalk,
        residual_strata_path=residual_strata,
        control_industry_matrix_path=control_matrix_path,
        district_direct_baseline_path=district_direct_baseline_path,
    )
    return {
        "spatial_root": spatial_root,
        "maps": maps,
        "core": core_path,
        "core_plus": core_plus_path,
        "sensitivity": sensitivity_path,
        "weighting_sensitivity": weighting_sensitivity_path,
        "diagnostics": diagnostics_path,
        "control_shift": control_shift_path,
        "concentration": concentration_path,
        "control_matrix": control_matrix_path,
        "matrix_diagnostics": matrix_diagnostics_path,
        "legacy_clusters": legacy_cluster_path,
        "summary": summary_path,
        "source_manifest": source_manifest_path,
        "building_evidence": evidence_path,
        "building_quality": quality_path,
    }
