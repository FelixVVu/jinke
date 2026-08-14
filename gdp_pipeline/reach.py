"""Area-weighted intersection with the existing production reach polygons."""

from __future__ import annotations

import hashlib
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from .calibration import GDP_COLUMNS
from .config import LIMITS


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_production_reach_areas(
    path: Path,
    target_crs: object,
) -> tuple[gpd.GeoDataFrame, str]:
    """Read and validate without writing or altering the source GeoJSON."""

    before = file_sha256(path)
    reaches = gpd.read_file(path)
    if reaches.crs is None:
        raise ValueError("Production reach polygons do not declare a CRS.")
    if "limit" not in reaches.columns:
        raise ValueError("Production reach polygons have no 'limit' field.")
    reaches["limit"] = pd.to_numeric(reaches["limit"], errors="raise").astype(int)
    if sorted(reaches["limit"].tolist()) != list(LIMITS):
        raise ValueError(
            f"Production reach limits must be {list(LIMITS)}; got {reaches['limit'].tolist()}."
        )
    if reaches["limit"].duplicated().any():
        raise ValueError("Production reach polygons contain duplicate limits.")
    if reaches.geometry.is_empty.any() or not reaches.geometry.is_valid.all():
        raise ValueError("Production reach polygons include empty or invalid geometry.")
    projected = reaches.to_crs(target_crs).sort_values("limit").reset_index(drop=True)
    after = file_sha256(path)
    if before != after:
        raise RuntimeError("The production reach GeoJSON changed while it was being read.")
    return projected, before


def calculate_reach_gdp(
    grid: gpd.GeoDataFrame,
    reaches_metric: gpd.GeoDataFrame,
    official_city_gdp_100m_cny: float,
) -> pd.DataFrame:
    """Calculate partial-cell GDP shares for each production reach limit."""

    if not np.isfinite(official_city_gdp_100m_cny) or official_city_gdp_100m_cny <= 0:
        raise ValueError("Official Shanghai GDP must be a finite positive value.")
    if grid.crs != reaches_metric.crs:
        raise ValueError("Grid and reach polygons must use the same projected CRS.")
    records: list[dict[str, float | int]] = []
    previous = 0.0
    for reach in reaches_metric.itertuples(index=False):
        geometry = reach.geometry
        candidates = np.asarray(grid.sindex.query(geometry, predicate="intersects"))
        if candidates.size == 0:
            raise RuntimeError(f"Reach {reach.limit} has no intersection with the GDP grid.")
        pieces = grid.iloc[candidates]
        intersection_areas = shapely.area(shapely.intersection(pieces.geometry.array, geometry))
        fractions = np.divide(
            intersection_areas,
            pieces["cell_area_m2"].to_numpy(dtype=float),
            out=np.zeros_like(intersection_areas, dtype=float),
            where=pieces["cell_area_m2"].to_numpy(dtype=float) > 0,
        )
        fractions = np.clip(fractions, 0.0, 1.0)
        estimates = {
            scenario: float(
                np.dot(fractions, pieces[column].to_numpy(dtype=float))
            )
            for scenario, column in GDP_COLUMNS.items()
        }
        central = estimates["central"]
        records.append(
            {
                "limit_minutes": int(reach.limit),
                "estimated_gdp_100m_cny": central,
                "percentage_of_shanghai_gdp": central
                / official_city_gdp_100m_cny
                * 100.0,
                "incremental_gdp_100m_cny": central - previous,
                "building_heavy_gdp_100m_cny": estimates["building_heavy"],
                "activity_heavy_gdp_100m_cny": estimates["activity_heavy"],
            }
        )
        previous = central
    result = pd.DataFrame.from_records(records)
    if (result["incremental_gdp_100m_cny"] < -1e-8).any():
        raise RuntimeError("Production reach GDP is not monotonic; check polygon nesting.")
    return result
