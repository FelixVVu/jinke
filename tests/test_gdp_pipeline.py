import hashlib
import json
import zipfile
from pathlib import Path

import geopandas as gpd
import h5py
import numpy as np
import pandas as pd
from shapely.geometry import Point, box

from gdp_pipeline.calibration import allocate_district_gdp, build_district_calibration
from gdp_pipeline.config import LIMITS, SCENARIOS
from gdp_pipeline.export import export_audit_outputs
from gdp_pipeline.grid import (
    add_viirs_radiance,
    classify_economic_category,
    robust_normalize,
)
from gdp_pipeline.inputs import load_district_inputs
from gdp_pipeline.reach import calculate_reach_gdp
from gdp_pipeline import sources as source_helpers

ROOT = Path(__file__).resolve().parents[1]
BOUNDARIES = ROOT / "data/economy/shanghai-district-boundaries.geojson"
DISTRICT_GDP = ROOT / "data/economy/shanghai-district-gdp.csv"
CITY_GDP = ROOT / "data/economy/shanghai-city-gdp.csv"


def test_pinned_district_boundaries_and_official_gdp_are_complete():
    wgs84, metric, district_gdp, city = load_district_inputs(
        BOUNDARIES, DISTRICT_GDP, CITY_GDP
    )
    assert len(wgs84) == len(metric) == len(district_gdp) == 16
    assert wgs84["district"].is_unique
    assert district_gdp["district"].is_unique
    assert district_gdp["year"].unique().tolist() == [2025]
    assert int(city["year"]) == 2025
    assert float(city["gdp_100m_cny"]) == 56708.71
    assert np.isclose(district_gdp["gdp_100m_cny"].sum(), 56468.79)
    assert metric.crs.to_epsg() == 32651
    assert metric.geometry.is_valid.all()
    assert metric.geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all()
    assert all(
        str(url).startswith("https://")
        for url in district_gdp["source_url"]
    )


def test_production_reach_polygons_are_pinned_and_unmodified():
    path = ROOT / "web/public/data/reach-areas.geojson"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "6f039b0661f63c1017a2c4a3bc8f5c4d8fdef207ca10afe987f160642fb5656b"
    )


def test_robust_normalization_is_bounded_and_does_not_invent_activity():
    values = pd.Series([0, 0, 1, 2, 10_000, np.nan, -4])
    normalized = robust_normalize(values)
    assert normalized.between(0, 1).all()
    assert (normalized.iloc[[0, 1, 5, 6]] == 0).all()
    assert normalized.max() == 1


def test_overture_economic_category_rules_are_explicit():
    assert classify_economic_category("restaurant") == "food_hospitality"
    assert classify_economic_category("industrial_warehouse") == "industry_logistics"
    assert classify_economic_category("university") == "education_research"
    assert classify_economic_category("mountain_peak") is None


def test_cmr_discovery_keeps_only_http_2025_science_granule(monkeypatch):
    expected = (
        "https://data.laadsdaac.earthdatacloud.nasa.gov/prod-lads/VNP46A4/"
        "VNP46A4.A2025001.h30v05.002.example.h5"
    )

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "feed": {
                    "entry": [
                        {
                            "links": [
                                {"href": expected},
                                {"href": "s3://bucket/VNP46A4.A2025001.h30v05.002.example.h5"},
                                {"href": expected.replace("A2025001", "A2026001")},
                                {"href": expected + ".xml"},
                            ]
                        }
                    ]
                }
            }

    monkeypatch.setattr(source_helpers.requests, "get", lambda *args, **kwargs: Response())
    assert source_helpers.discover_viirs_granules((120, 30, 123, 32)) == [expected]


def test_viirs_extraction_applies_scale_and_excludes_nonzero_quality(tmp_path):
    granule = tmp_path / "VNP46A4.A2025001.h30v05.002.test.h5"
    with h5py.File(granule, "w") as handle:
        group = handle.create_group("HDFEOS/GRIDS/VNP_Grid_DNB/Data Fields")
        radiance = group.create_dataset(
            "NearNadir_Composite_Snow_Free",
            data=np.array([[10.0, 20.0], [30.0, -999.9]], dtype=np.float32),
        )
        radiance.attrs["scale_factor"] = 0.1
        radiance.attrs["add_offset"] = 1.0
        radiance.attrs["_FillValue"] = -999.9
        group.create_dataset(
            "NearNadir_Composite_Snow_Free_Quality",
            data=np.array([[0, 1], [0, 0]], dtype=np.uint8),
        )
    grid = gpd.GeoDataFrame(
        {
            "center_x": [121.0, 126.0, 121.0, 126.0],
            "center_y": [39.0, 39.0, 34.0, 34.0],
        },
        geometry=[Point(121, 39), Point(126, 39), Point(121, 34), Point(126, 34)],
        crs="EPSG:4326",
    )
    result = add_viirs_radiance(grid, [granule])
    assert result["viirs_quality"].tolist() == [0, 1, 0, 0]
    assert result["viirs_quality_good"].tolist() == [True, False, True, True]
    assert result["viirs_radiance"].iloc[0] == 2.0
    assert np.isnan(result["viirs_radiance"].iloc[1])
    assert result["viirs_radiance"].iloc[2] == 4.0
    assert np.isnan(result["viirs_radiance"].iloc[3])


