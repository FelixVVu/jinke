"""Build the 100 m grid and derive the three spatial economic proxies."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import geopandas as gpd
import h5py
import numpy as np
import pandas as pd
import rasterio
import shapely
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject

from .config import (
    ANALYSIS_CRS,
    ECONOMIC_POI_RULES,
    GRID_SIZE_METRES,
    SCENARIOS,
    VIIRS_QUALITY_VARIABLE,
    VIIRS_RADIANCE_VARIABLE,
)


def build_100m_grid(districts_metric: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Create a common 100 m lattice and clip each cell to its district."""

    if districts_metric.crs is None or not districts_metric.crs.is_projected:
        raise ValueError("Districts must use a projected metric CRS before gridding.")
    grid_size = GRID_SIZE_METRES
    total_bounds = districts_metric.total_bounds
    origin_x = math.floor(total_bounds[0] / grid_size) * grid_size
    origin_y = math.floor(total_bounds[1] / grid_size) * grid_size
    frames: list[gpd.GeoDataFrame] = []

    for district_row in districts_metric[["district", "geometry"]].itertuples(index=False):
        district = district_row.district
        geometry = district_row.geometry
        minx, miny, maxx, maxy = geometry.bounds
        min_col = math.floor((minx - origin_x) / grid_size)
        max_col = math.ceil((maxx - origin_x) / grid_size) - 1
        min_row = math.floor((miny - origin_y) / grid_size)
        max_row = math.ceil((maxy - origin_y) / grid_size) - 1
        cols, rows = np.meshgrid(
            np.arange(min_col, max_col + 1, dtype=np.int32),
            np.arange(min_row, max_row + 1, dtype=np.int32),
        )
        cols = cols.ravel()
        rows = rows.ravel()
        x0 = origin_x + cols * grid_size
        y0 = origin_y + rows * grid_size
        squares = shapely.box(x0, y0, x0 + grid_size, y0 + grid_size)
        intersects = shapely.intersects(squares, geometry)
        if not intersects.any():
            raise RuntimeError(f"No grid cells intersect district {district}.")
        cols = cols[intersects]
        rows = rows[intersects]
        squares = squares[intersects]
        clipped = shapely.intersection(squares, geometry)
        areas = shapely.area(clipped)
        keep = areas > 1e-8
        frame = gpd.GeoDataFrame(
            {
                "district": district,
                "grid_col": cols[keep],
                "grid_row": rows[keep],
                "center_x": origin_x + (cols[keep] + 0.5) * grid_size,
                "center_y": origin_y + (rows[keep] + 0.5) * grid_size,
                "cell_area_m2": areas[keep],
                "area_fraction": areas[keep] / float(grid_size * grid_size),
            },
            geometry=clipped[keep],
            crs=districts_metric.crs,
        )
        frames.append(frame)

    grid = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=districts_metric.crs)
    grid["cell_id"] = (
        grid["district"].astype(str)
        + ":"
        + grid["grid_row"].astype(str)
        + ":"
        + grid["grid_col"].astype(str)
    )
    if grid["cell_id"].duplicated().any():
        raise RuntimeError("Generated grid cell IDs are not unique.")
    grid.attrs.update({"origin_x": origin_x, "origin_y": origin_y})
    return grid


def add_jrc_building_volume(
    grid: gpd.GeoDataFrame,
    raster_paths: list[Path],
) -> gpd.GeoDataFrame:
    """Conservatively reproject JRC 100 m volume onto the analysis lattice."""

    if not raster_paths:
        raise ValueError("At least one JRC raster is required.")
    min_col, max_col = int(grid["grid_col"].min()), int(grid["grid_col"].max())
    min_row, max_row = int(grid["grid_row"].min()), int(grid["grid_row"].max())
    width = max_col - min_col + 1
    height = max_row - min_row + 1
    origin_x = float(grid["center_x"].iloc[0] - (grid["grid_col"].iloc[0] + 0.5) * GRID_SIZE_METRES)
    origin_y = float(grid["center_y"].iloc[0] - (grid["grid_row"].iloc[0] + 0.5) * GRID_SIZE_METRES)
    left = origin_x + min_col * GRID_SIZE_METRES
    top = origin_y + (max_row + 1) * GRID_SIZE_METRES
    transform = from_origin(left, top, GRID_SIZE_METRES, GRID_SIZE_METRES)
    destination = np.zeros((height, width), dtype=np.float64)

    for path in raster_paths:
        tile = np.zeros_like(destination)
        with rasterio.open(path) as source:
            if source.crs is None:
                raise ValueError(f"JRC raster does not declare a CRS: {path}")
            reproject(
                source=rasterio.band(source, 1),
                destination=tile,
                src_transform=source.transform,
                src_crs=source.crs,
                src_nodata=source.nodata,
                dst_transform=transform,
                dst_crs=grid.crs,
                dst_nodata=0,
                resampling=Resampling.sum,
                init_dest_nodata=True,
            )
        destination += np.nan_to_num(tile, nan=0.0, posinf=0.0, neginf=0.0)

    array_rows = max_row - grid["grid_row"].to_numpy(dtype=np.int64)
    array_cols = grid["grid_col"].to_numpy(dtype=np.int64) - min_col
    full_cell_volume = destination[array_rows, array_cols]
    full_cell_volume = np.clip(full_cell_volume, 0.0, None)
    full_cell_volume[full_cell_volume < 1e-6] = 0.0
    output = grid.copy()
    output["jrc_nres_volume_m3"] = full_cell_volume * output["area_fraction"].to_numpy()
    return output


