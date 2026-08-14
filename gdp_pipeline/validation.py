"""Fail-closed validation for data sources, calibration and reach outputs."""

from __future__ import annotations

from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from .calibration import GDP_COLUMNS
from .config import LIMITS, SCENARIOS


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_outputs(
    *,
    districts_metric: gpd.GeoDataFrame,
    district_gdp: pd.DataFrame,
    grid: gpd.GeoDataFrame,
    calibration: pd.DataFrame,
    reach: pd.DataFrame,
    official_city_gdp_100m_cny: float,
    source_metadata: dict[str, Any],
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    checks: dict[str, Any] = {}

    checks["district_count"] = int(len(districts_metric))
    checks["districts_matched"] = int(grid["district"].nunique())
    _assert(len(districts_metric) == 16, "Boundary input must contain exactly 16 districts.")
    _assert(grid["district"].nunique() == 16, "Grid must contain exactly 16 districts.")
    _assert(
        set(district_gdp["district"]) == set(grid["district"]),
        "Boundary/grid/GDP district names do not match.",
    )
    _assert(
        districts_metric.crs is not None and districts_metric.crs.is_projected,
        "District analysis CRS must be projected.",
    )
    _assert(grid.crs == districts_metric.crs, "Grid and district CRSs differ.")
    _assert(grid.geometry.is_valid.all(), "Grid contains invalid geometry.")
    _assert((grid["cell_area_m2"] > 0).all(), "Grid contains zero-area cells.")
    boundary_area = float(districts_metric.geometry.union_all().area)
    grid_area = float(grid["cell_area_m2"].sum())
    _assert(
        abs(grid_area - boundary_area) <= 10.0,
        f"Grid does not completely cover the district union: error={grid_area - boundary_area} m².",
    )
    checks["grid_cell_count"] = int(len(grid))
    checks["analysis_crs"] = str(grid.crs)
    checks["district_union_area_km2"] = boundary_area / 1_000_000.0
    checks["grid_coverage_error_m2"] = grid_area - boundary_area

    gdp_columns = list(GDP_COLUMNS.values())
    _assert(
        np.isfinite(grid[gdp_columns].to_numpy(dtype=float)).all(),
        "Grid GDP contains non-finite values.",
    )
    _assert((grid[gdp_columns] >= -tolerance).all().all(), "Grid GDP is negative.")
    checks["no_negative_gdp"] = True

    targets = calibration.set_index("district")["reconciled_gdp_100m_cny"]
    district_errors: dict[str, dict[str, float]] = {}
    for scenario in SCENARIOS:
        column = GDP_COLUMNS[scenario]
        actual = grid.groupby("district")[column].sum().reindex(targets.index)
        error = actual - targets
        _assert(
            float(error.abs().max()) <= tolerance,
            f"District calibration failed for {scenario}: max error={error.abs().max()}",
        )
        city_error = float(grid[column].sum() - official_city_gdp_100m_cny)
        _assert(
            abs(city_error) <= tolerance,
            f"Shanghai grid does not equal official city GDP for {scenario}: {city_error}",
        )
        district_errors[scenario] = {
            "max_abs_error_100m_cny": float(error.abs().max()),
            "city_error_100m_cny": city_error,
        }
    checks["district_calibration"] = district_errors
    checks["official_city_gdp_100m_cny"] = official_city_gdp_100m_cny

    limits = reach["limit_minutes"].astype(int).tolist()
    _assert(limits == list(LIMITS), f"Reach output limits are {limits}, expected {list(LIMITS)}.")
    checks["reach_limits"] = limits
    for column in (
        "estimated_gdp_100m_cny",
        "building_heavy_gdp_100m_cny",
        "activity_heavy_gdp_100m_cny",
    ):
        values = reach[column].to_numpy(dtype=float)
        _assert((values >= -tolerance).all(), f"Reach output {column} is negative.")
        _assert(
            (np.diff(values) >= -tolerance).all(),
            f"Reach output {column} is not monotonic.",
        )
        _assert(
            (values <= official_city_gdp_100m_cny + tolerance).all(),
            f"Reach output {column} exceeds official Shanghai GDP.",
        )
    checks["reach_totals_monotonic"] = True

    coverage = {
        "jrc_positive_cells": int((grid["jrc_nres_volume_m3"] > 0).sum()),
        "viirs_good_positive_cells": int(
            (grid["viirs_quality_good"] & grid["viirs_radiance"].fillna(0).gt(0)).sum()
        ),
        "overture_positive_cells": int((grid["overture_poi_intensity"] > 0).sum()),
    }
    _assert(all(value > 0 for value in coverage.values()), f"Empty proxy coverage: {coverage}")
    checks["proxy_coverage"] = coverage

    metadata_text = str(source_metadata).lower()
    _assert("openrouteservice" not in metadata_text, "Source metadata references ORS.")
    _assert("api.openrouteservice" not in metadata_text, "Source metadata references ORS.")
    _assert("amap.com" not in metadata_text, "Source metadata references Gaode/Amap.")
    _assert("gaode" not in metadata_text, "Source metadata references Gaode/Amap.")
    checks["no_ors_or_gaode_sources"] = True
    return {"status": "passed", "checks": checks}
