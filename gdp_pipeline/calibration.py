"""Reconcile official totals and allocate district GDP across grid cells."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from .config import SCENARIOS

GDP_COLUMNS = {
    "central": "estimated_gdp_100m_cny",
    "building_heavy": "building_heavy_gdp_100m_cny",
    "activity_heavy": "activity_heavy_gdp_100m_cny",
}


def build_district_calibration(
    district_gdp: pd.DataFrame,
    city_gdp: pd.Series,
) -> tuple[pd.DataFrame, float]:
    """Calculate and disclose one city/district proportional factor."""

    calibration = district_gdp.copy(deep=True).rename(
        columns={"gdp_100m_cny": "raw_gdp_100m_cny"}
    )
    raw_sum = float(calibration["raw_gdp_100m_cny"].sum())
    city_total = float(city_gdp["gdp_100m_cny"])
    if raw_sum <= 0 or city_total <= 0:
        raise ValueError("Official GDP totals must be positive.")
    factor = city_total / raw_sum
    calibration["reconciliation_factor"] = factor
    calibration["reconciled_gdp_100m_cny"] = (
        calibration["raw_gdp_100m_cny"] * factor
    )
    calibration["reconciliation_difference_100m_cny"] = (
        calibration["reconciled_gdp_100m_cny"]
        - calibration["raw_gdp_100m_cny"]
    )
    calibration["official_shanghai_gdp_100m_cny"] = city_total
    calibration["raw_district_sum_100m_cny"] = raw_sum
    calibration["district_city_gap_100m_cny"] = city_total - raw_sum
    return calibration, factor


def allocate_district_gdp(
    grid: gpd.GeoDataFrame,
    calibration: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """Allocate each reconciled district target proportional to each scenario."""

    targets = calibration[
        ["district", "raw_gdp_100m_cny", "reconciled_gdp_100m_cny"]
    ]
    output = grid.merge(targets, on="district", how="left", validate="many_to_one")
    output = gpd.GeoDataFrame(output, geometry="geometry", crs=grid.crs)
    if output["reconciled_gdp_100m_cny"].isna().any():
        raise RuntimeError("At least one grid district has no official GDP target.")

    for scenario in SCENARIOS:
        weight_column = f"weight_{scenario}"
        gdp_column = GDP_COLUMNS[scenario]
        denominators = output.groupby("district")[weight_column].transform("sum")
        if (denominators <= 0).any():
            raise RuntimeError(f"Cannot calibrate {scenario}: a district has zero activity.")
        output[gdp_column] = (
            output[weight_column]
            / denominators
            * output["reconciled_gdp_100m_cny"]
        )
        # Floating arithmetic can leave sub-nanoyuan residuals. Assign each
        # residual to that district's highest-weight cell, preserving the model.
        for district, indices in output.groupby("district").groups.items():
            index = list(indices)
            target = float(output.loc[index[0], "reconciled_gdp_100m_cny"])
            residual = target - float(output.loc[index, gdp_column].sum())
            if residual:
                recipient = output.loc[index, weight_column].idxmax()
                output.loc[recipient, gdp_column] += residual
        if (output[gdp_column] < -1e-12).any():
            raise RuntimeError(f"Negative GDP was produced for scenario {scenario}.")
        output[gdp_column] = np.clip(output[gdp_column], 0.0, None)
    return output