def _find_hdf_dataset(handle: h5py.File, suffix: str) -> h5py.Dataset:
    matches: list[h5py.Dataset] = []

    def visitor(name: str, value: Any) -> None:
        if isinstance(value, h5py.Dataset) and name.split("/")[-1] == suffix:
            matches.append(value)

    handle.visititems(visitor)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one HDF dataset named {suffix}; found {len(matches)}.")
    return matches[0]


def _attribute(dataset: h5py.Dataset, names: tuple[str, ...], default: float) -> float:
    for name in names:
        if name in dataset.attrs:
            value = np.asarray(dataset.attrs[name]).ravel()[0]
            return float(value)
    return default


def _viirs_tile_bounds(path: Path) -> tuple[float, float, float, float]:
    match = re.search(r"\.h(\d{2})v(\d{2})\.", path.name)
    if not match:
        raise ValueError(f"Cannot derive VIIRS tile coordinates from {path.name}.")
    horizontal, vertical = map(int, match.groups())
    west = horizontal * 10.0 - 180.0
    north = 90.0 - vertical * 10.0
    return west, north - 10.0, west + 10.0, north


def add_viirs_radiance(
    grid: gpd.GeoDataFrame,
    granule_paths: list[Path],
) -> gpd.GeoDataFrame:
    """Assign quality-filtered native VIIRS pixels to 100 m cell centres."""

    if not granule_paths:
        raise ValueError("At least one VIIRS HDF5 granule is required.")
    transformer = Transformer.from_crs(grid.crs, "EPSG:4326", always_xy=True)
    longitudes, latitudes = transformer.transform(
        grid["center_x"].to_numpy(), grid["center_y"].to_numpy()
    )
    radiance_out = np.full(len(grid), np.nan, dtype=np.float64)
    quality_out = np.full(len(grid), np.nan, dtype=np.float64)

    for path in granule_paths:
        west, south, east, north = _viirs_tile_bounds(path)
        inside = (
            (longitudes >= west)
            & (longitudes < east)
            & (latitudes > south)
            & (latitudes <= north)
        )
        if not inside.any():
            continue
        with h5py.File(path, "r") as handle:
            radiance_ds = _find_hdf_dataset(handle, VIIRS_RADIANCE_VARIABLE)
            quality_ds = _find_hdf_dataset(handle, VIIRS_QUALITY_VARIABLE)
            raw = radiance_ds[...]
            quality = quality_ds[...]
            if raw.shape != quality.shape or raw.ndim != 2:
                raise RuntimeError(f"Unexpected VIIRS dataset shapes in {path.name}.")
            fill = _attribute(radiance_ds, ("_FillValue", "fill_value"), -999.9)
            scale = _attribute(radiance_ds, ("scale_factor", "Scale"), 1.0)
            offset = _attribute(radiance_ds, ("add_offset", "offset", "Offset"), 0.0)
            nrows, ncols = raw.shape
            indices = np.flatnonzero(inside)
            cols = np.floor((longitudes[indices] - west) / (10.0 / ncols)).astype(int)
            rows = np.floor((north - latitudes[indices]) / (10.0 / nrows)).astype(int)
            cols = np.clip(cols, 0, ncols - 1)
            rows = np.clip(rows, 0, nrows - 1)
            sampled_raw = raw[rows, cols]
            sampled_quality = quality[rows, cols]
            sampled_radiance = sampled_raw.astype(np.float64) * scale + offset
            good = (
                (sampled_quality == 0)
                & (sampled_raw != fill)
                & np.isfinite(sampled_radiance)
                & (sampled_radiance >= 0)
            )
            quality_out[indices] = sampled_quality
            radiance_out[indices[good]] = sampled_radiance[good]

    output = grid.copy()
    output["viirs_quality"] = quality_out
    output["viirs_radiance"] = radiance_out
    output["viirs_quality_good"] = output["viirs_quality"].eq(0)
    return output


def _primary_category(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("primary") or "").strip().lower()
    if hasattr(value, "as_py"):
        return _primary_category(value.as_py())
    return ""


def classify_economic_category(category: str) -> str | None:
    normalized = str(category).strip().lower()
    for group, terms in ECONOMIC_POI_RULES.items():
        if any(term in normalized for term in terms):
            return group
    return None


