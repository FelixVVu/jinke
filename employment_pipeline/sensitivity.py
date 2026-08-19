"""Functional-zone support and boundary-vintage sensitivities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from .boundaries import ZONE_PLANNING_AREA_KM2, area_matched_planning_interpretation
from .grid import (
    add_jrc_nonresidential_volume,
    add_overture_workplace_predictors,
    build_control_grid,
)
from .model import PpmlFit, allocate_control_employment
from .config import CITY_EMPLOYMENT
from .reach import _model_total

ZONE_PLAN_SOURCES = {
    "310115501000": "https://www.pudong.gov.cn/zwgk/qt-bsqglj/2024/200/328852.html",
    "310115502000": "https://www.pudong.gov.cn/zwgk/006003002/2022/302/257742.html",
    "310115503000": "https://www.pudong.gov.cn/zwgk/14482.gkml_ywl_sthjgl/2025/171/341785.html",
}


def calculate_zone_sensitivity(
    *,
    all_controls: gpd.GeoDataFrame,
    central_fine_grid: gpd.GeoDataFrame,
    fit: PpmlFit,
    jrc_raster_path: Path,
    overture_places_path: Path,
    reaches: gpd.GeoDataFrame,
) -> pd.DataFrame:
    zones = all_controls.loc[all_controls["control_type"] == "functional_zone"].copy()
    records: list[dict[str, Any]] = []
    for zone in zones.itertuples(index=False):
        code = str(zone.accounting_stratum_id)
        central_grid = central_fine_grid.loc[
            central_fine_grid["accounting_control"] == code
        ].copy()
        alternate_row = zones.loc[zones["accounting_stratum_id"] == code].copy()
        alternate_row.geometry = [
            area_matched_planning_interpretation(
                zone.geometry, ZONE_PLANNING_AREA_KM2[code]
            )
        ]
        alternate_row["boundary_source"] = (
            "area-matched morphology sensitivity based on official reported planning area"
        )
        alternate_row["restricted_geometry"] = False
        alternate = build_control_grid(alternate_row)
        alternate = add_jrc_nonresidential_volume(alternate, jrc_raster_path)
        alternate, _ = add_overture_workplace_predictors(
            alternate, alternate_row, overture_places_path
        )
        alternate = allocate_control_employment(alternate, fit)
        for reach in reaches.itertuples(index=False):
            central_uniform = _model_total(
                central_grid, reach.geometry, "cell_employment_uniform"
            )
            central_building = _model_total(
                central_grid, reach.geometry, "cell_employment_building_volume"
            )
            central_calibrated = _model_total(
                central_grid,
                reach.geometry,
                "cell_employment_calibrated_workplace",
            )
            planning_calibrated = _model_total(
                alternate,
                reach.geometry,
                "cell_employment_calibrated_workplace",
            )
            records.append(
                {
                    "limit_minutes": int(reach.limit),
                    "accounting_stratum_id": code,
                    "control_name": zone.official_control_name_2023,
                    "zone_employment": int(zone.employment_reconciled),
                    "selected_support": "Ruiduobao 2020 statistical polygon",
                    "selected_support_area_km2": float(zone.geometry.area / 1_000_000.0),
                    "selected_uniform_employment_inside": central_uniform,
                    "selected_building_employment_inside": central_building,
                    "selected_calibrated_employment_inside": central_calibrated,
                    "official_planning_source": ZONE_PLAN_SOURCES[code],
                    "official_reported_planning_area_km2": ZONE_PLANNING_AREA_KM2[
                        code
                    ],
                    "planning_interpretation": (
                        "area-matched morphology of the accounting-aligned support; "
                        "not an official vector and not assumed equal to the census stratum"
                    ),
                    "planning_interpretation_calibrated_employment_inside": planning_calibrated,
                    "conservative_lower_employment_inside": 0.0,
                    "conservative_upper_employment_inside": float(
                        zone.employment_reconciled
                    ),
                    "source_geometry_redistributed": False,
                    "geometry_is_approximate": True,
                }
            )
    return pd.DataFrame(records)


def add_zone_boundary_sensitivity(
    reach_results: pd.DataFrame,
    zone_sensitivity: pd.DataFrame,
) -> pd.DataFrame:
    """Add functional-zone support and combined boundary envelopes to reach rows.

    The official-planning comparison is the reported-area morphology interpretation,
    not an asserted census boundary. The conservative zone envelope sets each of the
    three uncertain zone rows to zero or 100% inside. It is compared, not added, to
    the independent +/-100 m reach-edge displacement diagnostic.
    """

    grouped = zone_sensitivity.groupby("limit_minutes", as_index=False).agg(
        functional_zone_selected_employment=(
            "selected_calibrated_employment_inside",
            "sum",
        ),
        functional_zone_reported_area_interpretation_employment=(
            "planning_interpretation_calibrated_employment_inside",
            "sum",
        ),
        functional_zone_conservative_lower_employment=(
            "conservative_lower_employment_inside",
            "sum",
        ),
        functional_zone_conservative_upper_employment=(
            "conservative_upper_employment_inside",
            "sum",
        ),
    )
    output = reach_results.merge(grouped, on="limit_minutes", validate="one_to_one")
    central = output["central_estimated_employment"].to_numpy(dtype=float)
    selected = output["functional_zone_selected_employment"].to_numpy(dtype=float)
    interpreted = output[
        "functional_zone_reported_area_interpretation_employment"
    ].to_numpy(dtype=float)
    zone_lower = output["functional_zone_conservative_lower_employment"].to_numpy(
        dtype=float
    )
    zone_upper = output["functional_zone_conservative_upper_employment"].to_numpy(
        dtype=float
    )
    output["reported_area_interpretation_total_employment"] = (
        central - selected + interpreted
    )
    output["reported_area_interpretation_delta_percentage_points"] = (
        interpreted - selected
    ) / CITY_EMPLOYMENT * 100.0
    output["functional_zone_support_lower_total_employment"] = (
        central - selected + zone_lower
    )
    output["functional_zone_support_upper_total_employment"] = (
        central - selected + zone_upper
    )
    lower_candidates = np.column_stack(
        [
            output["reach_edge_inward_100m_employment"].to_numpy(dtype=float),
            output["functional_zone_support_lower_total_employment"].to_numpy(
                dtype=float
            ),
        ]
    )
    upper_candidates = np.column_stack(
        [
            output["reach_edge_outward_100m_employment"].to_numpy(dtype=float),
            output["functional_zone_support_upper_total_employment"].to_numpy(
                dtype=float
            ),
        ]
    )
    boundary_lower = lower_candidates.min(axis=1)
    boundary_upper = upper_candidates.max(axis=1)
    output["boundary_sensitivity_lower_employment"] = boundary_lower
    output["boundary_sensitivity_upper_employment"] = boundary_upper
    output["boundary_sensitivity_minus_percentage_points"] = (
        boundary_lower - central
    ) / CITY_EMPLOYMENT * 100.0
    output["boundary_sensitivity_plus_percentage_points"] = (
        boundary_upper - central
    ) / CITY_EMPLOYMENT * 100.0
    output["boundary_sensitivity_absolute_percentage_points"] = np.maximum(
        np.abs(boundary_lower - central), np.abs(boundary_upper - central)
    ) / CITY_EMPLOYMENT * 100.0
    output["boundary_sensitivity_components_are_not_added"] = True
    return output
