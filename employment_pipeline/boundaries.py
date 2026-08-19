"""Strict control-geometry loading, diagnostics, and reach-edge review selection."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from .config import (
    ANALYSIS_CRS,
    OFFICIAL_ARCGIS_MAP_URL,
    OFFICIAL_MAP_BASE_SHA256,
    OFFICIAL_MAP_EXPORT_BBOX_WGS84,
    OFFICIAL_MAP_EXPORT_PIXELS,
    OFFICIAL_MAP_LABEL_SHA256,
    OFFICIAL_MAP_OVERLAY_SHA256,
    OFFICIAL_MAP_REVIEW_DATE,
    OFFICIAL_MAP_URL,
    OSM_LICENSE,
    OSM_SNAPSHOT_DATE,
    OSM_SOURCE_URL,
    RESTRICTED_ZONE_API,
    RESTRICTED_ZONE_CODES,
)
from .manifests import sha256_file

ZONE_EXPECTED_HASHES = {
    "310115501000": "9ca089bb740650ee47446e430c7e8f29c15b06516d414203c585fce8414f806f",
    "310115502000": "11cd1685641f79c3bd0b658e2a160d8dc7c60a53d8773111b9c057aedb367d78",
    "310115503000": "a2e2206cda63c922f963b51a462ad62d09bfeaccc7d8c03427fd42f1407e98c4",
}

ZONE_EXPECTED_AREAS_KM2 = {
    "310115501000": 22.97572364836535,
    "310115502000": 19.475692467276037,
    "310115503000": 18.30313339122193,
}

ZONE_PLANNING_AREA_KM2 = {
    "310115501000": 17.11,
    "310115502000": 29.38,
    "310115503000": 28.26,
}


def _geometry_digest(geometry: Any) -> str:
    return hashlib.sha256(shapely.to_wkb(geometry, hex=False)).hexdigest()


def load_ordinary_controls(
    boundary_path: Path,
    crosswalk_path: Path,
) -> gpd.GeoDataFrame:
    controls = pd.read_csv(
        crosswalk_path,
        dtype={"official_control_code_2023": "string", "accounting_stratum_id": "string"},
    )
    ordinary = controls.loc[controls["control_type"] != "functional_zone"].copy()
    geometry = gpd.read_file(boundary_path)
    if geometry.crs is None:
        raise ValueError("OSM control layer has no CRS.")
    geometry["official_control_code_2023"] = geometry[
        "official_control_code_2023"
    ].astype("string")
    expected = set(ordinary["official_control_code_2023"])
    actual = set(geometry["official_control_code_2023"])
    if expected != actual or len(geometry) != 113:
        raise ValueError(
            f"OSM geometry/cross-walk mismatch: missing={sorted(expected-actual)}, "
            f"unexpected={sorted(actual-expected)}"
        )
    merged = geometry.merge(
        ordinary,
        on=["district", "official_control_code_2023", "official_control_name_2023"],
        how="inner",
        validate="one_to_one",
        suffixes=("_geometry", ""),
    )
    if len(merged) != 113 or merged["accounting_stratum_id"].duplicated().any():
        raise ValueError("Ordinary geometry join is not one-to-one.")
    merged["boundary_source"] = "OpenStreetMap admin_level=8 relation"
    merged["boundary_source_url"] = OSM_SOURCE_URL
    merged["boundary_source_vintage"] = OSM_SNAPSHOT_DATE
    merged["boundary_license"] = OSM_LICENSE
    merged["restricted_geometry"] = False
    return gpd.GeoDataFrame(merged, geometry="geometry", crs=geometry.crs).to_crs(
        ANALYSIS_CRS
    )


def load_restricted_zone_controls(
    zone_directory: Path,
    crosswalk_path: Path,
) -> gpd.GeoDataFrame:
    controls = pd.read_csv(
        crosswalk_path,
        dtype={"official_control_code_2023": "string", "accounting_stratum_id": "string"},
    )
    zones = controls.loc[controls["control_type"] == "functional_zone"].copy()
    frames: list[gpd.GeoDataFrame] = []
    for code in RESTRICTED_ZONE_CODES:
        path = zone_directory / f"{code}-ruiduobao-2020.geojson"
        if not path.is_file():
            raise FileNotFoundError(
                f"Restricted zone geometry is unavailable: {path}. Follow "
                "data/employment/README.md; do not commit the acquired source geometry."
            )
        observed_hash = sha256_file(path)
        if observed_hash != ZONE_EXPECTED_HASHES[code]:
            raise ValueError(f"Restricted zone {code} hash changed: {observed_hash}")
        frame = gpd.read_file(path)
        if frame.crs is None or len(frame) != 1:
            raise ValueError(f"Restricted zone {code} must contain one georeferenced feature.")
        frame["code"] = frame["code"].astype("string")
        if frame["code"].iloc[0] != code:
            raise ValueError(f"Restricted zone file {path.name} contains the wrong code.")
        frames.append(frame[["code", "name", "geometry"]])
    geometry = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    geometry = geometry.rename(
        columns={"code": "official_control_code_2023", "name": "zone_source_name"}
    )
    merged = geometry.merge(
        zones,
        on="official_control_code_2023",
        how="inner",
        validate="one_to_one",
    )
    mismatch = merged["zone_source_name"] != merged["official_control_name_2023"]
    if mismatch.any():
        raise ValueError(
            "Restricted-zone names do not match census controls: "
            + str(merged.loc[mismatch, ["zone_source_name", "official_control_name_2023"]])
        )
    merged["boundary_source"] = "Ruiduobao 2020 statistical polygon"
    merged["boundary_source_url"] = RESTRICTED_ZONE_API
    merged["boundary_source_vintage"] = "approximately 2020"
    merged["boundary_license"] = (
        "academic/education reference only; commercial use prohibited"
    )
    merged["restricted_geometry"] = True
    metric = gpd.GeoDataFrame(merged, geometry="geometry", crs=geometry.crs).to_crs(
        ANALYSIS_CRS
    )
    for row in metric.itertuples(index=False):
        area = float(row.geometry.area / 1_000_000.0)
        expected = ZONE_EXPECTED_AREAS_KM2[row.official_control_code_2023]
        if abs(area - expected) > 1e-6:
            raise ValueError(
                f"Restricted zone {row.official_control_code_2023} area changed: {area} km²"
            )
    return metric


def load_all_controls(
    ordinary_boundary_path: Path,
    crosswalk_path: Path,
    restricted_zone_directory: Path,
) -> gpd.GeoDataFrame:
    ordinary = load_ordinary_controls(ordinary_boundary_path, crosswalk_path)
    zones = load_restricted_zone_controls(restricted_zone_directory, crosswalk_path)
    all_controls = gpd.GeoDataFrame(
        pd.concat([ordinary, zones], ignore_index=True),
        geometry="geometry",
        crs=ANALYSIS_CRS,
    )
    if len(all_controls) != 116 or all_controls["accounting_stratum_id"].duplicated().any():
        raise ValueError("Expected 116 unique accounting supports.")
    if all_controls.geometry.isna().any() or all_controls.geometry.is_empty.any():
        raise ValueError("A control support is empty.")
    if not all_controls.geometry.is_valid.all():
        bad = all_controls.loc[~all_controls.geometry.is_valid, "accounting_stratum_id"]
        raise ValueError(f"Invalid control supports: {bad.tolist()}")
    return all_controls


def topology_diagnostics(
    controls_metric: gpd.GeoDataFrame,
    district_reference_path: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Record, but do not conceal, differences from the older district reference."""

    districts = gpd.read_file(district_reference_path).to_crs(ANALYSIS_CRS)
    ordinary = controls_metric.loc[
        controls_metric["control_type"] != "functional_zone"
    ].copy()
    rows: list[dict[str, Any]] = []
    for district_name, group in ordinary.groupby("district", sort=True):
        union = group.geometry.union_all()
        summed_area = float(group.geometry.area.sum())
        union_area = float(union.area)
        overlap = max(0.0, summed_area - union_area)
        parent_rows = districts.loc[districts["district"] == district_name]
        if len(parent_rows) == 1:
            parent = parent_rows.geometry.iloc[0]
            outside = float(union.difference(parent).area)
            parent_gap = float(parent.difference(union).area)
            parent_source = "geoBoundaries 2017 ADM3 (diagnostic only)"
        else:
            outside = np.nan
            parent_gap = np.nan
            parent_source = "unavailable"
        rows.append(
            {
                "district": district_name,
                "ordinary_control_count": int(len(group)),
                "sum_control_area_km2": summed_area / 1_000_000.0,
                "union_area_km2": union_area / 1_000_000.0,
                "within_district_overlap_m2": overlap,
                "parent_reference": parent_source,
                "area_outside_parent_reference_m2": outside,
                "gap_inside_parent_reference_m2": parent_gap,
                "empty_geometry_count": int(group.geometry.is_empty.sum()),
                "invalid_geometry_count": int((~group.geometry.is_valid).sum()),
                "duplicate_code_count": int(group["accounting_stratum_id"].duplicated().sum()),
                "min_control_area_km2": float(group.geometry.area.min() / 1_000_000.0),
                "max_control_area_km2": float(group.geometry.area.max() / 1_000_000.0),
            }
        )
    per_district = pd.DataFrame(rows)
    geometry_hashes = controls_metric.geometry.map(_geometry_digest)
    summary = {
        "analysis_crs": ANALYSIS_CRS,
        "control_count": int(len(controls_metric)),
        "ordinary_control_count": int(len(ordinary)),
        "functional_zone_count": int((controls_metric["control_type"] == "functional_zone").sum()),
        "all_valid": bool(controls_metric.geometry.is_valid.all()),
        "no_empty_geometries": bool(not controls_metric.geometry.is_empty.any()),
        "duplicate_accounting_strata": int(controls_metric["accounting_stratum_id"].duplicated().sum()),
        "duplicate_geometry_hashes": int(geometry_hashes.duplicated().sum()),
        "ordinary_within_district_overlap_m2": float(
            per_district["within_district_overlap_m2"].sum()
        ),
        "zone_overlap_is_intentional": True,
        "parent_containment_note": (
            "The available repository parent layer is geoBoundaries 2017 and is used only "
            "as a cross-vintage diagnostic; differences do not modify OSM controls."
        ),
    }
    return per_district, summary


