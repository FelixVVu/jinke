"""Exact production-reach intersections, bounds, rounding, and contributions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from scipy.optimize import linprog

from .config import (
    BOUNDARY_DISPLACEMENT_METRES,
    CITY_EMPLOYMENT,
    EMPLOYMENT_UNIVERSE,
    LIMITS,
    PRODUCTION_REACH_SHA256,
)
from .manifests import sha256_file

REACH_SOURCE_SHA256 = PRODUCTION_REACH_SHA256

FINE_MODEL_COLUMNS = {
    "uniform": "cell_employment_uniform",
    "building_volume": "cell_employment_building_volume",
    "calibrated_workplace": "cell_employment_calibrated_workplace",
}


def load_production_reaches(
    path: Path,
    target_crs: Any,
) -> tuple[gpd.GeoDataFrame, str]:
    before = sha256_file(path)
    if before != REACH_SOURCE_SHA256:
        raise ValueError(f"Production reach GeoJSON hash changed: {before}")
    reaches = gpd.read_file(path)
    if reaches.crs is None or "limit" not in reaches:
        raise ValueError("Production reach file lacks a CRS or limit field.")
    reaches["limit"] = pd.to_numeric(reaches["limit"], errors="raise").astype(int)
    if sorted(reaches["limit"].tolist()) != list(LIMITS):
        raise ValueError(f"Production limits are not {LIMITS}.")
    if reaches["limit"].duplicated().any():
        raise ValueError("Production reach limits are duplicated.")
    if reaches.geometry.is_empty.any() or not reaches.geometry.is_valid.all():
        raise ValueError("Production reaches contain empty or invalid geometry.")
    projected = reaches.to_crs(target_crs).sort_values("limit").reset_index(drop=True)
    after = sha256_file(path)
    if after != before:
        raise RuntimeError("Production reach file changed while it was being read.")
    return projected, before


def partial_cell_fractions(grid: gpd.GeoDataFrame, geometry: Any) -> np.ndarray:
    fractions = np.zeros(len(grid), dtype=float)
    candidates = np.asarray(grid.sindex.query(geometry, predicate="intersects"))
    if candidates.size == 0:
        return fractions
    pieces = grid.iloc[candidates]
    areas = shapely.area(shapely.intersection(pieces.geometry.array, geometry))
    denominators = pieces["cell_area_m2"].to_numpy(dtype=float)
    candidate_fractions = np.divide(
        areas,
        denominators,
        out=np.zeros_like(areas, dtype=float),
        where=denominators > 0,
    )
    fractions[candidates] = np.clip(candidate_fractions, 0.0, 1.0)
    return fractions


def _model_total(
    grid: gpd.GeoDataFrame,
    geometry: Any,
    column: str,
) -> float:
    fractions = partial_cell_fractions(grid, geometry)
    return float(np.dot(fractions, grid[column].to_numpy(dtype=float)))


def calculate_reach_employment(
    fine_grid: gpd.GeoDataFrame,
    residual_grid: gpd.GeoDataFrame,
    reaches: gpd.GeoDataFrame,
    residuals: pd.DataFrame,
) -> pd.DataFrame:
    if fine_grid.crs != reaches.crs:
        raise ValueError("Employment grid and production reaches use different CRSs.")
    total_residual = float(residuals["employment_nominal"].sum())
    records: list[dict[str, Any]] = []
    prior_central = 0.0
    for reach in reaches.itertuples(index=False):
        fine = {
            model: _model_total(fine_grid, reach.geometry, column)
            for model, column in FINE_MODEL_COLUMNS.items()
        }
        residual_central = (
            _model_total(
                residual_grid,
                reach.geometry,
                "cell_employment_residual_central",
            )
            if not residual_grid.empty
            else 0.0
        )
        model_totals = {model: value + residual_central for model, value in fine.items()}
        central = model_totals["calibrated_workplace"]
        residual_lower_total = fine["calibrated_workplace"]
        residual_upper_total = fine["calibrated_workplace"] + total_residual
        inner = reach.geometry.buffer(-BOUNDARY_DISPLACEMENT_METRES)
        outer = reach.geometry.buffer(BOUNDARY_DISPLACEMENT_METRES)
        inner_fine = 0.0 if inner.is_empty else _model_total(
            fine_grid, inner, FINE_MODEL_COLUMNS["calibrated_workplace"]
        )
        outer_fine = _model_total(
            fine_grid, outer, FINE_MODEL_COLUMNS["calibrated_workplace"]
        )
        inner_residual = 0.0 if inner.is_empty or residual_grid.empty else _model_total(
            residual_grid, inner, "cell_employment_residual_central"
        )
        outer_residual = 0.0 if residual_grid.empty else _model_total(
            residual_grid, outer, "cell_employment_residual_central"
        )
        inner_total = inner_fine + inner_residual
        outer_total = outer_fine + outer_residual
        records.append(
            {
                "limit_minutes": int(reach.limit),
                "central_estimated_employment": central,
                "percentage_of_shanghai_employment": central / CITY_EMPLOYMENT * 100.0,
                "incremental_employment": central - prior_central,
                "fine_control_uniform_employment": fine["uniform"],
                "fine_control_building_volume_employment": fine["building_volume"],
                "fine_control_calibrated_workplace_employment": fine[
                    "calibrated_workplace"
                ],
                "residual_central_employment": residual_central,
                "uniform_allocation_employment": model_totals["uniform"],
                "uniform_allocation_percentage": model_totals["uniform"]
                / CITY_EMPLOYMENT
                * 100.0,
                "building_volume_employment": model_totals["building_volume"],
                "building_volume_percentage": model_totals["building_volume"]
                / CITY_EMPLOYMENT
                * 100.0,
                "calibrated_workplace_model_employment": model_totals[
                    "calibrated_workplace"
                ],
                "calibrated_workplace_model_percentage": model_totals[
                    "calibrated_workplace"
                ]
                / CITY_EMPLOYMENT
                * 100.0,
                "residual_lower_bound_employment": residual_lower_total,
                "residual_lower_bound_percentage": residual_lower_total
                / CITY_EMPLOYMENT
                * 100.0,
                "residual_upper_bound_employment": residual_upper_total,
                "residual_upper_bound_percentage": residual_upper_total
                / CITY_EMPLOYMENT
                * 100.0,
                "reach_edge_inward_100m_employment": inner_total,
                "reach_edge_outward_100m_employment": outer_total,
                "reach_edge_displacement_minus_percentage_points": (
                    inner_total - central
                )
                / CITY_EMPLOYMENT
                * 100.0,
                "reach_edge_displacement_plus_percentage_points": (
                    outer_total - central
                )
                / CITY_EMPLOYMENT
                * 100.0,
                "reach_edge_displacement_absolute_percentage_points": max(
                    abs(inner_total - central), abs(outer_total - central)
                )
                / CITY_EMPLOYMENT
                * 100.0,
                "employment_universe": EMPLOYMENT_UNIVERSE,
                "denominator": CITY_EMPLOYMENT,
                "geometry_is_approximate": True,
                "approximate_boundary_disclosure": (
                    "Street/town boundaries are OSM approximations cross-walked to 2023 "
                    "controls; Pudong functional-zone supports are approximate 2020 "
                    "statistical polygons and are redacted from the public grid."
                ),
            }
        )
        prior_central = central
    return pd.DataFrame.from_records(records)


def control_reach_shares(
    fine_grid: gpd.GeoDataFrame,
    geometry: Any,
    model_column: str = "cell_employment_calibrated_workplace",
) -> pd.DataFrame:
    fractions = partial_cell_fractions(fine_grid, geometry)
    working = pd.DataFrame(
        {
            "accounting_control": fine_grid["accounting_control"].to_numpy(),
            "inside": fractions * fine_grid[model_column].to_numpy(dtype=float),
            "total": fine_grid[model_column].to_numpy(dtype=float),
        }
    )
    grouped = working.groupby("accounting_control", as_index=False).sum()
    grouped["reach_share"] = np.divide(
        grouped["inside"],
        grouped["total"],
        out=np.zeros(len(grouped), dtype=float),
        where=grouped["total"].to_numpy(dtype=float) > 0,
    )
    return grouped


def rounding_sensitivity(
    fine_grid: gpd.GeoDataFrame,
    residual_grid: gpd.GeoDataFrame,
    reaches: gpd.GeoDataFrame,
    crosswalk: pd.DataFrame,
    residuals: pd.DataFrame,
    district_totals: pd.DataFrame,
) -> pd.DataFrame:
    """Solve feasible extrema while holding every exact district total fixed.

    A rounded fine-row change is offset by the corresponding district residual; it
    never creates or removes employment. For centrally located finance residuals,
    the residual's observed reach share enters the linear objective. Unlocated
    residuals have a reach share of zero.
    """

    controls = crosswalk.copy()
    controls["accounting_stratum_id"] = controls["accounting_stratum_id"].astype(str)
    district_employment = district_totals.set_index("district")["employment"].astype(float)
    records = []
    for reach in reaches.itertuples(index=False):
        shares = control_reach_shares(fine_grid, reach.geometry).set_index(
            "accounting_control"
        )["reach_share"]
        if residual_grid.empty:
            residual_shares = pd.Series(dtype=float)
        else:
            residual_control_shares = control_reach_shares(
                residual_grid,
                reach.geometry,
                model_column="cell_employment_residual_central",
            ).set_index("accounting_control")["reach_share"]
            residual_shares = residuals.set_index("residual_id").index.to_series().map(
                residual_control_shares
            ).fillna(0.0)
            residual_shares.index = residuals.set_index("residual_id").index
        district_residual_share = residuals.set_index("district")["residual_id"].map(
            residual_shares
        ).fillna(0.0)
        row_residual_share = controls["district"].map(district_residual_share).fillna(0.0)
        c = (
            controls["accounting_stratum_id"].map(shares).fillna(0.0)
            - row_residual_share
        ).to_numpy(dtype=float)
        constant = float(
            district_employment.reindex(district_residual_share.index).mul(
                district_residual_share
            ).sum()
        )
        lower = controls["employment_rounding_lower"].to_numpy(dtype=float)
        upper = controls["employment_rounding_upper_exclusive"].to_numpy(dtype=float)
        exact = controls["rounding_increment_people"].to_numpy(dtype=float) == 1
        bounds = [
            (lo, lo) if is_exact else (lo, np.nextafter(hi, -np.inf))
            for lo, hi, is_exact in zip(lower, upper, exact, strict=True)
        ]
        a_ub: list[np.ndarray] = []
        b_ub: list[float] = []
        for subtotal, lo, hi in (
            ("Pudong streets", 694_500.0, 695_500.0),
            ("Pudong towns", 1_098_500.0, 1_099_500.0),
            ("Pudong functional zones", 820_500.0, 821_500.0),
        ):
            mask = (controls["subtotal_group"] == subtotal).to_numpy(dtype=float)
            a_ub.extend([mask, -mask])
            b_ub.extend([np.nextafter(hi, -np.inf), -lo])
        result_min = linprog(
            c,
            A_ub=np.asarray(a_ub),
            b_ub=np.asarray(b_ub),
            bounds=bounds,
            method="highs",
        )
        result_max = linprog(
            -c,
            A_ub=np.asarray(a_ub),
            b_ub=np.asarray(b_ub),
            bounds=bounds,
            method="highs",
        )
        if not result_min.success or not result_max.success:
            raise RuntimeError("Published rounding intervals are infeasible.")
        central = float(
            constant
            + np.dot(c, controls["employment_reconciled"].to_numpy(dtype=float))
        )
        minimum = float(constant + result_min.fun)
        maximum = float(constant - result_max.fun)
        records.append(
            {
                "limit_minutes": int(reach.limit),
                "central_employment_with_fixed_district_totals": central,
                "rounding_minimum_employment_with_fixed_district_totals": minimum,
                "rounding_maximum_employment_with_fixed_district_totals": maximum,
                "rounding_minus_percentage_points": (minimum - central)
                / CITY_EMPLOYMENT
                * 100.0,
                "rounding_plus_percentage_points": (maximum - central)
                / CITY_EMPLOYMENT
                * 100.0,
            }
        )
    return pd.DataFrame(records)


def district_contributions_50min(
    fine_grid: gpd.GeoDataFrame,
    residual_grid: gpd.GeoDataFrame,
    reach_50: Any,
    district_totals: pd.DataFrame,
    residuals: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    fine_fractions = partial_cell_fractions(fine_grid, reach_50)
    fine = pd.DataFrame(
        {
            "district": fine_grid["district"].to_numpy(),
            "control_type": fine_grid["control_type"].to_numpy(),
            "accounting_control": fine_grid["accounting_control"].to_numpy(),
            "inside": fine_fractions
            * fine_grid["cell_employment_calibrated_workplace"].to_numpy(dtype=float),
            "total": fine_grid["cell_employment_calibrated_workplace"].to_numpy(
                dtype=float
            ),
        }
    )
    fine_district = fine.groupby("district", as_index=False).agg(
        fine_controlled_employment=("total", "sum"),
        fine_employment_inside_50min=("inside", "sum"),
    )
    if residual_grid.empty:
        residual_inside = pd.Series(dtype=float)
    else:
        residual_fractions = partial_cell_fractions(residual_grid, reach_50)
        residual_inside = pd.Series(
            residual_fractions
            * residual_grid["cell_employment_residual_central"].to_numpy(dtype=float),
            index=residual_grid.index,
        ).groupby(residual_grid["district"]).sum()
    priority = district_totals.loc[district_totals["priority_district"].astype(bool)].copy()
    priority = priority.merge(fine_district, on="district", validate="one_to_one")
    priority = priority.merge(
        residuals[["district", "employment_nominal"]].rename(
            columns={"employment_nominal": "residual_employment"}
        ),
        on="district",
        validate="one_to_one",
    )
    priority["residual_central_inside_50min"] = (
        priority["district"].map(residual_inside).fillna(0.0)
    )
    priority["employment_inside_50min"] = (
        priority["fine_employment_inside_50min"]
        + priority["residual_central_inside_50min"]
    )
    priority["percentage_of_district_employment_captured"] = (
        priority["employment_inside_50min"] / priority["employment"] * 100.0
    )
    total_inside = float(priority["employment_inside_50min"].sum())
    priority["contribution_to_total_reach_employment_percentage"] = (
        priority["employment_inside_50min"] / total_inside * 100.0
    )
    priority["boundary_source"] = (
        "OSM 2026-08-19; Pudong also uses restricted 2020 zone supports"
    )
    priority["boundary_is_approximate"] = True
    priority = priority.rename(columns={"employment": "exact_district_employment"})

    pudong = fine.loc[fine["district"] == "浦东新区"].copy()
    zone_names = {
        "310115501000": "FTZ Bonded Area",
        "310115502000": "Jinqiao ETDZ",
        "310115503000": "Zhangjiang High-Tech Park",
    }
    pudong["reporting_stratum"] = np.where(
        pudong["control_type"] == "functional_zone",
        pudong["accounting_control"].map(zone_names),
        "ordinary streets/towns",
    )
    pudong_detail = pudong.groupby("reporting_stratum", as_index=False).agg(
        stratum_employment=("total", "sum"),
        employment_inside_50min=("inside", "sum"),
    )
    pudong_residual = residuals.loc[residuals["district"] == "浦东新区"].iloc[0]
    pudong_detail = pd.concat(
        [
            pudong_detail,
            pd.DataFrame(
                [
                    {
                        "reporting_stratum": "Pudong residual",
                        "stratum_employment": float(pudong_residual.employment_nominal),
                        "employment_inside_50min": 0.0,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    pudong_detail["percentage_captured"] = (
        pudong_detail["employment_inside_50min"]
        / pudong_detail["stratum_employment"]
        * 100.0
    )
    pudong_detail["boundary_is_approximate"] = True
    return priority, pudong_detail


def minhang_sliver_diagnostic(
    district_boundary_path: Path,
    reach_50: Any,
) -> dict[str, Any]:
    districts = gpd.read_file(district_boundary_path).to_crs(
        gpd.GeoSeries([reach_50], crs="EPSG:32651").crs
    )
    minhang = districts.loc[districts["district"] == "闵行区"]
    if len(minhang) != 1:
        raise ValueError("Minhang district boundary is unavailable.")
    area = float(minhang.geometry.iloc[0].intersection(reach_50).area)
    return {
        "district": "闵行区",
        "intersection_area_m2": area,
        "treatment": (
            "technical boundary sensitivity only; no Minhang employment assigned to the sliver"
        ),
        "employment_assigned": 0.0,
        "could_dominate_uncertainty": False,
    }
