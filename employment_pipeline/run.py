"""End-to-end v1 runner; it never writes or regenerates production reach geometry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .boundaries import (
    ZONE_EXPECTED_AREAS_KM2,
    ZONE_EXPECTED_HASHES,
    controls_needing_official_map_review,
    load_all_controls,
    record_official_map_review,
    topology_diagnostics,
)
from .config import (
    ANALYSIS_CRS,
    CITY_EMPLOYMENT,
    EMPLOYMENT_UNIVERSE,
    GRID_SIZE_METRES,
    JRC_RASTER_NAME,
    NOMINAL_FINE_CONTROL_EMPLOYMENT,
    NOMINAL_RESIDUAL_EMPLOYMENT,
    OSM_PBF_SHA256,
    OSM_SNAPSHOT_DATE,
    OSM_SOURCE_URL,
    OVERTURE_RELEASE,
    PRIORITY_DISTRICT_EMPLOYMENT,
    REFERENCE_DATE,
)
from .export import export_outputs
from .manifests import sha256_file
from .grid import (
    add_jrc_nonresidential_volume,
    add_overture_workplace_predictors,
    build_control_grid,
    investigate_zone_attribution,
)
from .model import (
    allocate_control_employment,
    allocate_finance_residuals,
    fit_calibrated_workplace_model,
)
from .reach import (
    calculate_reach_employment,
    district_contributions_50min,
    load_production_reaches,
    minhang_sliver_diagnostic,
    rounding_sensitivity,
)
from .sensitivity import add_zone_boundary_sensitivity, calculate_zone_sensitivity
from .validation import validate_benchmark


def _read_inputs(repository_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    manifest = repository_root / "data/employment/manifests"
    districts = pd.read_csv(manifest / "district-employment-2023.csv")
    controls = pd.read_csv(
        manifest / "control-crosswalk-2023.csv",
        dtype={"official_control_code_2023": "string", "accounting_stratum_id": "string"},
    )
    residuals = pd.read_csv(manifest / "residual-strata.csv")
    for frame, column in (
        (districts, "priority_district"),
        (districts, "individual_business_included"),
        (controls, "individual_business_included"),
        (controls, "geometry_is_approximate"),
        (residuals, "central_is_spatially_allocated"),
    ):
        frame[column] = frame[column].map(
            lambda value: value is True or str(value).strip().lower() == "true"
        )
    return districts, controls, residuals


def _update_boundary_manifest(
    repository_root: Path,
    controls: pd.DataFrame,
    review: pd.DataFrame,
) -> None:
    path = repository_root / "data/employment/manifests/boundary-manifest.csv"
    boundary = pd.read_csv(path, dtype={"accounting_stratum_id": "string"})
    statuses = review.set_index("accounting_stratum_id")["review_status"]
    boundary["official_map_validation_status"] = (
        boundary["accounting_stratum_id"].map(statuses).fillna("not_required")
    )
    material = review.set_index("accounting_stratum_id")[
        "could_materially_change_reach_employment"
    ]
    boundary["could_materially_change_reach_employment"] = (
        boundary["accounting_stratum_id"].map(material).fillna("no")
    )
    boundary["official_map_review_date"] = boundary[
        "official_map_validation_status"
    ].map(lambda status: "2026-08-19" if status != "not_required" else "")
    if set(boundary["accounting_stratum_id"]) != set(controls["accounting_stratum_id"]):
        raise RuntimeError("Boundary manifest lost an accounting stratum.")
    boundary.to_csv(path, index=False)


def _methodology(
    *,
    reach_hash: str,
    model_diagnostics: dict[str, Any],
    topology_summary: dict[str, Any],
    boundary_review: pd.DataFrame,
    zone_attribution: pd.DataFrame,
    rounding: pd.DataFrame,
    minhang: dict[str, Any],
    zone_sensitivity: pd.DataFrame,
    gdp_share_50min: float,
    gdp_result_sha256: str,
) -> dict[str, Any]:
    rounding_50 = rounding.loc[rounding["limit_minutes"] == 50].iloc[0]
    return {
        "schema_version": 1,
        "title": "Jinke independent Shanghai workplace-employment benchmark v1",
        "employment_universe": EMPLOYMENT_UNIVERSE,
        "universe_disclosure": (
            "This is workplace employment of legal entities engaged in secondary- "
            "and tertiary-sector activity, not all jobs and not employed population."
        ),
        "reference_date": REFERENCE_DATE,
        "denominator": CITY_EMPLOYMENT,
        "individual_business_employment_included": False,
        "priority_district_employment": PRIORITY_DISTRICT_EMPLOYMENT,
        "fine_control_employment": NOMINAL_FINE_CONTROL_EMPLOYMENT,
        "residual_employment": NOMINAL_RESIDUAL_EMPLOYMENT,
        "analysis": {
            "crs": ANALYSIS_CRS,
            "grid_metres": GRID_SIZE_METRES,
            "grid_rule": "common 100 m lattice; squares clipped to each accounting support",
            "reach_path": "web/public/data/reach-areas.geojson",
            "reach_sha256": reach_hash,
            "reach_limits_minutes": [10, 20, 30, 40, 50],
            "partial_cell_rule": "area(cell intersection reach) / clipped cell_area_m2",
            "production_reach_modified": False,
        },
        "accounting": {
            "ordinary_controls": 113,
            "pudong_functional_zone_strata": 3,
            "functional_zone_counts_are_separate": True,
            "geometric_overlap_does_not_merge_or_duplicate_accounting_rows": True,
            "pudong_street_rounding_reconciliation": (
                "The 12 displayed rows sum to 69.8 万 versus the published 69.5 万 "
                "subtotal. The minimum-squared adjustment subtracts 250 people from "
                "each row, remains within every half-unit interval, and totals 695,000."
            ),
        },
        "ordinary_boundary": {
            "source": "OpenStreetMap",
            "source_url": OSM_SOURCE_URL,
            "snapshot_date": OSM_SNAPSHOT_DATE,
            "source_pbf_sha256": OSM_PBF_SHA256,
            "source_crs": "EPSG:4326",
            "relation_ids": "data/employment/manifests/control-crosswalk-2023.csv",
            "license": "OpenStreetMap contributors, ODbL 1.0",
            "geometry_is_approximate": True,
            "topology": topology_summary,
        },
        "official_map_validation": {
            "authoritative_source": "Shanghai Tianditu / Shanghai SHMAP_D and SHMAP_LAN map service",
            "review_date": "2026-08-19",
            "controls_reviewed": int(len(boundary_review)),
            "passed": int((boundary_review["review_status"] == "pass").sum()),
            "failed": int((boundary_review["review_status"] == "fail").sum()),
            "review_file": "data/employment/intermediate/official-map-visual-review.csv",
            "review_scope": "only controls intersecting or within 500 m of the 50-minute boundary",
            "pass_definition": (
                "no visible material contradiction at official display precision; not "
                "official adoption of the OSM line"
            ),
        },
        "pudong_functional_zones": {
            "selected_support": "approximately 2020 statistical polygons",
            "selected_support_areas_km2": ZONE_EXPECTED_AREAS_KM2,
            "source_hashes": ZONE_EXPECTED_HASHES,
            "source_geometry_redistributed": False,
            "public_grid_treatment": (
                "three aggregate ledger rows with null geometry; exact acquisition and "
                "processing instructions retained"
            ),
            "establishment_attribution_investigation": zone_attribution.to_dict(
                orient="records"
            ),
            "decision": (
                "release Places do not provide sufficiently complete, employment-weighted "
                "zone attribution; fallback support selected"
            ),
            "sensitivity_file": "data/employment/intermediate/pudong-zone-sensitivity.csv",
            "planning_scope_warning": (
                "same-name planning scopes are not assumed equal to census strata; the "
                "area-matched case is a morphology sensitivity, not an official vector"
            ),
            "conservative_bounds": "0% and 100% of each zone row inside each reach",
        },
        "predictors": {
            "jrc": "raw 2020 JRC non-residential built volume; upper tail preserved",
            "overture": f"Overture Places release {OVERTURE_RELEASE}; confidence summed by interpretable category",
            "temporal_alignment": (
                "JRC epoch 2020 and Overture/OSM snapshots after the 2023 census are "
                "spatial predictors/supports, not replacements for the 2023 counts"
            ),
            "viirs": (
                "not used in v1: it is auxiliary and the official annual numerical product "
                "requires an Earthdata credential; no visual-tile substitute was used"
            ),
        },
        "allocation_models": {
            "uniform": "uniform employment density within each accounting support",
            "building_volume": (
                "raw JRC non-residential built volume; no log target, cap, winsorization, "
                "district min-max normalization, or GDP weights"
            ),
            "calibrated_workplace": model_diagnostics,
            "normalization": (
                "each model is normalized independently within every census accounting "
                "control so its cell sum exactly equals the reconciled control count"
            ),
        },
        "residuals": {
            "total": NOMINAL_RESIDUAL_EMPLOYMENT,
            "lower": "all unresolved residual employment contributes zero",
            "central": (
                "only four bulletin-identified finance residuals use finance/business "
                "workplace points and building evidence; unsplit/unclassified residuals "
                "remain unresolved"
            ),
            "upper": "all unresolved residual employment contributes to the numerator",
            "separate_from_spatial_model_sensitivity": True,
        },
        "rounding": {
            "method": (
                "linear extrema inside every published half-unit interval, with Pudong "
                "category-subtotal constraints; rounding is not an employment stratum"
            ),
            "50min_minus_percentage_points": float(
                rounding_50["rounding_minus_percentage_points"]
            ),
            "50min_plus_percentage_points": float(
                rounding_50["rounding_plus_percentage_points"]
            ),
        },
        "boundary_sensitivity": {
            "reach_edge_method": (
                "recalculate with reach edges displaced inward/outward by 100 m"
            ),
            "functional_zone_method": (
                "compare selected 2020 statistical supports with official-reported-area "
                "morphology interpretations and a conservative 0%-to-100% reach envelope"
            ),
            "reported_area_interpretation_warning": (
                "reported-area morphology is not an official vector and is not assumed "
                "equal to a census accounting boundary"
            ),
            "combined_envelope_rule": (
                "take the most adverse single component; do not add the independent "
                "reach-edge and functional-zone support perturbations"
            ),
            "reported_separately_from_residual_and_model_ranges": True,
        },
        "minhang_sliver": minhang,
        "prohibited_inputs": {
            "openrouteservice_called": False,
            "job_posting_counts_used": False,
            "existing_gdp_model_reused_as_primary_employment_model": False,
        },
        "gdp_diagnostic": {
            "comparison_only": True,
            "source_path": "web/public/data/reach-economy.json",
            "source_sha256": gdp_result_sha256,
            "existing_50min_gdp_share_percentage": gdp_share_50min,
            "employment_share_source": "50-minute preferred employment result",
            "interpretation": (
                "GDP share divided by employment share is relative GDP per worker "
                "inside the reach versus Shanghai overall; no GDP result was rerun"
            ),
        },
        "benchmark_classification": "USABLE WITH CAUTION",
        "limitations": [
            "All street/town geometries are approximate rather than official 2023 accounting boundaries.",
            "The three Pudong zone supports fail official-scope equivalence and dominate boundary uncertainty.",
            "The calibrated surface is constrained by aggregate controls and cannot identify establishment headcounts.",
            "Several residual strata remain deliberately unlocated in the central estimate.",
        ],
    }


def run_benchmark(repository_root: Path, source_cache: Path) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    source_cache = source_cache.resolve()
    districts, controls, residuals = _read_inputs(repository_root)
    crosswalk_path = repository_root / "data/employment/manifests/control-crosswalk-2023.csv"
    all_controls = load_all_controls(
        repository_root
        / "data/employment/raw/boundaries/osm-priority-controls-2026-08-19.geojson",
        crosswalk_path,
        source_cache,
    )
    topology_by_district, topology_summary = topology_diagnostics(
        all_controls,
        repository_root / "data/economy/shanghai-district-boundaries.geojson",
    )
    reaches, reach_hash = load_production_reaches(
        repository_root / "web/public/data/reach-areas.geojson", ANALYSIS_CRS
    )
    reach_50 = reaches.loc[reaches["limit"] == 50, "geometry"].iloc[0]
    boundary_review = record_official_map_review(
        controls_needing_official_map_review(all_controls, reach_50)
    )
    _update_boundary_manifest(repository_root, controls, boundary_review)

    grid = build_control_grid(all_controls)
    grid = add_jrc_nonresidential_volume(grid, source_cache / JRC_RASTER_NAME)
    overture_path = source_cache / f"overture-places-shanghai-{OVERTURE_RELEASE}.parquet"
    grid, poi_diagnostics = add_overture_workplace_predictors(
        grid, all_controls, overture_path
    )
    zone_attribution = investigate_zone_attribution(overture_path)
    fit, control_model, model_diagnostics = fit_calibrated_workplace_model(grid)
    model_diagnostics["poi_diagnostics"] = poi_diagnostics
    fine_grid = allocate_control_employment(grid, fit)
    residual_grid = allocate_finance_residuals(fine_grid, residuals)
    reach_results = calculate_reach_employment(
        fine_grid, residual_grid, reaches, residuals
    )
    rounding = rounding_sensitivity(
        fine_grid,
        residual_grid,
        reaches,
        controls,
        residuals,
        districts,
    )
    district_50, pudong_50 = district_contributions_50min(
        fine_grid,
        residual_grid,
        reach_50,
        districts,
        residuals,
    )
    minhang = minhang_sliver_diagnostic(
        repository_root / "data/economy/shanghai-district-boundaries.geojson",
        reach_50,
    )
    zone_sensitivity = calculate_zone_sensitivity(
        all_controls=all_controls,
        central_fine_grid=fine_grid,
        fit=fit,
        jrc_raster_path=source_cache / JRC_RASTER_NAME,
        overture_places_path=overture_path,
        reaches=reaches,
    )
    reach_results = add_zone_boundary_sensitivity(reach_results, zone_sensitivity)
    gdp_result_path = repository_root / "web/public/data/reach-economy.json"
    gdp_rows = json.loads(gdp_result_path.read_text(encoding="utf-8"))
    gdp_50 = next(row for row in gdp_rows if int(row["limit_minutes"]) == 50)
    gdp_share_50min = float(gdp_50["percentage_of_shanghai_gdp"])
    gdp_result_sha256 = sha256_file(gdp_result_path)
    validation = validate_benchmark(
        district_totals=districts,
        controls=controls,
        residuals=residuals,
        control_geometries=all_controls,
        fine_grid=fine_grid,
        residual_grid=residual_grid,
        reaches=reach_results,
        reach_source_sha256=reach_hash,
        model_diagnostics=model_diagnostics,
        boundary_review=boundary_review,
    )
    methodology = _methodology(
        reach_hash=reach_hash,
        model_diagnostics=model_diagnostics,
        topology_summary=topology_summary,
        boundary_review=boundary_review,
        zone_attribution=zone_attribution,
        rounding=rounding,
        minhang=minhang,
        zone_sensitivity=zone_sensitivity,
        gdp_share_50min=gdp_share_50min,
        gdp_result_sha256=gdp_result_sha256,
    )
    fifty_methodology = reach_results.loc[
        reach_results["limit_minutes"] == 50
    ].iloc[0]
    methodology["gdp_diagnostic"]["employment_share_percentage"] = float(
        fifty_methodology["percentage_of_shanghai_employment"]
    )
    methodology["gdp_diagnostic"]["gdp_share_divided_by_employment_share"] = (
        gdp_share_50min
        / float(fifty_methodology["percentage_of_shanghai_employment"])
    )
    paths = export_outputs(
        repository_root=repository_root,
        fine_grid=fine_grid,
        residual_grid=residual_grid,
        reach_results=reach_results,
        district_contributions=district_50,
        pudong_contributions=pudong_50,
        rounding=rounding,
        control_model_diagnostics=control_model,
        model_diagnostics=model_diagnostics,
        topology_by_district=topology_by_district,
        topology_summary=topology_summary,
        boundary_review=boundary_review,
        zone_attribution=zone_attribution,
        zone_sensitivity=zone_sensitivity,
        minhang_sliver=minhang,
        validation=validation,
        methodology=methodology,
    )
    fifty = reach_results.loc[reach_results["limit_minutes"] == 50].iloc[0]
    return {
        "primary_50min_employment": float(fifty["central_estimated_employment"]),
        "primary_50min_percentage": float(
            fifty["percentage_of_shanghai_employment"]
        ),
        "validation": validation,
        "paths": {key: str(value) for key, value in paths.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-cache", type=Path, required=True)
    args = parser.parse_args()
    result = run_benchmark(args.repository_root, args.source_cache)
    print(
        f"50-minute central employment: {result['primary_50min_employment']:.0f} "
        f"({result['primary_50min_percentage']:.3f}%)"
    )
    print(f"Validation: {result['validation']['status']}")


if __name__ == "__main__":
    main()
