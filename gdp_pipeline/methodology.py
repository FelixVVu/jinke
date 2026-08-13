"""Construct a machine-readable methodology and provenance record."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .config import (
    ANALYSIS_CRS,
    BOUNDARY_LICENSE,
    BOUNDARY_METADATA_URL,
    BOUNDARY_SOURCE_URL,
    ECONOMIC_POI_RULES,
    GRID_SIZE_METRES,
    SCENARIOS,
)


def build_methodology(
    *,
    source_metadata: dict[str, Any],
    district_gdp: pd.DataFrame,
    city_gdp: pd.Series,
    reconciliation_factor: float,
    reach_path: Path,
    reach_sha256: str,
    boundary_sha256: str,
) -> dict[str, Any]:
    raw_district_total = float(district_gdp["gdp_100m_cny"].sum())
    city_total = float(city_gdp["gdp_100m_cny"])
    return {
        "methodology_version": "jinke-gdp-v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "Spatially allocate official Shanghai GDP and estimate the share inside "
            "the existing Jinke 10/20/30/40/50-minute production reach polygons."
        ),
        "analysis_grid": {
            "cell_size_metres": GRID_SIZE_METRES,
            "crs": ANALYSIS_CRS,
            "district_boundary_clipping": True,
            "partial_reach_cells": "GDP multiplied by intersection area / clipped cell area",
        },
        "district_boundaries": {
            "dataset": "geoBoundaries gbOpen CHN ADM3, filtered to Shanghai",
            "source_url": BOUNDARY_SOURCE_URL,
            "metadata_url": BOUNDARY_METADATA_URL,
            "pinned_commit": "9469f09",
            "boundary_year": 2017,
            "license": BOUNDARY_LICENSE,
            "file_sha256": boundary_sha256,
            "district_count": 16,
        },
        "sources": source_metadata,
        "poi_classification": {
            "rule": (
                "Lower-case categories.primary is assigned to the first group with a "
                "matching substring. Nonmatching places are excluded. Included POIs are "
                "weighted by confidence (0.5 only when confidence is unavailable); no "
                "category-specific multiplier is used."
            ),
            "groups": {key: list(values) for key, values in ECONOMIC_POI_RULES.items()},
            "gaode_amap_used": False,
        },
        "normalization": {
            "scope": "separately within each district",
            "steps": [
                "replace missing/negative proxy values with zero",
                "log1p transform",
                "winsorize positive values at district 1st and 99th percentiles",
                "min-max scale to [0, 1] with zeros retained as zero",
            ],
            "viirs_note": (
                "Radiance remains a native 15-arc-second observation. It is assigned to "
                "100 m cell centres and multiplied by clipped-cell area fraction only for "
                "the extensive activity proxy; this is not a claim of 100 m VIIRS detail."
            ),
        },
        "scenarios": {
            name: {
                **weights,
                "label": "central scenario" if name == "central" else "sensitivity scenario",
            }
            for name, weights in SCENARIOS.items()
        },
        "sensitivity_disclosure": (
            "Building-heavy and activity-heavy results are sensitivity scenarios, not "
            "confidence intervals."
        ),
        "official_gdp": {
            "year": int(district_gdp["year"].iloc[0]),
            "unit": "100 million current CNY (亿元)",
            "district_source_rows": district_gdp.to_dict(orient="records"),
            "city_source_row": city_gdp.to_dict(),
            "raw_district_sum_100m_cny": raw_district_total,
            "official_city_gdp_100m_cny": city_total,
            "difference_100m_cny": city_total - raw_district_total,
            "proportional_reconciliation_factor": reconciliation_factor,
            "rule": (
                "Each raw district value remains unchanged in the source table. One common "
                "factor rescales district targets so the final grid equals official city GDP."
            ),
        },
        "reach_polygons": {
            "path": str(reach_path),
            "sha256": reach_sha256,
            "modified_by_workflow": False,
            "limits_minutes": [10, 20, 30, 40, 50],
        },
        "prohibited_services": {
            "openrouteservice_called": False,
            "gaode_amap_called": False,
        },
        "limitations": [
            "This is a modelled spatial allocation of official GDP, not measured cell GDP.",
            "Proxy relationships may vary within districts despite district-level normalization.",
            "Boundary, building, lights, POI, and GDP reference dates are not identical.",
            "Reach results inherit the geometry and assumptions of the existing production polygons.",
        ],
    }
