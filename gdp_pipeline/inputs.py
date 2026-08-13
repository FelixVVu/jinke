"""Pinned Shanghai district boundaries and official GDP inputs."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd

from .config import ANALYSIS_CRS

REQUIRED_GDP_COLUMNS = {
    "district",
    "year",
    "gdp_100m_cny",
    "source_url",
    "source_title",
    "retrieved_date",
}


def load_district_inputs(
    boundary_path: Path,
    district_gdp_path: Path,
    city_gdp_path: Path,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, pd.DataFrame, pd.Series]:
    """Load and strictly validate the 16-district, common-year inputs."""

    districts = gpd.read_file(boundary_path)
    if districts.crs is None:
        raise ValueError("Shanghai district boundaries do not declare a CRS.")
    if "district" not in districts.columns:
        raise ValueError("Shanghai district boundaries need a 'district' field.")
    districts["district"] = districts["district"].astype(str).str.strip()
    if len(districts) != 16:
        raise ValueError(f"Expected exactly 16 Shanghai districts; found {len(districts)}.")
    if districts["district"].duplicated().any():
        duplicates = districts.loc[
            districts["district"].duplicated(keep=False), "district"
        ].tolist()
        raise ValueError(f"Duplicate district names: {duplicates}")
    if districts.geometry.is_empty.any() or districts.geometry.isna().any():
        raise ValueError("District boundaries contain an empty geometry.")
    if not districts.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("Every district geometry must be Polygon or MultiPolygon.")
    if not districts.geometry.is_valid.all():
        invalid = districts.loc[~districts.geometry.is_valid, "district"].tolist()
        raise ValueError(f"Invalid district geometry: {invalid}")
    districts_wgs84 = districts.to_crs("EPSG:4326")
    districts_metric = districts.to_crs(ANALYSIS_CRS)
    if districts_metric.crs is None or not districts_metric.crs.is_projected:
        raise ValueError(f"Analysis CRS must be projected; got {districts_metric.crs}.")
    district_area = float(districts_metric.geometry.area.sum())
    union = districts_metric.geometry.union_all()
    if union.is_empty or not union.is_valid:
        raise ValueError("The 16 district geometries do not form a valid Shanghai union.")
    overlap_area = district_area - float(union.area)
    if overlap_area > 1.0:
        raise ValueError(f"Shanghai district boundaries materially overlap by {overlap_area} m².")
    if not 6_000_000_000 <= union.area <= 8_000_000_000:
        raise ValueError(
            f"Shanghai district union area is implausible or incomplete: {union.area / 1e6:.2f} km²."
        )

    district_gdp = pd.read_csv(district_gdp_path)
    missing_columns = REQUIRED_GDP_COLUMNS - set(district_gdp.columns)
    if missing_columns:
        raise ValueError(f"District GDP CSV is missing columns: {sorted(missing_columns)}")
    district_gdp["district"] = district_gdp["district"].astype(str).str.strip()
    if len(district_gdp) != 16 or district_gdp["district"].duplicated().any():
        raise ValueError("District GDP CSV must have one unique row for each of 16 districts.")
    if district_gdp["year"].nunique() != 1:
        raise ValueError("District GDP CSV mixes years; a common full year is required.")
    missing_boundary = sorted(set(district_gdp["district"]) - set(districts["district"]))
    missing_gdp = sorted(set(districts["district"]) - set(district_gdp["district"]))
    if missing_boundary or missing_gdp:
        raise ValueError(
            f"District name mismatch; missing boundary={missing_boundary}, missing GDP={missing_gdp}"
        )
    district_gdp["gdp_100m_cny"] = pd.to_numeric(
        district_gdp["gdp_100m_cny"], errors="raise"
    )
    if (district_gdp["gdp_100m_cny"] <= 0).any():
        raise ValueError("Every official district GDP must be positive.")

    city = pd.read_csv(city_gdp_path)
    city_missing = REQUIRED_GDP_COLUMNS - set(city.columns)
    if city_missing or len(city) != 1:
        raise ValueError(
            "City GDP CSV must contain one row with the district-GDP provenance columns."
        )
    city_row = city.iloc[0].copy()
    if int(city_row["year"]) != int(district_gdp["year"].iloc[0]):
        raise ValueError("Shanghai city GDP and district GDP must use the same year.")
    city_row["gdp_100m_cny"] = float(city_row["gdp_100m_cny"])
    if city_row["gdp_100m_cny"] <= 0:
        raise ValueError("Official Shanghai GDP must be positive.")
    return districts_wgs84, districts_metric, district_gdp, city_row
