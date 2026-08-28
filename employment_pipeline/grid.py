"""Common 100 m accounting-control grid and independent workplace predictors."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject

from .config import ANALYSIS_CRS, GRID_SIZE_METRES, POI_CATEGORY_RULES

POI_COLUMNS = (
    "poi_business_finance",
    "poi_industry_logistics",
    "poi_education_research",
    "poi_retail_hospitality",
    "poi_health_public",
    "poi_other_economic",
)


def build_control_grid(controls_metric: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Clip one common EPSG:32651 100 m lattice to every accounting support."""

    if controls_metric.crs is None or controls_metric.crs.to_string() != ANALYSIS_CRS:
        raise ValueError(f"Control geometries must use {ANALYSIS_CRS}.")
    if controls_metric["accounting_stratum_id"].duplicated().any():
        raise ValueError("Accounting strata must be unique before gridding.")
    size = GRID_SIZE_METRES
    frames: list[gpd.GeoDataFrame] = []
    required = [
        "district",
        "accounting_stratum_id",
        "official_control_name_2023",
        "control_type",
        "employment_reconciled",
        "employment_universe",
        "geometry_is_approximate",
        "boundary_source",
        "boundary_source_url",
        "boundary_source_vintage",
        "restricted_geometry",
        "geometry",
    ]
    for control in controls_metric[required].itertuples(index=False):
        geometry = control.geometry
        minx, miny, maxx, maxy = geometry.bounds
        min_col = math.floor(minx / size)
        max_col = math.ceil(maxx / size) - 1
        min_row = math.floor(miny / size)
        max_row = math.ceil(maxy / size) - 1
        cols, rows = np.meshgrid(
            np.arange(min_col, max_col + 1, dtype=np.int32),
            np.arange(min_row, max_row + 1, dtype=np.int32),
        )
        cols = cols.ravel()
        rows = rows.ravel()
        x0 = cols.astype(float) * size
        y0 = rows.astype(float) * size
        squares = shapely.box(x0, y0, x0 + size, y0 + size)
        intersects = shapely.intersects(squares, geometry)
        clipped = shapely.intersection(squares[intersects], geometry)
        areas = shapely.area(clipped)
        keep = areas > 1e-8
        kept_cols = cols[intersects][keep]
        kept_rows = rows[intersects][keep]
        kept_areas = areas[keep]
        frame = gpd.GeoDataFrame(
            {
                "district": control.district,
                "accounting_control": control.accounting_stratum_id,
                "control_name": control.official_control_name_2023,
                "control_type": control.control_type,
                "control_employment": int(control.employment_reconciled),
                "employment_universe": control.employment_universe,
                "grid_col": kept_cols,
                "grid_row": kept_rows,
                "center_x": (kept_cols.astype(float) + 0.5) * size,
                "center_y": (kept_rows.astype(float) + 0.5) * size,
                "cell_area_m2": kept_areas,
                "area_fraction": kept_areas / float(size * size),
                "geometry_is_approximate": bool(control.geometry_is_approximate),
                "boundary_source": control.boundary_source,
                "boundary_source_url": control.boundary_source_url,
                "boundary_source_vintage": control.boundary_source_vintage,
                "restricted_geometry": bool(control.restricted_geometry),
                "residual_treatment": "not residual",
            },
            geometry=clipped[keep],
            crs=controls_metric.crs,
        )
        frames.append(frame)
    grid = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=controls_metric.crs)
    grid["cell_id"] = (
        grid["accounting_control"].astype(str)
        + ":"
        + grid["grid_row"].astype(str)
        + ":"
        + grid["grid_col"].astype(str)
    )
    if grid["cell_id"].duplicated().any():
        raise RuntimeError("A control grid contains duplicate cell IDs.")
    if grid.geometry.is_empty.any() or not grid.geometry.is_valid.all():
        raise RuntimeError("The control grid contains invalid or empty clipped cells.")
    return grid