def controls_needing_official_map_review(
    controls_metric: gpd.GeoDataFrame,
    reach_50_geometry: Any,
    *,
    approach_distance_metres: float = 500.0,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for row in controls_metric.itertuples(index=False):
        area = float(row.geometry.area)
        inside = float(row.geometry.intersection(reach_50_geometry).area)
        share = inside / area if area > 0 else 0.0
        distance = float(row.geometry.boundary.distance(reach_50_geometry.boundary))
        partial = 1e-9 < share < 1.0 - 1e-9
        approaches = distance <= approach_distance_metres
        if partial or approaches:
            records.append(
                {
                    "district": row.district,
                    "accounting_stratum_id": row.accounting_stratum_id,
                    "control": row.official_control_name_2023,
                    "control_type": row.control_type,
                    "boundary_source": row.boundary_source,
                    "reach_intersection_area_share": share,
                    "distance_to_50min_boundary_m": distance,
                    "review_reason": (
                        "partially intersected"
                        if partial
                        else f"within {approach_distance_metres:.0f} m of boundary"
                    ),
                    "source_map": OFFICIAL_MAP_URL,
                    "source_map_service": OFFICIAL_ARCGIS_MAP_URL,
                    "review_date": OFFICIAL_MAP_REVIEW_DATE,
                    "review_status": "pending",
                    "discrepancy_description": "",
                    "could_materially_change_reach_employment": "pending",
                }
            )
    return pd.DataFrame(records).sort_values(
        ["district", "accounting_stratum_id"]
    ).reset_index(drop=True)


def record_official_map_review(candidates: pd.DataFrame) -> pd.DataFrame:
    """Attach the completed 2026-08-19 visual review to reach-relevant controls.

    The reviewed overlay used the official SHMAP_D/LAN export over bbox
    121.33,31.015,121.83,31.325 at 4096x2540 pixels. ``pass`` means no visible
    material contradiction at that display precision; it is not a claim that OSM is
    the government's accounting boundary.
    """

    review = candidates.copy()
    zone = review["control_type"] == "functional_zone"
    review.loc[~zone, "review_status"] = "pass"
    review.loc[~zone, "discrepancy_description"] = (
        "No material displacement visible against official SHMAP_D/LAN road, water, "
        "and named-place context at the reviewed scale. Pass means no visible "
        "contradiction, not official-boundary equivalence."
    )
    review.loc[~zone, "could_materially_change_reach_employment"] = "no"
    review.loc[zone, "review_status"] = "fail"
    review.loc[zone, "discrepancy_description"] = (
        "The accounting-aligned 2020 statistical support differs in area/scope from "
        "the authoritative same-name planning scope; no official feature vector is "
        "available, so the equivalence cannot pass visual validation."
    )
    review.loc[zone, "could_materially_change_reach_employment"] = "yes"
    review["reviewer"] = "Codex visual audit for Jinke employment benchmark v1"
    review["official_export_bbox_wgs84"] = OFFICIAL_MAP_EXPORT_BBOX_WGS84
    review["official_export_pixels"] = OFFICIAL_MAP_EXPORT_PIXELS
    review["official_base_sha256"] = OFFICIAL_MAP_BASE_SHA256
    review["official_label_sha256"] = OFFICIAL_MAP_LABEL_SHA256
    review["review_overlay_sha256"] = OFFICIAL_MAP_OVERLAY_SHA256
    review["screenshot_redistributed"] = False
    review["review_limitation"] = (
        "The official display service is validation cartography, not a queryable "
        "street/town feature layer. Quantified boundary displacement sensitivity is "
        "therefore retained."
    )
    return review


def area_matched_planning_interpretation(
    zone_geometry: Any,
    target_area_km2: float,
) -> Any:
    """Create a disclosed morphology sensitivity, never an official boundary."""

    target = target_area_km2 * 1_000_000.0
    current = float(zone_geometry.area)
    if abs(current - target) < 1.0:
        return zone_geometry
    if target > current:
        low, high = 0.0, 10_000.0
    else:
        low, high = -10_000.0, 0.0
    for _ in range(80):
        mid = (low + high) / 2.0
        candidate = zone_geometry.buffer(mid)
        area = float(candidate.area)
        if area < target:
            low = mid
        else:
            high = mid
    result = zone_geometry.buffer((low + high) / 2.0)
    if result.is_empty or not result.is_valid:
        raise RuntimeError("Area-matched planning sensitivity produced invalid geometry.")
    return result
