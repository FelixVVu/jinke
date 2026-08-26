import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SPATIAL = ROOT / "data/office_employment/spatial"
INTERMEDIATE = SPATIAL / "intermediate"
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
OFFICE_CODES = (*CORE_CODES, *CORE_PLUS_CODES)
MATRIX_CODES = (*OFFICE_CODES, "OTHER")
SCENARIOS = ("low_office_intensity", "base", "high_office_intensity")
WEIGHTING_SCENARIOS = (
    "base",
    "building_volume_dominant",
    "workplace_evidence_emphasis",
)

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


def _matrix() -> pd.DataFrame:
    return pd.read_csv(
        INTERMEDIATE / "control-industry-matrix-2023.csv",
        dtype={"accounting_stratum_id": str, "industry_code": str},
    )


def test_protected_gdp_employment_reach_and_office_controls_are_unchanged():
    observed = {path: _sha256(ROOT / path) for path in PROTECTED_SHA256}
    assert observed == PROTECTED_SHA256


def test_summary_declares_fine_controls_weight_sensitivities_and_method_boundary():
    summary = json.loads(
        (OUTPUTS / "spatial-allocation-summary.json").read_text(encoding="utf-8")
    )
    assert summary["schema_version"] == 2
    assert summary["city_core_hard_control"] == 2_477_585
    assert summary["city_core_plus_control_each_scenario"] == 3_220_710
    assert summary["fine_accounting_control_count"] == 116
    assert summary["ordinary_control_count"] == 113
    assert summary["pudong_functional_zone_count"] == 3
    assert summary["district_residual_overlay_count"] == 8
    assert summary["fine_controls_are_hard_geographic_controls"] is True
    assert summary["pudong_functional_zones_counted_once_as_separate_strata"] is True
    assert summary["restricted_zone_geometry_redistributed"] is False
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
    assert summary["component_shares"] == {
        "jrc_nonresidential_volume": 0.60,
        "osm_building_function_footprint": 0.25,
        "osm_office_establishments": 0.10,
        "overture_poi_supplement": 0.05,
    }
    assert set(summary["weighting_scenarios"]) == set(WEIGHTING_SCENARIOS)
    for definition in summary["weighting_scenarios"].values():
        assert np.isclose(sum(definition["shares"].values()), 1.0)


def test_control_industry_matrix_preserves_every_row_and_column_margin():
    matrix = _matrix()
    fine = pd.read_csv(
        ROOT / "data/employment/manifests/control-crosswalk-2023.csv",
        dtype={"accounting_stratum_id": str},
    )
    fine = fine.loc[fine["district"].isin(PRIORITY_DISTRICTS)]
    residual = pd.read_csv(
        ROOT / "data/employment/manifests/residual-strata.csv",
        dtype={"residual_id": str},
    )
    residual = residual.loc[residual["district"].isin(PRIORITY_DISTRICTS)]
    district_industry = pd.read_csv(
        ROOT
        / "data/office_employment/intermediate/district-industry-employment-2023.csv",
        dtype={"industry_code": str},
    )
    subgroup = pd.read_csv(
        ROOT
        / "data/office_employment/scenarios/district-business-services-subgroup-scenarios-2023.csv",
        dtype={"industry_code": str},
    )
    assert len(matrix) == 2_976
    assert not matrix.duplicated(
        ["scenario", "accounting_stratum_id", "industry_code"]
    ).any()
    assert set(matrix["scenario"]) == set(SCENARIOS)
    assert set(matrix["industry_code"]) == set(MATRIX_CODES)
    assert (matrix["control_industry_employment"] >= 0).all()
    assert matrix.loc[matrix["row_is_official_fine_control"], "accounting_stratum_id"].nunique() == 116
    assert matrix["accounting_stratum_id"].nunique() == 124

    expected_rows = pd.concat(
        [
            fine.set_index("accounting_stratum_id")["employment_reconciled"],
            residual.set_index("residual_id")["employment_nominal"],
        ]
    ).astype(int)
    for scenario in SCENARIOS:
        current = matrix.loc[matrix["scenario"].eq(scenario)]
        observed_rows = current.groupby("accounting_stratum_id")[
            "control_industry_employment"
        ].sum()
        pd.testing.assert_series_equal(
            observed_rows.sort_index().astype(int),
            expected_rows.sort_index().astype(int),
            check_names=False,
        )
        assert int(observed_rows.sum()) == 7_640_573
        observed_columns = current.groupby(["district", "industry_code"])[
            "control_industry_employment"
        ].sum()
        for code in CORE_CODES:
            expected = (
                district_industry.loc[
                    district_industry["district"].isin(PRIORITY_DISTRICTS)
                    & district_industry["industry_code"].eq(code)
                ]
                .set_index("district")["district_industry_employment"]
                .astype(int)
            )
            actual = observed_columns.xs(code, level="industry_code")
            pd.testing.assert_series_equal(
                actual.sort_index().astype(int),
                expected.sort_index().astype(int),
                check_names=False,
            )
        for code in CORE_PLUS_CODES:
            expected = (
                subgroup.loc[
                    subgroup["scenario"].eq(scenario)
                    & subgroup["district"].isin(PRIORITY_DISTRICTS)
                    & subgroup["industry_code"].eq(code)
                ]
                .set_index("district")["scenario_district_subgroup_employment"]
                .astype(int)
            )
            actual = observed_columns.xs(code, level="industry_code")
            pd.testing.assert_series_equal(
                actual.sort_index().astype(int),
                expected.sort_index().astype(int),
                check_names=False,
            )