def add_overture_poi_intensity(
    grid: gpd.GeoDataFrame,
    districts_metric: gpd.GeoDataFrame,
    places_path: Path,
    *,
    economic_places_path: Path | None = None,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Retain relevant Places and sum confidence in the matching grid piece."""

    places = gpd.read_parquet(places_path)
    if places.empty or places.crs is None:
        raise RuntimeError("Overture Places cache is empty or lacks a CRS.")
    if "categories" in places.columns:
        categories = places["categories"].map(_primary_category)
    elif "categories.primary" in places.columns:
        categories = places["categories.primary"].fillna("").astype(str).str.lower()
    else:
        raise ValueError("Overture Places data has no categories.primary field.")
    confidence = (
        pd.to_numeric(places["confidence"], errors="coerce")
        if "confidence" in places.columns
        else pd.Series(np.nan, index=places.index)
    ).fillna(0.5).clip(lower=0.0, upper=1.0)
    keep_columns = [column for column in ("id",) if column in places.columns]
    economic = places[keep_columns + ["geometry"]].copy()
    economic["basic_category"] = categories
    economic["economic_category"] = categories.map(classify_economic_category)
    economic["confidence"] = confidence
    economic = economic.loc[economic["economic_category"].notna()].copy()
    if economic.empty:
        raise RuntimeError("No Overture Places matched the economic classification rules.")

    economic = economic.to_crs(districts_metric.crs)
    joined = gpd.sjoin(
        economic,
        districts_metric[["district", "geometry"]],
        how="inner",
        predicate="within",
    ).drop(columns=["index_right"])
    if "id" in joined.columns:
        joined = joined.drop_duplicates(subset=["id"], keep="first")
    if joined.empty:
        raise RuntimeError("No economically relevant Overture Places fall inside Shanghai.")

    origin_x = float(grid["center_x"].iloc[0] - (grid["grid_col"].iloc[0] + 0.5) * GRID_SIZE_METRES)
    origin_y = float(grid["center_y"].iloc[0] - (grid["grid_row"].iloc[0] + 0.5) * GRID_SIZE_METRES)
    joined["grid_col"] = np.floor(
        (joined.geometry.x.to_numpy() - origin_x) / GRID_SIZE_METRES
    ).astype(np.int32)
    joined["grid_row"] = np.floor(
        (joined.geometry.y.to_numpy() - origin_y) / GRID_SIZE_METRES
    ).astype(np.int32)
    intensity = (
        joined.groupby(["district", "grid_row", "grid_col"], as_index=False)["confidence"]
        .sum()
        .rename(columns={"confidence": "overture_poi_intensity"})
    )
    output = grid.merge(
        intensity,
        on=["district", "grid_row", "grid_col"],
        how="left",
        validate="one_to_one",
    )
    output = gpd.GeoDataFrame(output, geometry="geometry", crs=grid.crs)
    output["overture_poi_intensity"] = output["overture_poi_intensity"].fillna(0.0)

    if economic_places_path is not None:
        economic_places_path.parent.mkdir(parents=True, exist_ok=True)
        joined[[
            *(column for column in ("id",) if column in joined.columns),
            "district",
            "basic_category",
            "economic_category",
            "confidence",
            "geometry",
        ]].to_crs("EPSG:4326").to_parquet(economic_places_path, index=False)
    return output, joined


def robust_normalize(values: pd.Series) -> pd.Series:
    """Log-transform, winsorize nonzero values, then min-max to [0, 1]."""

    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0).clip(lower=0.0)
    transformed = np.log1p(numeric.to_numpy(dtype=np.float64))
    positive = transformed[transformed > 0]
    if positive.size == 0:
        return pd.Series(np.zeros(len(values)), index=values.index, dtype=float)
    lower, upper = np.quantile(positive, [0.01, 0.99])
    clipped = np.clip(transformed, lower, upper)
    clipped[transformed == 0] = 0.0
    if upper <= 0 or math.isclose(upper, lower):
        normalized = (transformed > 0).astype(float)
    else:
        normalized = np.where(clipped > 0, (clipped - lower) / (upper - lower), 0.0)
        normalized = np.clip(normalized, 0.0, 1.0)
    return pd.Series(normalized, index=values.index, dtype=float)


def add_composite_weights(grid: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Normalize proxies within district and calculate all labelled scenarios."""

    required = {"jrc_nres_volume_m3", "viirs_radiance", "overture_poi_intensity"}
    missing = required - set(grid.columns)
    if missing:
        raise ValueError(f"Grid is missing proxy columns: {sorted(missing)}")
    output = grid.copy()
    output["viirs_activity"] = (
        output["viirs_radiance"].fillna(0.0).clip(lower=0.0) * output["area_fraction"]
    )
    proxy_columns = {
        "building": "jrc_nres_volume_m3",
        "lights": "viirs_activity",
        "poi": "overture_poi_intensity",
    }
    for proxy, column in proxy_columns.items():
        output[f"{proxy}_normalized"] = output.groupby("district", group_keys=False)[
            column
        ].transform(robust_normalize)
    for scenario, weights in SCENARIOS.items():
        output[f"weight_{scenario}"] = sum(
            weights[proxy] * output[f"{proxy}_normalized"] for proxy in proxy_columns
        )
    district_sums = output.groupby("district")[
        [f"weight_{scenario}" for scenario in SCENARIOS]
    ].sum()
    if (district_sums <= 0).any().any():
        failures = district_sums.index[(district_sums <= 0).any(axis=1)].tolist()
        raise RuntimeError(f"Composite activity is zero in districts: {failures}")
    return output
