import json
from pathlib import Path

import numpy as np
import pandas as pd

from employment_pipeline.workplace_feasibility import TARGET_CONTROLS


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "data/employment/outputs"
MANIFESTS = ROOT / "data/employment/manifests"


def test_target_control_feasibility_is_complete_and_does_not_claim_direct_data():
    controls = pd.read_csv(
        OUTPUTS / "workplace-data-feasibility-controls.csv",
        dtype={"accounting_stratum_id": "string"},
    )
    assert len(controls) == 14
    assert controls["accounting_stratum_id"].is_unique
    assert set(controls["control_name"]) == set(TARGET_CONTROLS)
    assert controls["uncertainty_priority_rank_within_14"].tolist() == list(
        range(1, 15)
    )
    assert not controls["public_finer_census_breakdown_found"].astype(bool).any()
    assert not controls["direct_inside_outside_employment_data_found"].astype(bool).any()
    allowed = {
        "DIRECT EMPLOYMENT DATA AVAILABLE",
        "STRONG INDEPENDENT PROXY AVAILABLE",
        "ONLY EXISTING JRC/POI-TYPE PROXIES AVAILABLE",
        "NO PRACTICAL IMPROVEMENT AVAILABLE",
    }
    assert set(controls["status"]) <= allowed
    assert controls["status"].value_counts().to_dict() == {
        "STRONG INDEPENDENT PROXY AVAILABLE": 7,
        "ONLY EXISTING JRC/POI-TYPE PROXIES AVAILABLE": 5,
        "NO PRACTICAL IMPROVEMENT AVAILABLE": 2,
    }
    assert np.isclose(
        controls["model_difference_shanghai_percentage_points"].sum(),
        1.3196400525412422,
    )


def test_candidate_source_ledger_has_required_fields_and_preference_tiers():
    sources = pd.read_csv(
        MANIFESTS / "workplace-source-candidates.csv",
        dtype={"accounting_stratum_id": "string"},
    )
    required = [
        "source_provider",
        "year_or_vintage",
        "spatial_resolution",
        "measure_or_proxy",
        "access_method",
        "license_or_reuse_restriction",
        "reproducibly_acquirable",
        "can_distinguish_exact_reach_inside_outside",
        "expected_usefulness_for_control",
    ]
    assert not sources[required].isna().any().any()
    assert set(sources["control_name"]) == set(TARGET_CONTROLS)
    assert sources.groupby("control_name").size().ge(8).all()
    assert {1, 3, 4, 5, 6} <= set(sources["source_preference_tier"])
    assert sources.loc[
        sources["candidate_source_id"] == "district-epc5-publication",
        "availability_finding",
    ].str.contains("NO FINER PUBLIC BREAKDOWN").all()
    assert not sources.astype(str).apply(
        lambda column: column.str.contains("job posting|vacancy", case=False).any()
    ).any()


def test_portfolio_scenarios_are_sensitivity_math_not_new_results():
    scenarios = pd.read_csv(
        OUTPUTS / "workplace-data-feasibility-portfolios.csv"
    )
    assert len(scenarios) == 9
    assert set(scenarios["portfolio_size"]) == {5, 10, 20}
    assert set(scenarios["shrink_fraction_assumption"]) == {0.3, 0.7, 1.0}
    assert np.allclose(
        scenarios["baseline_aggregate_model_range_percentage_points"],
        0.9245913340283058,
    )
    for _, group in scenarios.groupby("portfolio_size"):
        ordered = group.sort_values("shrink_fraction_assumption")
        assert ordered["remaining_aggregate_model_range_percentage_points"].is_monotonic_decreasing
        assert ordered["aggregate_range_reduction_percentage_points"].is_monotonic_increasing
    oracle = scenarios.loc[
        scenarios["scenario"] == "oracle_perfect_inside_outside_share"
    ].set_index("portfolio_size")
    assert np.isclose(
        oracle.loc[5, "aggregate_range_reduction_percentage_points"],
        0.32534219514455,
    )
    assert np.isclose(
        oracle.loc[20, "remaining_aggregate_model_range_percentage_points"],
        0.1907513879552308,
    )


def test_existing_employment_result_is_unchanged_by_feasibility_audit():
    payload = json.loads(
        (ROOT / "web/public/data/reach-employment.json").read_text(encoding="utf-8")
    )
    result_50 = next(
        row for row in payload["results"] if int(row["limit_minutes"]) == 50
    )
    assert np.isclose(result_50["central_estimated_employment"], 3_691_257.9268553634)
    assert np.isclose(result_50["percentage_of_shanghai_employment"], 28.177982379536193)
