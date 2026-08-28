import json
from pathlib import Path

import numpy as np
import pandas as pd

from office_employment_pipeline.source_audit import (
    CITY_EMPLOYMENT,
    DISTRICTS,
    SOURCE_BYTES,
    SOURCE_SHA256,
    SUBINDUSTRY_SOURCE_BYTES,
    SUBINDUSTRY_SOURCE_SHA256,
)


ROOT = Path(__file__).resolve().parents[1]
OFFICE_DATA = ROOT / "data/office_employment"


def test_office_industry_scope_is_nested_mutually_exclusive_and_documented():
    scope = pd.read_csv(OFFICE_DATA / "manifests/industry-scope-2023.csv")
    assert len(scope) == 9
    assert scope["industry_code"].is_unique
    assert set(scope.loc[scope["core_office"], "industry_code"]) == {"I", "J", "M"}
    assert set(scope.loc[scope["core_plus_full_row"], "industry_code"]) == {
        "I",
        "J",
        "M",
    }
    assert set(scope.loc[scope["broad_office"], "industry_code"]) == {
        "I",
        "J",
        "72",
        "M",
        "K",
        "P",
        "Q",
        "R",
        "S",
    }
    assert not (scope["core_office"] & ~scope["broad_office"]).any()
    assert not (scope["core_office"] & ~scope["core_plus_full_row"]).any()
    assert scope["rationale"].notna().all()
    assert scope["mixed_activity_warning"].notna().all()
    assert int(scope.loc[scope["core_office"], "official_city_industry_employment"].sum()) == 2_477_585
    assert int(scope.loc[scope["broad_office"], "official_city_industry_employment"].sum()) == 6_374_547


def test_business_services_core_plus_selection_is_official_and_conservative():
    detail = pd.read_csv(
        OFFICE_DATA / "intermediate/business-services-subindustry-employment-2023.csv",
        dtype={"industry_code": str},
    )
    assert len(detail) == 9
    assert detail["industry_code"].is_unique
    assert set(detail["industry_code"]) == {
        "721",
        "722",
        "723",
        "724",
        "725",
        "726",
        "727",
        "728",
        "729",
    }
    assert set(detail.loc[detail["core_plus_selected"], "industry_code"]) == {
        "721",
        "723",
        "724",
        "725",
    }
    assert int(detail["official_city_employment"].sum()) == 1_904_322
    assert int(
        detail.loc[
            detail["core_plus_selected"], "official_city_employment"
        ].sum()
    ) == 743_125
    assert not detail.loc[
        detail["industry_code"].isin(["726", "727", "728", "729"]),
        "core_plus_selected",
    ].any()


def test_official_district_industry_controls_are_complete_and_reconcile():
    detail = pd.read_csv(
        OFFICE_DATA / "intermediate/district-industry-employment-2023.csv"
    )
    assert len(detail) == 16 * 9
    assert set(detail["district"]) == set(DISTRICTS)
    assert not detail.duplicated(["district", "industry_code"]).any()
    assert (detail["district_industry_employment"] >= 0).all()
    assert not detail["district_industry_employment"].isna().any()
    by_industry = detail.groupby("industry_code").agg(
        district_sum=("district_industry_employment", "sum"),
        official_city_total=("official_city_industry_employment", "first"),
        city_total_nunique=("official_city_industry_employment", "nunique"),
    )
    assert by_industry["city_total_nunique"].eq(1).all()
    assert by_industry["district_sum"].equals(by_industry["official_city_total"])


def test_district_core_and_broad_controls_reconcile_to_official_city_totals():
    controls = pd.read_csv(
        OFFICE_DATA / "outputs/district-office-employment-controls-2023.csv"
    )
    assert len(controls) == 16
    assert set(controls["district"]) == set(DISTRICTS)
    assert int(controls["official_all_industry_employment"].sum()) == CITY_EMPLOYMENT
    assert int(controls["core_office_employment"].sum()) == 2_477_585
    assert int(controls["broad_office_employment"].sum()) == 6_374_547
    assert (controls["core_office_employment"] <= controls["broad_office_employment"]).all()
    assert (controls["broad_office_employment"] <= controls["official_all_industry_employment"]).all()
    assert np.allclose(
        controls["core_share_of_district_employment_percentage"],
        controls["core_office_employment"]
        / controls["official_all_industry_employment"]
        * 100.0,
    )
    assert np.allclose(
        controls["broad_share_of_district_employment_percentage"],
        controls["broad_office_employment"]
        / controls["official_all_industry_employment"]
        * 100.0,
    )


def test_source_is_pinned_and_decision_is_scoped_to_district_calibration():
    manifest = pd.read_csv(OFFICE_DATA / "manifests/source-manifest.csv")
    source = manifest.loc[manifest["source_id"] == "shanghai-epc5-a1-09"].iloc[0]
    assert source["sha256"] == SOURCE_SHA256
    assert int(source["file_bytes"]) == SOURCE_BYTES
    assert "raw workbook not redistributed" in source["license_or_terms"]
    subindustry_source = manifest.loc[
        manifest["source_id"] == "shanghai-epc5-a1-03"
    ].iloc[0]
    assert subindustry_source["sha256"] == SUBINDUSTRY_SOURCE_SHA256
    assert int(subindustry_source["file_bytes"]) == SUBINDUSTRY_SOURCE_BYTES
    assert not (OFFICE_DATA / "raw").exists()

    summary = json.loads(
        (
            OFFICE_DATA / "outputs/city-office-employment-summary-2023.json"
        ).read_text(encoding="utf-8")
    )
    assert summary["official_all_industry_employment"] == CITY_EMPLOYMENT
    assert summary["core_office_employment"] == 2_477_585
    assert summary["core_plus_office_employment"] == 3_220_710
    assert summary["core_plus_selected_72_employment"] == 743_125
    assert summary["core_plus_selected_72_subindustry_rows"] == [
        "721",
        "723",
        "724",
        "725",
    ]
    assert summary["core_plus_72_city_total_is_official"] is True
    assert summary["core_plus_district_controls_constructed"] is False
    assert summary["broad_office_employment"] == 6_374_547
    assert summary["sufficiency_decision"] == "PROCEED"
    assert "district calibration controls" in summary["sufficiency_scope"]
    assert "occupation-level" in summary["sufficiency_scope"]


def test_existing_employment_and_gdp_outputs_remain_unchanged():
    employment = json.loads(
        (ROOT / "web/public/data/reach-employment.json").read_text(encoding="utf-8")
    )
    result_50 = next(
        row for row in employment["results"] if int(row["limit_minutes"]) == 50
    )
    assert np.isclose(result_50["central_estimated_employment"], 3_691_257.9268553634)
    assert np.isclose(result_50["percentage_of_shanghai_employment"], 28.177982379536193)
    assert (ROOT / "web/public/data/reach-economy.json").exists()
    assert (ROOT / "web/public/data/reach-areas.geojson").exists()
