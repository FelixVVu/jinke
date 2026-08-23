import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SPATIAL = ROOT / "data/office_employment/spatial"
OUTPUTS = SPATIAL / "outputs"

PRIORITY_DISTRICTS = {
    "黄浦区",
    "徐汇区",
    "长宁区",
    "静安区",
    "普陀区",
    "虹口区",
    "杨浦区",
    "浦东新区",
}
CORE_CODES = ("I", "J", "M")
CORE_PLUS_CODES = ("721", "723", "724", "725")
SCENARIOS = ("low_office_intensity", "base", "high_office_intensity")

PROTECTED_SHA256 = {
    "web/public/data/reach-employment.json": "7f4a7447e52f70c595e3be9d0b38e1fc3ec06e9c8c3e3350a095b997cc87b105",
    "web/public/data/employment-methodology.json": "bd1eacdcd51725c9443c20aa11841941ea9120f8c76571bbf009efd75cdc152c",
    "web/public/data/reach-economy.json": "4054f47f07afa1e53612b50d965b3094161f43d94e8420a96911d6ac3c5731ca",
    "web/public/data/gdp-methodology.json": "c2f251e7394a53b903f3b577e5fba316292b8e3aecfdf677cfcf881b40dba9eb",
    "web/public/data/reach-areas.geojson": "6f039b0661f63c1017a2c4a3bc8f5c4d8fdef207ca10afe987f160642fb5656b",
    "data/employment/intermediate/employment-allocation-grid.parquet": "12de4bd6c3f8df26c7702f1a4ff0f6aed797068d3f571a6ccabdd6b5f6f8c1b7",
    "data/office_employment/outputs/district-core-plus-controls-2023.csv": "ba20d46e2afe336d334513c8ff12686027f3362d23f2a7a488072345d7023eb2",
    "data/office_employment/scenarios/district-core-plus-scenarios-2023.csv": "9c44dab573c4223685d219db2d6549035e835e2699aebbba767419baac5240dc",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_protected_gdp_employment_reach_and_office_controls_are_unchanged():
    observed = {path: _sha256(ROOT / path) for path in PROTECTED_SHA256}
    assert observed == PROTECTED_SHA256


def test_spatial_summary_enforces_method_boundary_and_fixed_city_controls():
    summary = json.loads(
        (OUTPUTS / "spatial-allocation-summary.json").read_text(encoding="utf-8")
    )
    assert summary["city_core_hard_control"] == 2_477_585
    assert summary["city_core_plus_control_each_scenario"] == 3_220_710
    assert summary["spatial_scope_districts"] == [
        "黄浦区",
        "徐汇区",
        "长宁区",
        "静安区",
        "普陀区",
        "虹口区",
        "杨浦区",
        "浦东新区",
    ]
    assert summary["core_is_hard_control"] is True
    assert summary["core_plus_base_is_central_case"] is True
    assert summary["low_and_high_core_plus_retained"] is True
    assert summary["uniform_allocation_used_as_main"] is False
    assert summary["generic_ppml_fitted"] is False
    assert summary["spatial_smoothing_or_winsorization_used"] is False
    assert summary["grid_created"] is True
    assert summary["reach_intersection_calculated"] is False
    assert summary["reach_percentage_calculated"] is False
    assert summary["production_outputs_modified"] is False
    assert summary["geometry_is_approximate"] is True
    assert np.isclose(sum(summary["component_shares"].values()), 1.0)
    assert summary["component_shares"] == {
        "jrc_nonresidential_volume": 0.60,
        "osm_building_function_footprint": 0.25,
        "osm_office_establishments": 0.10,
        "overture_poi_supplement": 0.05,
    }


def test_core_grid_is_unique_valid_nonnegative_and_matches_hard_controls():
    core = gpd.read_parquet(OUTPUTS / "core-employment-grid-100m.parquet")
    controls = pd.read_csv(
        ROOT
        / "data/office_employment/intermediate/district-industry-employment-2023.csv",
        dtype={"industry_code": str},
    )
    controls = controls.loc[
        controls["district"].isin(PRIORITY_DISTRICTS)
        & controls["industry_code"].isin(CORE_CODES)
    ]
    assert len(core) == 172_233
    assert core.crs.to_epsg() == 32651
    assert core["cell_id"].is_unique
    assert set(core["district"]) == PRIORITY_DISTRICTS
    assert core.geometry.is_valid.all()
    assert not core.geometry.is_empty.any()
    assert core["geometry_is_approximate"].all()
    assert not core["reach_intersection_calculated"].any()
    for code in CORE_CODES:
        assert (core[f"cell_employment_{code}"] >= 0).all()
        allocated = core.groupby("district")[f"cell_employment_{code}"].sum()
        expected = (
            controls.loc[controls["industry_code"] == code]
            .set_index("district")["district_industry_employment"]
            .reindex(allocated.index)
        )
        pd.testing.assert_series_equal(
            allocated.astype(int), expected.astype(int), check_names=False
        )
        weights = core.groupby("district")[f"allocation_weight_{code}"].sum()
        assert np.allclose(weights, 1.0, atol=1e-12)
    assert core["cell_employment_core"].equals(
        core[[f"cell_employment_{code}" for code in CORE_CODES]].sum(axis=1)
    )
    hard = pd.read_csv(
        ROOT / "data/office_employment/outputs/district-office-employment-controls-2023.csv"
    ).set_index("district")["core_office_employment"]
    observed = core.groupby("district")["cell_employment_core"].sum()
    pd.testing.assert_series_equal(
        observed.sort_index().astype(int),
        hard.loc[list(PRIORITY_DISTRICTS)].sort_index().astype(int),
        check_names=False,
    )


def test_core_plus_base_and_sensitivity_preserve_every_district_subgroup_control():
    base = gpd.read_parquet(
        OUTPUTS / "core-plus-base-employment-grid-100m.parquet"
    )
    sensitivity = gpd.read_parquet(
        OUTPUTS / "core-plus-sensitivity-grid-100m.parquet"
    )
    controls = pd.read_csv(
        ROOT
        / "data/office_employment/scenarios/district-business-services-subgroup-scenarios-2023.csv",
        dtype={"industry_code": str},
    )
    controls = controls.loc[controls["district"].isin(PRIORITY_DISTRICTS)]
    assert base["cell_id"].equals(sensitivity["cell_id"])
    assert base.geometry.to_wkb().equals(sensitivity.geometry.to_wkb())
    assert base["cell_employment_core"].equals(
        sensitivity["cell_employment_core"]
    )
    for code in CORE_PLUS_CODES:
        weights = base.groupby("district")[f"allocation_weight_{code}"].sum()
        assert np.allclose(weights, 1.0, atol=1e-12)
        for scenario in SCENARIOS:
            allocated = sensitivity.groupby("district")[
                f"cell_employment_{code}_{scenario}"
            ].sum()
            expected = (
                controls.loc[
                    (controls["scenario"] == scenario)
                    & (controls["industry_code"] == code)
                ]
                .set_index("district")["scenario_district_subgroup_employment"]
                .reindex(allocated.index)
            )
            pd.testing.assert_series_equal(
                allocated.astype(int), expected.astype(int), check_names=False
            )
        assert base[f"cell_employment_{code}"].equals(
            sensitivity[f"cell_employment_{code}_base"]
        )
    assert base["cell_employment_core_plus_base"].equals(
        base["cell_employment_core"]
        + base[[f"cell_employment_{code}" for code in CORE_PLUS_CODES]].sum(axis=1)
    )
    assert not base["reach_intersection_calculated"].any()
    assert not sensitivity["reach_intersection_calculated"].any()


def test_low_base_high_priority_comparison_is_exact_and_symmetric():
    sensitivity = gpd.read_parquet(
        OUTPUTS / "core-plus-sensitivity-grid-100m.parquet"
    )
    totals = {
        scenario: int(
            sensitivity[f"cell_employment_core_plus_{scenario}"].sum()
        )
        for scenario in SCENARIOS
    }
    assert totals == {
        "low_office_intensity": 2_323_401,
        "base": 2_336_384,
        "high_office_intensity": 2_349_367,
    }
    assert totals["base"] - totals["low_office_intensity"] == 12_983
    assert totals["high_office_intensity"] - totals["base"] == 12_983
    assert int(sensitivity["cell_employment_core_plus_low_minus_base"].sum()) == -12_983
    assert int(sensitivity["cell_employment_core_plus_high_minus_base"].sum()) == 12_983


def test_allocation_diagnostics_reconcile_and_retain_concentration():
    diagnostics = pd.read_csv(OUTPUTS / "allocation-diagnostics.csv")
    assert len(diagnostics) == 120
    assert set(diagnostics["district"]) == PRIORITY_DISTRICTS
    assert set(diagnostics["industry_code"].astype(str)) == {
        *CORE_CODES,
        *CORE_PLUS_CODES,
    }
    assert (diagnostics["reconciliation_difference"] == 0).all()
    assert diagnostics["no_log_cap_winsorize_or_minmax"].all()
    assert not diagnostics["generic_ppml_fitted"].any()
    assert not diagnostics["uniform_allocation_used_as_main"].any()
    assert diagnostics["gini_cell_employment"].between(0, 1).all()
    assert diagnostics["top_1_percent_cell_employment_share"].between(0, 1).all()
    assert (diagnostics["positive_weight_cells"] > 0).all()
    assert (diagnostics["maximum_cell_employment"] > 0).all()


def test_building_evidence_and_source_manifest_are_frozen_and_attributed():
    evidence_path = SPATIAL / "intermediate/building-function-evidence-100m.parquet"
    evidence = pd.read_parquet(evidence_path)
    quality = json.loads(
        (SPATIAL / "intermediate/building-evidence-quality.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = pd.read_csv(SPATIAL / "manifests/source-manifest.csv")
    assert len(evidence) == 172_233
    assert evidence["cell_id"].is_unique
    assert set(evidence["district"]) == PRIORITY_DISTRICTS
    assert (evidence.filter(like="_footprint_m2") >= 0).all().all()
    assert (evidence["osm_office_establishment_count"] >= 0).all()
    assert quality["osm_source_sha256"] == (
        "3b6e8bb207db37e6d86546c8e73fcfb3a68b8b6c744f74ed1d5d645bc7873099"
    )
    assert quality["building_levels_used_in_allocation"] is False
    osm = manifest.set_index("source_id").loc["osm-building-function-2026-08-23"]
    assert "Open Database License" in osm["license_or_reuse"]
    assert osm["derived_sha256"] == _sha256(evidence_path)
    assert manifest["used_for"].str.len().gt(0).all()


def test_cluster_validation_maps_are_complete_and_honest():
    clusters = pd.read_csv(OUTPUTS / "cluster-validation.csv")
    assert len(clusters) == 7
    assert clusters["cluster_id"].is_unique
    assert clusters["cluster_emerges_under_declared_rule"].all()
    assert int(clusters["strong_cluster_emerges_under_declared_rule"].sum()) == 4
    assert not clusters["reach_polygon_used"].any()
    assert (clusters["local_to_district_density_ratio"] >= 1.0).all()
    assert (
        clusters["maximum_local_cell_percentile_among_positive_cells"] >= 95.0
    ).all()
    for cluster_id in clusters["cluster_id"]:
        path = SPATIAL / "maps" / f"cluster-{cluster_id}.png"
        assert path.is_file() and path.stat().st_size > 50_000
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.width >= 1_000
            assert image.height >= 1_000


def test_saved_output_hashes_and_report_match_review_artifacts():
    summary = json.loads(
        (OUTPUTS / "spatial-allocation-summary.json").read_text(encoding="utf-8")
    )
    expected_paths = {
        "core_grid": OUTPUTS / "core-employment-grid-100m.parquet",
        "core_plus_base_grid": OUTPUTS
        / "core-plus-base-employment-grid-100m.parquet",
        "core_plus_sensitivity_grid": OUTPUTS
        / "core-plus-sensitivity-grid-100m.parquet",
        "allocation_diagnostics": OUTPUTS / "allocation-diagnostics.csv",
    }
    assert summary["output_sha256"] == {
        key: _sha256(path) for key, path in expected_paths.items()
    }
    report = (OUTPUTS / "spatial-allocation-report.md").read_text(encoding="utf-8")
    assert "No reach polygon was intersected" in report
    assert "no reach result or percentage" in report
    assert "generic PPML" in report
    assert "All **7 of 7**" in report