def add_jrc_nonresidential_volume(
    grid: gpd.GeoDataFrame,
    raster_path: Path,
) -> gpd.GeoDataFrame:
    """Conservatively reproject raw JRC non-residential volume; do not cap it."""

    min_col, max_col = int(grid["grid_col"].min()), int(grid["grid_col"].max())
    min_row, max_row = int(grid["grid_row"].min()), int(grid["grid_row"].max())
    width = max_col - min_col + 1
    height = max_row - min_row + 1
    left = min_col * GRID_SIZE_METRES
    top = (max_row + 1) * GRID_SIZE_METRES
    transform = from_origin(left, top, GRID_SIZE_METRES, GRID_SIZE_METRES)
    destination = np.zeros((height, width), dtype=np.float64)
    with rasterio.open(raster_path) as source:
        if source.crs is None:
            raise ValueError("JRC raster does not declare a CRS.")
        reproject(
            source=rasterio.band(source, 1),
            destination=destination,
            src_transform=source.transform,
            src_crs=source.crs,
            src_nodata=source.nodata,
            dst_transform=transform,
            dst_crs=grid.crs,
            dst_nodata=0,
            resampling=Resampling.sum,
            init_dest_nodata=True,
        )
    destination = np.nan_to_num(destination, nan=0.0, posinf=0.0, neginf=0.0)
    destination = np.clip(destination, 0.0, None)
    array_rows = max_row - grid["grid_row"].to_numpy(dtype=np.int64)
    array_cols = grid["grid_col"].to_numpy(dtype=np.int64) - min_col
    full_cell = destination[array_rows, array_cols]
    output = grid.copy()
    output["jrc_nres_volume_m3"] = (
        full_cell * output["area_fraction"].to_numpy(dtype=float)
    )
    # Floating reproject noise below one millionth of a cubic metre is not data.
    output.loc[output["jrc_nres_volume_m3"] < 1e-6, "jrc_nres_volume_m3"] = 0.0
    return output


def _primary_category(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("primary") or "").strip().lower()
    if hasattr(value, "as_py"):
        return _primary_category(value.as_py())
    return ""


def classify_workplace_category(category: Any) -> str | None:
    normalized = str(category or "").strip().lower()
    if not normalized or normalized in {"nan", "none"}:
        return None
    for group, terms in POI_CATEGORY_RULES.items():
        if any(term in normalized for term in terms):
            return group
    other_terms = (
        "service",
        "office",
        "company",
        "facility",
        "automotive",
        "repair",
        "museum",
        "theater",
        "cinema",
        "sports",
        "entertainment",
        "personal_care",
    )
    if any(term in normalized for term in other_terms):
        return "other_economic"
    return None