def test_pudong_zones_are_separate_immutable_rows_and_not_double_counted():
    matrix = _matrix()
    zones = matrix.loc[
        matrix["scenario"].eq("base")
        & matrix["control_type"].eq("functional_zone")
    ]
    totals = zones.groupby("accounting_stratum_id")[
        "control_industry_employment"
    ].sum()
    assert totals.to_dict() == {
        "310115501000": 149_000,
        "310115502000": 203_000,
        "310115503000": 469_000,
    }
    assert zones["accounting_stratum_id"].nunique() == 3
    assert not list(ROOT.rglob("31011550*-ruiduobao-2020.geojson"))


def test_core_and_core_plus_grids_preserve_district_industry_controls():
    core = gpd.read_parquet(OUTPUTS / "core-employment-grid-100m.parquet")
    base = gpd.read_parquet(OUTPUTS / "core-plus-base-employment-grid-100m.parquet")
    matrix = _matrix()
    assert len(core) == len(base) == 172_233
    assert core.crs.to_epsg() == base.crs.to_epsg() == 32651
    assert core["cell_id"].is_unique and base["cell_id"].is_unique
    assert set(core["district"]) == PRIORITY_DISTRICTS
    assert core.geometry.is_valid.all() and base.geometry.is_valid.all()
    assert not core.geometry.is_empty.any() and not base.geometry.is_empty.any()
    assert core["geometry_is_approximate"].all()
    assert base["geometry_is_approximate"].all()
    assert not core["reach_intersection_calculated"].any()
    assert not base["reach_intersection_calculated"].any()

    matrix_base = matrix.loc[matrix["scenario"].eq("base")]
    for code in CORE_CODES:
        expected = matrix_base.loc[
            matrix_base["industry_code"].eq(code)
        ].groupby("district")["control_industry_employment"].sum()
        actual = core.groupby("district")[f"cell_employment_{code}"].sum()
        pd.testing.assert_series_equal(
            actual.sort_index().astype(int),
            expected.sort_index().astype(int),
            check_names=False,
        )
    assert int(core["cell_employment_core"].sum()) == 1_852_975
    expected_base = matrix_base.loc[
        matrix_base["industry_code"].isin(OFFICE_CODES)
    ].groupby("district")["control_industry_employment"].sum()
    actual_base = base.groupby("district")["cell_employment_core_plus_base"].sum()
    pd.testing.assert_series_equal(
        actual_base.sort_index().astype(int),
        expected_base.sort_index().astype(int),
        check_names=False,
    )
    assert int(base["cell_employment_core_plus_base"].sum()) == 2_336_384


def test_composition_and_weighting_sensitivities_preserve_controls():
    composition = gpd.read_parquet(
        OUTPUTS / "core-plus-sensitivity-grid-100m.parquet"
    )
    weighting = gpd.read_parquet(
        OUTPUTS / "core-plus-weighting-sensitivity-grid-100m.parquet"
    )
    assert composition["cell_id"].equals(weighting["cell_id"])
    assert composition.geometry.to_wkb().equals(weighting.geometry.to_wkb())
    totals = {
        scenario: int(
            composition[f"cell_employment_core_plus_{scenario}"].sum()
        )
        for scenario in SCENARIOS
    }
    assert totals == {
        "low_office_intensity": 2_323_401,
        "base": 2_336_384,
        "high_office_intensity": 2_349_367,
    }
    weighting_totals = {
        scenario: int(weighting[f"cell_employment_core_plus_{scenario}"].sum())
        for scenario in WEIGHTING_SCENARIOS
    }
    assert set(weighting_totals.values()) == {2_336_384}
    assert (
        weighting["cell_employment_core_plus_building_volume_dominant"]
        != weighting["cell_employment_core_plus_base"]
    ).any()
    assert (
        weighting["cell_employment_core_plus_workplace_evidence_emphasis"]
        != weighting["cell_employment_core_plus_base"]
    ).any()
    assert not composition["reach_intersection_calculated"].any()
    assert not weighting["reach_intersection_calculated"].any()


