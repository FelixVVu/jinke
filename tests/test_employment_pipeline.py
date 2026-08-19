import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from employment_pipeline.config import (
    ANALYSIS_CRS,
    CITY_EMPLOYMENT,
    EMPLOYMENT_UNIVERSE,
    NOMINAL_FINE_CONTROL_EMPLOYMENT,
    NOMINAL_RESIDUAL_EMPLOYMENT,
    PRIORITY_DISTRICT_EMPLOYMENT,
)
from employment_pipeline.reach import partial_cell_fractions

ROOT = Path(__file__).resolve().parents[1]
EMPLOYMENT = ROOT / "data/employment"

PROTECTED_SHA256 = {
    "web/public/data/reach-areas.geojson": "6f039b0661f63c1017a2c4a3bc8f5c4d8fdef207ca10afe987f160642fb5656b",
    "web/public/data/reach-economy.json": "4054f47f07afa1e53612b50d965b3094161f43d94e8420a96911d6ac3c5731ca",
    "web/public/data/gdp-methodology.json": "c2f251e7394a53b903f3b577e5fba316292b8e3aecfdf677cfcf881b40dba9eb",
    "data/station_coordinates_416.csv": "f6cdad9e43b5ba584146d109f81f091d2f98c4590bc811aa3c9eed5ec2226d89",
    "web/public/data/stations.geojson": "bdf50465951420171ebb4dad3ad3e28857209ec6b88e6d697d2dceac06d44b02",
    "web/public/data/shanghai-metro-stations.geojson": "049c03c423cf4c83bf3646cd3020b1e82b81cc7015f5f877c9e5e9e651478fff",
    "web/public/data/shanghai-metro-lines.geojson": "901b84b2d416ae1f15de3bfbf421472fff830ae02f37891c773795fae0ce6252",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _as_bool(series: pd.Series) -> pd.Series:
    return series.map(lambda value: value is True or str(value).lower() == "true")


def test_protected_production_inputs_and_gdp_assets_are_unchanged():
    for relative, expected in PROTECTED_SHA256.items():
        assert _sha256(ROOT / relative) == expected


def test_official_universe_controls_and_residuals_reconcile_exactly():
    manifests = EMPLOYMENT / "manifests"
    districts = pd.read_csv(manifests / "district-employment-2023.csv")
    controls = pd.read_csv(
        manifests / "control-crosswalk-2023.csv",
        dtype={"official_control_code_2023": "string", "accounting_stratum_id": "string"},
    )
    residuals = pd.read_csv(manifests / "residual-strata.csv")
    xuhui_individual = pd.read_csv(
        manifests / "xuhui-individual-business-employment-2023.csv"
    )

    assert len(districts) == 16
    assert districts["district"].is_unique
    assert int(districts["employment"].sum()) == CITY_EMPLOYMENT
    assert int(districts.loc[_as_bool(districts["priority_district"]), "employment"].sum()) == (
        PRIORITY_DISTRICT_EMPLOYMENT
    )
    assert not _as_bool(districts["individual_business_included"]).any()
    assert districts["employment_universe"].eq(EMPLOYMENT_UNIVERSE).all()

    xuhui = districts.loc[districts["district"] == "徐汇区"].iloc[0]
    assert int(xuhui["employment"]) == 1_027_746
    assert int(xuhui["individual_business_employment_reported_separately"]) == 17_098
    assert "excluded" in xuhui["individual_business_source_reference"]
    assert int(xuhui_individual["individual_business_employment"].sum()) == 17_098
    assert not _as_bool(
        xuhui_individual["included_in_benchmark_denominator"]
    ).any()

    assert len(controls) == 116
    assert controls["accounting_stratum_id"].is_unique
    assert int(controls["employment_reconciled"].sum()) == NOMINAL_FINE_CONTROL_EMPLOYMENT
    assert not _as_bool(controls["individual_business_included"]).any()
    assert int(residuals["employment_nominal"].sum()) == NOMINAL_RESIDUAL_EMPLOYMENT
    assert NOMINAL_FINE_CONTROL_EMPLOYMENT + NOMINAL_RESIDUAL_EMPLOYMENT == (
        PRIORITY_DISTRICT_EMPLOYMENT
    )

    fine_by_district = controls.groupby("district")["employment_reconciled"].sum()
    residual_by_district = residuals.set_index("district")["employment_nominal"]
    exact_priority = districts.loc[
        _as_bool(districts["priority_district"])
    ].set_index("district")["employment"]
    pd.testing.assert_series_equal(
        (fine_by_district + residual_by_district).sort_index().astype(int),
        exact_priority.sort_index().astype(int),
        check_names=False,
    )

    lower = controls["employment_rounding_lower"].to_numpy(dtype=float)
    upper = controls["employment_rounding_upper_exclusive"].to_numpy(dtype=float)
    central = controls["employment_reconciled"].to_numpy(dtype=float)
    exact = controls["rounding_increment_people"].to_numpy(dtype=float) == 1
    assert np.all(central >= lower)
    assert np.all(exact | (central < upper))
    pudong = controls.loc[controls["district"] == "浦东新区"]
    assert pudong.groupby("subtotal_group")["employment_reconciled"].sum().to_dict() == {
        "Pudong functional zones": 821_000,
        "Pudong streets": 695_000,
        "Pudong towns": 1_099_000,
    }


def test_osm_crosswalk_is_exact_pinned_and_explicitly_approximate():
    path = EMPLOYMENT / "raw/boundaries/osm-priority-controls-2026-08-19.geojson"
    assert _sha256(path) == "d94b7fc3800e8c6bbe3c8b2f376f541b7887f6690a71cee103d53840bdf1a9a9"
    geometry = gpd.read_file(path)
    assert len(geometry) == 113
    assert geometry.crs.to_epsg() == 4326
    assert geometry["official_control_code_2023"].is_unique
    assert geometry["osm_relation_id_source"].is_unique
    assert geometry["official_control_name_2023"].equals(geometry["osm_name"])
    assert geometry["admin_level"].eq("8").all()
    assert geometry["boundary"].eq("administrative").all()
    assert _as_bool(geometry["geometry_is_approximate"]).all()
    assert geometry.geometry.is_valid.all()
    assert not geometry.geometry.is_empty.any()
    assert geometry["license"].str.contains("Open Database License").all()

    boundary = pd.read_csv(
        EMPLOYMENT / "manifests/boundary-manifest.csv",
        dtype={"accounting_stratum_id": "string"},
    )
    assert len(boundary) == 116
    assert boundary["accounting_stratum_id"].is_unique
    assert _as_bool(boundary["geometry_is_approximate"]).all()
    assert set(boundary["official_map_validation_status"]) <= {
        "pass",
        "fail",
        "not_required",
    }
    zones = boundary.loc[boundary["control_type"] == "functional_zone"]
    assert zones["repository_geometry_file"].isna().all()
    assert zones["redistribution_status"].str.contains("not redistributed").all()

    review = pd.read_csv(EMPLOYMENT / "intermediate/official-map-visual-review.csv")
    assert len(review) == 82
    assert review["review_status"].isin(["pass", "fail"]).all()
    assert review["source_map"].str.contains("tianditu", case=False).all()
    assert review["discrepancy_description"].str.len().gt(0).all()
    assert review["could_materially_change_reach_employment"].isin(["yes", "no"]).all()


def test_public_grid_is_auditable_nonnegative_and_control_preserving():
    controls = pd.read_csv(
        EMPLOYMENT / "manifests/control-crosswalk-2023.csv",
        dtype={"accounting_stratum_id": "string"},
    ).set_index("accounting_stratum_id")
    grid = gpd.read_parquet(
        EMPLOYMENT / "intermediate/employment-allocation-grid.parquet"
    )
    assert grid.crs.to_string() == ANALYSIS_CRS
    assert grid["cell_id"].is_unique
    assert _as_bool(grid["geometry_is_approximate"]).all()
    assert grid["employment_universe"].eq(EMPLOYMENT_UNIVERSE).all()
    assert (grid["cell_area_m2"] > 0).all()

    redacted = grid.loc[grid.geometry.isna()]
    assert len(redacted) == 3
    assert redacted["control_type"].eq("functional_zone").all()
    assert _as_bool(redacted["geometry_redacted"]).all()
    visible = grid.loc[grid.geometry.notna()]
    assert visible.geometry.is_valid.all()
    assert not visible.geometry.is_empty.any()

    employment_columns = [
        "cell_employment_uniform",
        "cell_employment_building_volume",
        "cell_employment_calibrated_workplace",
        "cell_employment_residual_central",
        "cell_employment_preferred",
    ]
    for column in employment_columns:
        values = grid[column].to_numpy(dtype=float)
        assert np.isfinite(values).all()
        assert (values >= 0).all()

    fine = grid.loc[grid["control_type"] != "residual_finance"]
    for column in (
        "cell_employment_uniform",
        "cell_employment_building_volume",
        "cell_employment_calibrated_workplace",
    ):
        observed = fine.groupby("accounting_control")[column].sum().reindex(controls.index)
        assert np.allclose(
            observed.to_numpy(dtype=float),
            controls["employment_reconciled"].to_numpy(dtype=float),
            atol=1e-5,
        )


def test_partial_cell_intersection_uses_clipped_cell_area():
    grid = gpd.GeoDataFrame(
        {"cell_area_m2": [10_000.0, 5_000.0]},
        geometry=[box(0, 0, 100, 100), box(100, 0, 150, 100)],
        crs=ANALYSIS_CRS,
    )
    reach = box(0, 0, 125, 100)
    assert partial_cell_fractions(grid, reach).tolist() == [1.0, 0.5]


def test_reach_outputs_are_monotonic_bounded_and_use_fixed_denominator():
    payload = json.loads((ROOT / "web/public/data/reach-employment.json").read_text())
    assert payload["denominator"] == CITY_EMPLOYMENT
    assert payload["employment_universe"] == EMPLOYMENT_UNIVERSE
    assert payload["geometry_is_approximate"] is True
    results = pd.DataFrame(payload["results"])
    assert results["limit_minutes"].tolist() == [10, 20, 30, 40, 50]
    for column in (
        "central_estimated_employment",
        "uniform_allocation_employment",
        "building_volume_employment",
        "calibrated_workplace_model_employment",
        "residual_lower_bound_employment",
        "residual_upper_bound_employment",
    ):
        assert np.all(np.diff(results[column].to_numpy(dtype=float)) >= -1e-6)
    assert (
        results["residual_lower_bound_employment"]
        <= results["central_estimated_employment"]
    ).all()
    assert (
        results["central_estimated_employment"]
        <= results["residual_upper_bound_employment"]
    ).all()
    assert np.allclose(
        results["percentage_of_shanghai_employment"],
        results["central_estimated_employment"] / CITY_EMPLOYMENT * 100.0,
    )
    expected_increment = results["central_estimated_employment"].diff()
    expected_increment.iloc[0] = results["central_estimated_employment"].iloc[0]
    assert np.allclose(results["incremental_employment"], expected_increment)
    assert _as_bool(results["geometry_is_approximate"]).all()
    assert results["approximate_boundary_disclosure"].str.contains("OSM").all()
    assert _as_bool(results["boundary_sensitivity_components_are_not_added"]).all()


def test_model_diagnostics_rounding_and_district_contributions_are_complete():
    diagnostics = json.loads(
        (EMPLOYMENT / "intermediate/model-diagnostics.json").read_text()
    )
    assert diagnostics["final_fit"]["converged"] is True
    assert diagnostics["selected_alpha"] > 0
    assert "geographic-block" in diagnostics["cross_validation_design"]
    assert set(diagnostics["all_control_metrics"]) >= {
        "mae_people",
        "mean_absolute_percentage_error",
        "weighted_absolute_percentage_error",
        "spearman_rank_correlation",
    }
    assert all(
        value >= 0
        for value in diagnostics["final_fit"][
            "standardized_spatial_coefficients"
        ].values()
    )
    assert "no cap" in diagnostics["upper_tail_treatment"]
    assert isinstance(diagnostics["obvious_high_employment_underprediction"], list)

    rounding = pd.read_csv(EMPLOYMENT / "intermediate/rounding-sensitivity.csv")
    assert (
        rounding["rounding_minimum_employment_with_fixed_district_totals"]
        <= rounding["central_employment_with_fixed_district_totals"]
    ).all()
    assert (
        rounding["central_employment_with_fixed_district_totals"]
        <= rounding["rounding_maximum_employment_with_fixed_district_totals"]
    ).all()
    fifty_rounding = rounding.loc[rounding["limit_minutes"] == 50].iloc[0]
    assert max(
        abs(fifty_rounding["rounding_minus_percentage_points"]),
        abs(fifty_rounding["rounding_plus_percentage_points"]),
    ) < 0.1

    reach = pd.read_csv(EMPLOYMENT / "outputs/employment-reach-summary.csv")
    fifty = reach.loc[reach["limit_minutes"] == 50].iloc[0]
    district = pd.read_csv(EMPLOYMENT / "outputs/district-50min-contributions.csv")
    assert int(district["exact_district_employment"].sum()) == PRIORITY_DISTRICT_EMPLOYMENT
    assert int(round(district["fine_controlled_employment"].sum())) == (
        NOMINAL_FINE_CONTROL_EMPLOYMENT
    )
    assert int(district["residual_employment"].sum()) == NOMINAL_RESIDUAL_EMPLOYMENT
    assert np.isclose(
        district["employment_inside_50min"].sum(),
        fifty["central_estimated_employment"],
    )

    pudong = pd.read_csv(EMPLOYMENT / "outputs/pudong-50min-strata.csv").set_index(
        "reporting_stratum"
    )
    expected_pudong = pd.Series({
        "FTZ Bonded Area": 149_000.0,
        "Jinqiao ETDZ": 203_000.0,
        "Pudong residual": 264_157.0,
        "Zhangjiang High-Tech Park": 469_000.0,
        "ordinary streets/towns": 1_794_000.0,
    })
    assert np.allclose(
        pudong["stratum_employment"].reindex(expected_pudong.index),
        expected_pudong,
    )
    assert np.isclose(pudong["stratum_employment"].sum(), 2_879_157)


def test_methodology_retains_prohibited_source_and_boundary_disclosures():
    methodology = json.loads(
        (ROOT / "web/public/data/employment-methodology.json").read_text()
    )
    assert methodology["denominator"] == CITY_EMPLOYMENT
    assert methodology["individual_business_employment_included"] is False
    assert methodology["analysis"]["crs"] == ANALYSIS_CRS
    assert methodology["analysis"]["grid_metres"] == 100
    assert methodology["analysis"]["production_reach_modified"] is False
    assert methodology["ordinary_boundary"]["geometry_is_approximate"] is True
    assert "ODbL" in methodology["ordinary_boundary"]["license"]
    assert methodology["pudong_functional_zones"]["source_geometry_redistributed"] is False
    assert methodology["prohibited_inputs"] == {
        "openrouteservice_called": False,
        "job_posting_counts_used": False,
        "existing_gdp_model_reused_as_primary_employment_model": False,
    }
    sliver = json.loads(
        (EMPLOYMENT / "outputs/minhang-sliver-sensitivity.json").read_text()
    )
    assert np.isclose(sliver["intersection_area_m2"], 2915.159950421586)
    assert sliver["employment_assigned"] == 0