def _deduplicate_ordinary_matches(joined: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Assign an edge-overlap POI to one ordinary control; retain zone overlap."""

    ordinary = joined.loc[joined["control_type"] != "functional_zone"].copy()
    zones = joined.loc[joined["control_type"] == "functional_zone"].copy()
    if not ordinary.empty:
        ordinary = ordinary.sort_values(
            ["id", "accounting_stratum_id"], kind="mergesort"
        ).drop_duplicates(subset=["id"], keep="first")
    return gpd.GeoDataFrame(
        pd.concat([ordinary, zones], ignore_index=True),
        geometry="geometry",
        crs=joined.crs,
    )


def add_overture_workplace_predictors(
    grid: gpd.GeoDataFrame,
    controls_metric: gpd.GeoDataFrame,
    places_path: Path,
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    """Add unweighted category-specific Overture confidence totals by cell."""

    places = gpd.read_parquet(places_path)
    if places.empty or places.crs is None:
        raise ValueError("Overture Places cache is empty or lacks a CRS.")
    if "basic_category" in places.columns:
        basic = places["basic_category"].fillna("").astype(str).str.lower()
    elif "categories" in places.columns:
        basic = places["categories"].map(_primary_category)
    else:
        raise ValueError("Overture Places has no usable category field.")
    categories = basic.map(classify_workplace_category)
    confidence = (
        pd.to_numeric(places.get("confidence", 0.5), errors="coerce")
        .fillna(0.5)
        .clip(lower=0.0, upper=1.0)
    )
    selected = places[["id", "geometry"]].copy()
    selected["basic_category"] = basic
    selected["workplace_category"] = categories
    selected["confidence"] = confidence
    selected = selected.loc[selected["workplace_category"].notna()].copy()
    selected = selected.to_crs(controls_metric.crs)
    joined = gpd.sjoin(
        selected,
        controls_metric[
            ["accounting_stratum_id", "district", "control_type", "geometry"]
        ],
        how="inner",
        predicate="within",
    ).drop(columns=["index_right"])
    joined = _deduplicate_ordinary_matches(joined)
    joined["grid_col"] = np.floor(
        joined.geometry.x.to_numpy(dtype=float) / GRID_SIZE_METRES
    ).astype(np.int32)
    joined["grid_row"] = np.floor(
        joined.geometry.y.to_numpy(dtype=float) / GRID_SIZE_METRES
    ).astype(np.int32)
    grouped = (
        joined.groupby(
            ["accounting_stratum_id", "grid_row", "grid_col", "workplace_category"],
            observed=True,
        )["confidence"]
        .sum()
        .unstack(fill_value=0.0)
        .reset_index()
    )
    rename = {
        category: f"poi_{category}"
        for category in (
            "business_finance",
            "industry_logistics",
            "education_research",
            "retail_hospitality",
            "health_public",
            "other_economic",
        )
    }
    grouped = grouped.rename(columns=rename)
    for column in POI_COLUMNS:
        if column not in grouped:
            grouped[column] = 0.0
    output = grid.merge(
        grouped[
            ["accounting_stratum_id", "grid_row", "grid_col", *POI_COLUMNS]
        ].rename(columns={"accounting_stratum_id": "accounting_control"}),
        on=["accounting_control", "grid_row", "grid_col"],
        how="left",
        validate="one_to_one",
    )
    output = gpd.GeoDataFrame(output, geometry="geometry", crs=grid.crs)
    output[list(POI_COLUMNS)] = output[list(POI_COLUMNS)].fillna(0.0)
    output["overture_total_intensity"] = output[list(POI_COLUMNS)].sum(axis=1)
    diagnostics = {
        "input_places": int(len(places)),
        "workplace_relevant_places": int(len(selected)),
        "control_place_matches": int(len(joined)),
        "ordinary_matches_after_edge_deduplication": int(
            (joined["control_type"] != "functional_zone").sum()
        ),
        "functional_zone_overlap_matches": int(
            (joined["control_type"] == "functional_zone").sum()
        ),
        "positive_cells_by_category": {
            column: int((output[column] > 0).sum()) for column in POI_COLUMNS
        },
        "poi_weighting": "sum of source confidence; no category multiplier",
    }
    return output, diagnostics


def _names_text(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    pieces = [str(value.get("primary") or "")]
    common = value.get("common")
    if isinstance(common, dict):
        pieces.extend(str(item) for item in common.values())
    elif isinstance(common, list):
        pieces.extend(str(item) for item in common)
    return " ".join(pieces)


def _address_text(value: Any) -> str:
    if not isinstance(value, (list, tuple, np.ndarray)):
        return ""
    pieces: list[str] = []
    for item in value:
        if isinstance(item, dict):
            pieces.extend(str(item.get(key) or "") for key in ("freeform", "locality"))
        else:
            pieces.append(str(item))
    return " ".join(pieces)


def investigate_zone_attribution(places_path: Path) -> pd.DataFrame:
    """Test whether release Places independently identify each census zone."""

    places = gpd.read_parquet(places_path)
    text = (
        places.get("names", pd.Series(index=places.index, dtype=object)).map(_names_text)
        + " "
        + places.get("addresses", pd.Series(index=places.index, dtype=object)).map(
            _address_text
        )
    )
    rules = (
        (
            "310115501000",
            "中国（上海）自由贸易试验区（保税片区）",
            r"外高桥保税|Waigaoqiao Free Trade|Waigaoqiao Bonded|浦东机场综合保税|洋山港保税",
        ),
        (
            "310115502000",
            "金桥经济技术开发区",
            r"金桥经济技术开发区|金桥开发区|Jinqiao Economic|Jinqiao Development",
        ),
        (
            "310115503000",
            "张江高科技园区",
            r"张江高科技园区|张江高新区|Zhangjiang Hi-?Tech Park|Zhangjiang High-?Tech Park",
        ),
    )
    rows = []
    for code, name, pattern in rules:
        matched = text.str.contains(pattern, case=False, regex=True, na=False)
        rows.append(
            {
                "accounting_stratum_id": code,
                "control_name": name,
                "attributed_place_count": int(matched.sum()),
                "attribution_rule": pattern,
                "sufficient_for_central_support": False,
                "decision": (
                    "insufficient coverage and no employment-by-establishment weights; "
                    "use the separately acquired 2020 statistical support"
                ),
            }
        )
    return pd.DataFrame(rows)