def test_control_allocation_diagnostics_reconcile_without_uniform_fallback():
    diagnostics = pd.read_csv(
        OUTPUTS / "allocation-diagnostics.csv",
        dtype={"accounting_stratum_id": str, "industry_code": str},
    )
    assert len(diagnostics) == 3_596
    assert diagnostics["accounting_stratum_id"].nunique() == 124
    assert set(diagnostics["industry_code"]) == set(OFFICE_CODES)
    assert (diagnostics["reconciliation_difference"] == 0).all()
    assert not diagnostics["uniform_fallback_used"].any()
    assert diagnostics["no_log_cap_winsorize_or_minmax"].all()
    assert not diagnostics["generic_ppml_fitted"].any()
    assert not diagnostics["uniform_allocation_used_as_main"].any()
    assert diagnostics["gini_cell_employment"].between(0, 1).all()
    assert diagnostics["top_1_percent_cell_employment_share"].between(0, 1).all()


def test_shift_and_concentration_comparisons_are_complete():
    shifts = pd.read_csv(OUTPUTS / "control-shift-comparison.csv")
    concentration = pd.read_csv(OUTPUTS / "concentration-comparison.csv")
    summary = json.loads(
        (OUTPUTS / "spatial-allocation-summary.json").read_text(encoding="utf-8")
    )
    assert len(shifts) == 113
    assert set(shifts["district"]) == PRIORITY_DISTRICTS
    assert np.isclose(shifts["core_shift_from_district_direct"].sum(), 0, atol=1e-6)
    assert np.isclose(
        shifts["core_plus_base_shift_from_district_direct"].sum(), 0, atol=1e-6
    )
    gross = shifts["core_plus_base_shift_from_district_direct"].abs().sum() / 2
    assert np.isclose(
        gross,
        summary["control_shift_from_district_direct"][
            "core_plus_base_gross_jobs_shifted_between_ordinary_controls"
        ],
    )
    assert gross > 400_000
    assert set(concentration["allocation_architecture"]) == {
        "district_direct_base",
        "fine_control_base",
        "fine_control_building_volume_dominant",
        "fine_control_workplace_evidence_emphasis",
    }
    assert set(concentration["employment"]) == {2_336_384}
    assert concentration["gini_cell_employment"].between(0, 1).all()


def test_building_evidence_and_source_manifest_are_frozen_and_attributed():
    evidence_path = INTERMEDIATE / "building-function-evidence-100m.parquet"
    evidence = pd.read_parquet(evidence_path)
    quality = json.loads(
        (INTERMEDIATE / "building-evidence-quality.json").read_text(encoding="utf-8")
    )
    manifest = pd.read_csv(SPATIAL / "manifests/source-manifest.csv")
    assert len(evidence) == 172_233
    assert evidence["cell_id"].is_unique
    assert set(evidence["district"]) == PRIORITY_DISTRICTS
    assert (evidence.filter(like="_footprint_m2") >= 0).all().all()
    assert quality["official_fine_control_count"] == 116
    assert quality["functional_zone_count"] == 3
    assert quality["restricted_zone_source_geometry_committed"] is False
    osm = manifest.set_index("source_id").loc["osm-building-function-2026-08-23"]
    assert "Open Database License" in osm["license_or_reuse"]
    assert osm["derived_sha256"] == _sha256(evidence_path)
    zone = manifest.set_index("source_id").loc[
        "pudong-zone-statistical-polygons-2020"
    ]
    assert "source geometry not redistributed" in zone["license_or_reuse"]
    assert manifest["used_for"].str.len().gt(0).all()


def test_cluster_validations_and_maps_are_reproduced_under_all_weights():
    clusters = pd.read_csv(OUTPUTS / "cluster-validation.csv")
    weighting = pd.read_csv(OUTPUTS / "cluster-weighting-sensitivity.csv")
    assert len(clusters) == 7
    assert clusters["cluster_id"].is_unique
    assert clusters["cluster_emerges_under_declared_rule"].all()
    assert int(clusters["strong_cluster_emerges_under_declared_rule"].sum()) == 6
    assert not clusters["reach_polygon_used"].any()
    assert "district_direct_local_to_district_density_ratio" in clusters
    assert len(weighting) == 21
    assert set(weighting["weighting_scenario"]) == set(WEIGHTING_SCENARIOS)
    assert weighting["cluster_emerges_under_declared_rule"].all()
    assert weighting.groupby("weighting_scenario")[
        "strong_cluster_emerges_under_declared_rule"
    ].sum().eq(6).all()
    for cluster_id in clusters["cluster_id"]:
        path = SPATIAL / "maps" / f"cluster-{cluster_id}.png"
        assert path.is_file() and path.stat().st_size > 50_000
        with Image.open(path) as image:
            assert image.format == "PNG"
            assert image.width >= 1_000
            assert image.height >= 1_000


def test_report_and_outputs_do_not_claim_or_calculate_reach_results():
    report = (OUTPUTS / "spatial-allocation-report.md").read_text(encoding="utf-8")
    assert "No reach polygon" in report
    assert "no reach result or percentage" in report
    assert "448,992" in report
    assert "116 official fine accounting rows" in report
