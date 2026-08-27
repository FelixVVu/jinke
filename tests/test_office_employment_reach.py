import hashlib
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from office_employment_pipeline.reach import _reach_fraction_map


ROOT = Path(__file__).resolve().parents[1]
REACH_OUTPUTS = ROOT / "data/office_employment/reach"

SCENARIOS = {
    "core",
    "core_plus_base",
    "core_plus_low_office_intensity",
    "core_plus_high_office_intensity",
    "core_plus_building_volume_dominant",
    "core_plus_workplace_evidence_emphasis",
}

INDUSTRY_LABELS = {
    "I": "Information transmission, software and IT services",
    "J": "Financial services",
    "M": "Scientific research and technical services",
    "721": "Organization management services",
    "723": "Legal services",
    "724": "Consulting and investigation",
    "725": "Advertising",
}

REACH_SUMMARY_SHA256 = (
    "f505b28a82b6d91f862d03cdbe306b3f7ff87d31965e3d07c5948d146f523c5a"
)
INDUSTRY_NUMERIC_PROJECTION_SHA256 = (
    "68e7c9cf816e8e1b11f7025d47450839f0cd4837c894f7fdf9fd6a2872716623"
)

PROTECTED_SHA256 = {
    "web/public/data/reach-areas.geojson": "6f039b0661f63c1017a2c4a3bc8f5c4d8fdef207ca10afe987f160642fb5656b",
    "web/public/data/reach-employment.json": "7f4a7447e52f70c595e3be9d0b38e1fc3ec06e9c8c3e3350a095b997cc87b105",
    "web/public/data/employment-methodology.json": "bd1eacdcd51725c9443c20aa11841941ea9120f8c76571bbf009efd75cdc152c",
    "web/public/data/reach-economy.json": "4054f47f07afa1e53612b50d965b3094161f43d94e8420a96911d6ac3c5731ca",
    "web/public/data/gdp-methodology.json": "c2f251e7394a53b903f3b577e5fba316292b8e3aecfdf677cfcf881b40dba9eb",
    "data/employment/intermediate/employment-allocation-grid.parquet": "12de4bd6c3f8df26c7702f1a4ff0f6aed797068d3f571a6ccabdd6b5f6f8c1b7",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_protected_reach_gdp_site_and_all_employment_files_are_unchanged():
    observed = {relative: _sha256(ROOT / relative) for relative in PROTECTED_SHA256}
    assert observed == PROTECTED_SHA256


def test_reach_summary_has_six_scenarios_five_limits_and_exact_denominators():
    summary = pd.read_csv(REACH_OUTPUTS / "office-reach-summary.csv")
    assert len(summary) == 30
    assert set(summary["scenario"]) == SCENARIOS
    assert summary.groupby("scenario")["limit_minutes"].apply(list).apply(
        lambda values: values == [10, 20, 30, 40, 50]
    ).all()
    assert summary.loc[summary["scenario"].eq("core"), "exact_shanghai_denominator"].eq(
        2_477_585
    ).all()
    assert summary.loc[~summary["scenario"].eq("core"), "exact_shanghai_denominator"].eq(
        3_220_710
    ).all()
    assert summary["employment_universe"].eq(
        "2023 secondary- and tertiary-sector legal-entity workplace employment"
    ).all()
    assert summary["exact_partial_cell_area_intersection"].all()
    assert not summary["grid_smoothed"].any()

    for _, frame in summary.groupby("scenario", sort=False):
        values = frame["employment_inside_reach"].to_numpy(dtype=float)
        assert np.all(np.diff(values) >= -1e-7)
        assert np.allclose(
            frame["incremental_employment"].to_numpy(dtype=float),
            np.diff(np.r_[0.0, values]),
            atol=1e-7,
        )
        expected_percentage = values / frame["exact_shanghai_denominator"].to_numpy() * 100
        assert np.allclose(
            frame["percentage_of_exact_shanghai_denominator"],
            expected_percentage,
            atol=1e-10,
        )


def test_fifty_minute_headlines_are_pinned_to_committed_unsmoothed_grids():
    summary = pd.read_csv(REACH_OUTPUTS / "office-reach-summary.csv")
    fifty = summary.loc[summary["limit_minutes"].eq(50)].set_index("scenario")
    expected = {
        "core": (945_831.540970, 38.1755437),
        "core_plus_base": (1_212_066.713237, 37.6335253),
        "core_plus_low_office_intensity": (1_204_075.597031, 37.3854087),
        "core_plus_high_office_intensity": (1_220_058.674804, 37.8816682),
        "core_plus_building_volume_dominant": (1_201_284.750074, 37.2987556),
        "core_plus_workplace_evidence_emphasis": (1_226_561.562576, 38.0835767),
    }
    for scenario, (employment, percentage) in expected.items():
        assert np.isclose(
            fifty.loc[scenario, "employment_inside_reach"], employment, atol=1e-6
        )
        assert np.isclose(
            fifty.loc[scenario, "percentage_of_exact_shanghai_denominator"],
            percentage,
            atol=1e-7,
        )

    assert round(fifty.loc["core", "employment_inside_reach"], 6) == 945_831.540970
    assert round(
        fifty.loc["core", "percentage_of_exact_shanghai_denominator"], 7
    ) == 38.1755436
    assert round(
        fifty.loc["core_plus_base", "employment_inside_reach"], 6
    ) == 1_212_066.713237
    assert round(
        fifty.loc[
            "core_plus_base", "percentage_of_exact_shanghai_denominator"
        ],
        7,
    ) == 37.6335253


def test_industry_labels_match_census_codes_and_726_is_excluded():
    industry_path = REACH_OUTPUTS / "office-50min-industry-contributions.csv"
    industry = pd.read_csv(industry_path, dtype={"industry_code": str})
    observed = industry.set_index("industry_code")["industry_name"].to_dict()
    assert observed == INDUSTRY_LABELS
    assert "726" not in observed

    numeric_projection = industry.drop(columns=["industry_name"]).to_csv(
        index=False, lineterminator="\n"
    )
    assert hashlib.sha256(numeric_projection.encode()).hexdigest() == (
        INDUSTRY_NUMERIC_PROJECTION_SHA256
    )
    assert _sha256(REACH_OUTPUTS / "office-reach-summary.csv") == (
        REACH_SUMMARY_SHA256
    )

    report = (REACH_OUTPUTS / "office-reach-report.md").read_text(encoding="utf-8")
    for code, label in INDUSTRY_LABELS.items():
        assert f"| {code} — {label} |" in report
    assert "| 726 —" not in report
    assert "Human-resources services" not in report


def test_fifty_minute_contributions_reconcile_to_core_plus_base():
    summary = pd.read_csv(REACH_OUTPUTS / "office-reach-summary.csv")
    central = float(
        summary.loc[
            summary["scenario"].eq("core_plus_base")
            & summary["limit_minutes"].eq(50),
            "employment_inside_reach",
        ].iloc[0]
    )
    core = float(
        summary.loc[
            summary["scenario"].eq("core") & summary["limit_minutes"].eq(50),
            "employment_inside_reach",
        ].iloc[0]
    )
    district = pd.read_csv(REACH_OUTPUTS / "office-50min-district-contributions.csv")
    industry = pd.read_csv(REACH_OUTPUTS / "office-50min-industry-contributions.csv")
    fine = pd.read_csv(REACH_OUTPUTS / "office-50min-fine-control-contributions.csv")
    residual = pd.read_csv(REACH_OUTPUTS / "office-50min-residual-contributions.csv")

    assert len(district) == 16
    assert district["district"].is_unique
    assert int(district["district_core_employment"].sum()) == 2_477_585
    assert int(district["district_core_plus_base_employment"].sum()) == 3_220_710
    assert np.isclose(district["core_inside"].sum(), core, atol=1e-6)
    assert np.isclose(district["core_plus_base_inside"].sum(), central, atol=1e-6)
    assert (district["core_percentage_of_district_captured"].between(0, 100)).all()
    assert (district["core_plus_percentage_of_district_captured"].between(0, 100)).all()
    assert district.loc[
        district["district"].eq("闵行区"),
        "minhang_technical_sliver_employment_assigned",
    ].eq(0).all()

    assert len(industry) == 7
    assert set(industry["industry_code"].astype(str)) == {
        "I",
        "J",
        "M",
        "721",
        "723",
        "724",
        "725",
    }
    assert int(industry["exact_or_constrained_city_employment"].sum()) == 3_220_710
    assert np.isclose(industry["employment_inside_50min"].sum(), central, atol=1e-6)

    assert len(fine) == 116
    assert len(residual) == 8
    assert fine["accounting_stratum_id"].is_unique
    assert residual["accounting_stratum_id"].is_unique
    assert not set(fine["accounting_stratum_id"]) & set(residual["accounting_stratum_id"])
    assert np.isclose(
        fine["core_plus_base_inside_50min"].sum()
        + residual["core_plus_base_inside_50min"].sum(),
        central,
        atol=1e-6,
    )
    top = fine.sort_values("fine_control_rank").iloc[0]
    assert top["control_name"] == "张江高科技园区"
    assert top["accounting_stratum_id"] == 310115503000


def test_six_uncertainty_dimensions_remain_separate_and_bounded():
    uncertainty = pd.read_csv(
        REACH_OUTPUTS / "office-50min-uncertainty-decomposition.csv"
    )
    expected = {
        "Core+ district-composition sensitivity",
        "Within-control weighting sensitivity",
        "Residual-location sensitivity",
        "Pudong functional-zone boundary sensitivity",
        "Reach-edge ±100 m sensitivity",
        "Census rounding sensitivity",
    }
    assert set(uncertainty["uncertainty_dimension"]) == expected
    assert len(uncertainty) == 6
    assert uncertainty["not_a_confidence_interval"].all()
    assert (
        uncertainty["lower_employment"]
        <= uncertainty["central_employment"]
    ).all()
    assert (
        uncertainty["central_employment"]
        <= uncertainty["upper_employment"]
    ).all()
    assert uncertainty["central_employment"].nunique() == 1
    assert np.isclose(uncertainty["central_employment"].iloc[0], 1_212_066.713237)


def test_methodology_declares_exact_geometry_no_refit_and_cautious_classification():
    methodology = json.loads(
        (REACH_OUTPUTS / "office-reach-methodology.json").read_text(encoding="utf-8")
    )
    analysis = methodology["analysis"]
    assert methodology["source_commit"] == "7b88f7fc8d81a52daebcd19ddc68df90bee4c6c5"
    assert methodology["denominators"] == {
        "core": 2_477_585,
        "core_plus_each_scenario": 3_220_710,
    }
    assert analysis["crs"] == "EPSG:32651"
    assert analysis["grid_metres"] == 100
    assert analysis["grid_smoothed"] is False
    assert analysis["rendered_heatmap_used"] is False
    assert analysis["spatial_model_refit"] is False
    assert analysis["spatial_grids_regenerated"] is False
    assert analysis["partial_cell_method"] == "area(cell intersection reach) / clipped cell_area_m2"
    assert methodology["uncertainty_dimensions_are_separate"] is True
    assert methodology["uncertainty_is_statistical_confidence_interval"] is False
    assert methodology["classification"] == "USABLE WITH CAUTION"
    assert methodology["site_modified"] is False
    assert methodology["gdp_modified"] is False
    assert methodology["existing_all_employment_outputs_modified"] is False


def test_partial_cell_fraction_uses_intersection_over_clipped_cell_area():
    cells = gpd.GeoDataFrame(
        {
            "cell_id": ["full", "partial", "outside"],
            "cell_area_m2": [10_000.0, 5_000.0, 10_000.0],
        },
        geometry=[
            box(0, 0, 100, 100),
            box(100, 0, 150, 100),
            box(200, 0, 300, 100),
        ],
        crs="EPSG:32651",
    )
    reaches = gpd.GeoDataFrame(
        {"limit": [50]},
        geometry=[box(0, 0, 125, 100)],
        crs="EPSG:32651",
    )
    fractions = _reach_fraction_map(cells, reaches)[50]
    assert fractions.tolist() == [1.0, 0.5, 0.0]


def test_output_checksum_manifest_is_complete_and_current():
    checksum_path = REACH_OUTPUTS / "checksums.sha256"
    entries = {}
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        entries[relative] = digest
    expected_files = {
        path.relative_to(ROOT).as_posix()
        for path in REACH_OUTPUTS.iterdir()
        if path.is_file() and path.name not in {"README.md", "checksums.sha256"}
    }
    assert set(entries) == expected_files
    assert {relative: _sha256(ROOT / relative) for relative in entries} == entries