def test_overture_download_pins_release_and_clips_exact_boundary(tmp_path, monkeypatch):
    districts = gpd.GeoDataFrame(
        {"district": ["test"]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:4326"
    )
    monkeypatch.setattr(source_helpers, "latest_overture_release", lambda: "2026-07-22.0")
    observed: dict[str, list[str]] = {}

    def fake_run(command, check):
        assert check is True
        observed["command"] = command
        output = Path(command[command.index("-o") + 1])
        gpd.GeoDataFrame(
            {"id": ["inside", "bbox-only"]},
            geometry=[Point(0.5, 0.5), Point(0.5, 1.5)],
            crs="EPSG:4326",
        ).to_parquet(output, index=False)

    monkeypatch.setattr(source_helpers.subprocess, "run", fake_run)
    path, metadata = source_helpers.download_overture_places(districts, tmp_path)
    cached = gpd.read_parquet(path)
    assert cached["id"].tolist() == ["inside"]
    assert metadata["release"] == "2026-07-22.0"
    assert metadata["rows_intersecting_shanghai"] == 1
    assert "--release" in observed["command"]
    assert "2026-07-22.0" in observed["command"]


def test_reconciliation_preserves_raw_values_and_allocation_hits_targets():
    district_source = pd.DataFrame(
        {
            "district": ["甲", "乙"],
            "year": [2025, 2025],
            "gdp_100m_cny": [100.0, 200.0],
            "source_url": ["https://example.gov/1", "https://example.gov/2"],
            "source_title": ["one", "two"],
            "retrieved_date": ["2026-08-13", "2026-08-13"],
        }
    )
    original = district_source.copy(deep=True)
    city = pd.Series({"gdp_100m_cny": 330.0})
    calibration, factor = build_district_calibration(district_source, city)
    pd.testing.assert_frame_equal(district_source, original)
    assert factor == 1.1
    assert calibration["raw_gdp_100m_cny"].tolist() == [100.0, 200.0]

    grid = gpd.GeoDataFrame(
        {
            "district": ["甲", "甲", "乙", "乙"],
            "weight_central": [1.0, 3.0, 1.0, 1.0],
            "weight_building_heavy": [2.0, 2.0, 3.0, 1.0],
            "weight_activity_heavy": [1.0, 1.0, 1.0, 3.0],
        },
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1), box(2, 0, 3, 1), box(3, 0, 4, 1)],
        crs="EPSG:32651",
    )
    allocated = allocate_district_gdp(grid, calibration)
    for column in (
        "estimated_gdp_100m_cny",
        "building_heavy_gdp_100m_cny",
        "activity_heavy_gdp_100m_cny",
    ):
        totals = allocated.groupby("district")[column].sum()
        assert np.isclose(totals["甲"], 110.0)
        assert np.isclose(totals["乙"], 220.0)


def test_area_weighted_reach_is_monotonic_for_partial_cells():
    grid = gpd.GeoDataFrame(
        {
            "cell_area_m2": [10_000.0, 10_000.0],
            "estimated_gdp_100m_cny": [100.0, 100.0],
            "building_heavy_gdp_100m_cny": [90.0, 110.0],
            "activity_heavy_gdp_100m_cny": [110.0, 90.0],
        },
        geometry=[box(0, 0, 100, 100), box(100, 0, 200, 100)],
        crs="EPSG:32651",
    )
    reaches = gpd.GeoDataFrame(
        {"limit": list(LIMITS)},
        geometry=[
            box(0, 0, 50, 100),
            box(0, 0, 100, 100),
            box(0, 0, 150, 100),
            box(0, 0, 200, 100),
            box(0, 0, 200, 100),
        ],
        crs=grid.crs,
    )
    result = calculate_reach_gdp(grid, reaches, 200.0)
    assert result["estimated_gdp_100m_cny"].tolist() == [50, 100, 150, 200, 200]
    assert result["incremental_gdp_100m_cny"].tolist() == [50, 50, 50, 50, 0]
    assert result["percentage_of_shanghai_gdp"].tolist() == [25, 50, 75, 100, 100]


def test_export_zip_is_lightweight_and_exact(tmp_path):
    grid = gpd.GeoDataFrame(
        {"cell_id": ["x"], "estimated_gdp_100m_cny": [1.0]},
        geometry=[box(0, 0, 1, 1)],
        crs="EPSG:32651",
    )
    calibration = pd.DataFrame({"district": ["x"], "raw_gdp_100m_cny": [1.0]})
    reach = pd.DataFrame(
        {
            "limit_minutes": list(LIMITS),
            "estimated_gdp_100m_cny": [1, 2, 3, 4, 5],
            "percentage_of_shanghai_gdp": [1, 2, 3, 4, 5],
            "incremental_gdp_100m_cny": [1, 1, 1, 1, 1],
            "building_heavy_gdp_100m_cny": [1, 2, 3, 4, 5],
            "activity_heavy_gdp_100m_cny": [1, 2, 3, 4, 5],
        }
    )
    paths = export_audit_outputs(
        audit_dir=tmp_path,
        grid=grid,
        calibration=calibration,
        reach=reach,
        methodology={"scenarios": SCENARIOS},
        validation_report={"status": "passed"},
    )
    with zipfile.ZipFile(paths["web_zip"]) as archive:
        assert sorted(archive.namelist()) == [
            "gdp-methodology.json",
            "reach-economy.json",
        ]
        records = json.loads(archive.read("reach-economy.json"))
        assert [record["limit_minutes"] for record in records] == list(LIMITS)
        assert "shanghai-gdp-grid.parquet" not in archive.namelist()
