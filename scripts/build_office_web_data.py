#!/usr/bin/env python3
"""Build lightweight, display-only office-employment web artifacts.

Reach statistics are copied from the committed exact-intersection outputs.
The density layer is a visual aggregation of the committed unsmoothed 100 m
Core+ Base grid and must never be used to recompute reach statistics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer


SOURCE_COMMIT = "7b88f7fc8d81a52daebcd19ddc68df90bee4c6c5"
EXPECTED_HASHES = {
    "reach_summary": "f505b28a82b6d91f862d03cdbe306b3f7ff87d31965e3d07c5948d146f523c5a",
    "reach_methodology": "2c228e241e5685018d80605d31cfc8da882d403253c052cc9ebe932ebe44898b",
    "core_plus_grid": "433acd3ef11fc7570e0e06d5a0fa2da49fecedc1cf65a6b120b3087197ae6abb",
    "cluster_validation": "25d538a5eab6a40ad094c17b4d0bd496996d22088b9f6106fcd8163c403b8fb3",
}
DENOMINATORS = {"core": 2_477_585, "core_plus_base": 3_220_710}
EXPECTED_50 = {
    "core": (945_831.540970, 38.1755436),
    "core_plus_base": (1_212_066.713237, 37.6335253),
}
LIMITS = [10, 20, 30, 40, 50]
DISPLAY_AGGREGATION_METRES = 400
DISPLAY_MINIMUM_JOBS = 5.0
REQUIRED_DISCLOSURE = (
    "Office-employment density is modelled from official 2023 employment controls "
    "and workplace/building evidence. Heatmap smoothing is for visualization only; "
    "reach statistics use the unsmoothed 100 m analytical grid."
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def verify_input_hash(path: Path, key: str) -> str:
    actual = sha256(path)
    expected = EXPECTED_HASHES[key]
    if actual != expected:
        raise ValueError(f"Unexpected {key} hash: {actual}; expected {expected}")
    return actual


def build_reach_data(summary_path: Path) -> dict:
    summary = pd.read_csv(summary_path)
    selected = summary[summary["scenario"].isin(DENOMINATORS)].copy()
    if set(selected["scenario"]) != set(DENOMINATORS):
        raise ValueError("Core and Core+ Base reach scenarios are required")

    benchmarks: dict[str, dict] = {}
    for scenario, denominator in DENOMINATORS.items():
        rows = selected[selected["scenario"] == scenario].sort_values("limit_minutes")
        if rows["limit_minutes"].astype(int).tolist() != LIMITS:
            raise ValueError(f"{scenario} must contain exactly the five production limits")
        if not rows["employment_inside_reach"].is_monotonic_increasing:
            raise ValueError(f"{scenario} reach employment is not monotonic")
        if not (rows["exact_shanghai_denominator"] == denominator).all():
            raise ValueError(f"{scenario} denominator changed")
        if not rows["exact_partial_cell_area_intersection"].all() or rows["grid_smoothed"].any():
            raise ValueError(f"{scenario} is not the unsmoothed exact-intersection result")

        records = []
        for row in rows.itertuples(index=False):
            recomputed = row.employment_inside_reach / denominator * 100
            if not math.isclose(
                recomputed,
                row.percentage_of_exact_shanghai_denominator,
                rel_tol=0,
                abs_tol=1e-9,
            ):
                raise ValueError(f"{scenario} percentage does not reconcile at {row.limit_minutes}")
            records.append(
                {
                    "limit_minutes": int(row.limit_minutes),
                    "employment_inside_reach": float(row.employment_inside_reach),
                    "display_employment": int(round(row.employment_inside_reach)),
                    "percentage_of_shanghai": float(row.percentage_of_exact_shanghai_denominator),
                    "incremental_employment": float(row.incremental_employment),
                    "display_incremental_employment": int(round(row.incremental_employment)),
                }
            )

        observed_50 = records[-1]
        expected_employment, expected_share = EXPECTED_50[scenario]
        if not math.isclose(
            observed_50["employment_inside_reach"], expected_employment, rel_tol=0, abs_tol=5e-7
        ) or not math.isclose(
            observed_50["percentage_of_shanghai"], expected_share, rel_tol=0, abs_tol=5e-8
        ):
            raise ValueError(f"Approved {scenario} 50-minute result changed")

        benchmarks[scenario] = {
            "label": "Core office-oriented employment" if scenario == "core" else "Core+ Base office-oriented employment",
            "denominator": denominator,
            "records": records,
        }

    return {
        "schema_version": 1,
        "source_commit": SOURCE_COMMIT,
        "reference_date": "2023-12-31",
        "employment_universe": "2023 secondary- and tertiary-sector legal-entity workplace employment",
        "individual_business_employment_included": False,
        "primary_benchmark": "core_plus_base",
        "analytical_grid_metres": 100,
        "analytical_grid_smoothed": False,
        "partial_cell_method": "area(cell intersection reach) / clipped cell_area_m2",
        "display_density_used_for_statistics": False,
        "benchmarks": benchmarks,
    }


def build_density(grid_path: Path, clusters_path: Path) -> tuple[dict, dict]:
    columns = ["center_x", "center_y", "cell_employment_core_plus_base"]
    grid = pd.read_parquet(grid_path, columns=columns)
    if len(grid) != 172_233:
        raise ValueError(f"Unexpected analytical cell count: {len(grid)}")
    if (grid["cell_employment_core_plus_base"] < 0).any():
        raise ValueError("Negative Core+ employment in analytical grid")

    analytical_total = float(grid["cell_employment_core_plus_base"].sum())
    if not math.isclose(analytical_total, 2_336_384, rel_tol=0, abs_tol=1e-6):
        raise ValueError(f"Priority-district Core+ grid total changed: {analytical_total}")

    size = DISPLAY_AGGREGATION_METRES
    positive = grid[grid["cell_employment_core_plus_base"] > 0].copy()
    positive["bin_x"] = np.floor(positive["center_x"] / size).astype("int64")
    positive["bin_y"] = np.floor(positive["center_y"] / size).astype("int64")
    aggregated = (
        positive.groupby(["bin_x", "bin_y"], as_index=False)["cell_employment_core_plus_base"]
        .sum()
        .rename(columns={"cell_employment_core_plus_base": "jobs"})
    )
    aggregated["center_x"] = (aggregated["bin_x"] + 0.5) * size
    aggregated["center_y"] = (aggregated["bin_y"] + 0.5) * size
    displayed = aggregated[aggregated["jobs"] > DISPLAY_MINIMUM_JOBS].copy()
    displayed_total = float(displayed["jobs"].sum())
    retained_share = displayed_total / analytical_total
    if len(displayed) > 5_000 or retained_share < 0.999:
        raise ValueError(
            f"Display trade-off failed: {len(displayed)} features, {retained_share:.8%} retained"
        )

    q99 = float(displayed["jobs"].quantile(0.99))
    displayed["weight"] = np.minimum(
        1.0, np.log1p(displayed["jobs"]) / math.log1p(q99)
    )
    transformer = Transformer.from_crs("EPSG:32651", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(
        displayed["center_x"].to_numpy(), displayed["center_y"].to_numpy()
    )

    features = []
    for longitude, latitude, jobs, weight in zip(
        lon, lat, displayed["jobs"], displayed["weight"], strict=True
    ):
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(float(longitude), 6), round(float(latitude), 6)],
                },
                "properties": {"j": int(round(float(jobs))), "w": round(float(weight), 6)},
            }
        )

    clusters = pd.read_csv(clusters_path)
    cluster_checks = []
    positive_jobs = displayed["jobs"].to_numpy()
    for row in clusters.itertuples(index=False):
        distances = np.hypot(
            displayed["center_x"].to_numpy() - row.analysis_x,
            displayed["center_y"].to_numpy() - row.analysis_y,
        )
        local = displayed.loc[distances <= row.validation_radius_m, "jobs"]
        local_max = float(local.max()) if len(local) else 0.0
        percentile = float((positive_jobs <= local_max).mean() * 100) if local_max else 0.0
        passes = len(local) > 0 and percentile >= 90.0
        if not passes:
            raise ValueError(f"Display aggregation obscures declared cluster: {row.cluster_name}")
        cluster_checks.append(
            {
                "cluster_id": row.cluster_id,
                "cluster_name": row.cluster_name,
                "display_bin_max_jobs_within_1500m": int(round(local_max)),
                "display_bin_max_percentile": round(percentile, 3),
                "visible_in_display_validation": True,
            }
        )

    metadata = {
        "display_only": True,
        "analytical_use_prohibited": True,
        "source_commit": SOURCE_COMMIT,
        "source_grid_sha256": EXPECTED_HASHES["core_plus_grid"],
        "source_grid_crs": "EPSG:32651",
        "source_grid_metres": 100,
        "aggregation_metres": size,
        "smoothing": "MapLibre heatmap kernel at render time",
        "minimum_aggregated_jobs_exclusive": DISPLAY_MINIMUM_JOBS,
        "analytical_priority_district_jobs": analytical_total,
        "displayed_priority_district_jobs_before_rounding": displayed_total,
        "retained_share_of_priority_district_grid": retained_share,
        "feature_count": len(features),
        "statistics_source": "reach-office-employment.json from unsmoothed 100 m exact-area intersections",
        "disclosure": REQUIRED_DISCLOSURE,
    }
    geojson = {"type": "FeatureCollection", "metadata": metadata, "features": features}
    diagnostics = {
        **metadata,
        "q99_aggregated_jobs_for_weight_scaling": q99,
        "cluster_display_checks": cluster_checks,
    }
    return geojson, diagnostics


def build_methodology(reach_method_path: Path, density_diagnostics: dict) -> dict:
    source_method = json.loads(reach_method_path.read_text(encoding="utf-8"))
    if source_method.get("source_commit") != SOURCE_COMMIT:
        raise ValueError("Office reach methodology source commit changed")
    if source_method.get("classification") != "USABLE WITH CAUTION":
        raise ValueError("Office benchmark classification changed")

    return {
        "schema_version": 1,
        "source_commit": SOURCE_COMMIT,
        "reference_date": source_method["reference_date"],
        "employment_universe": source_method["employment_universe"],
        "classification": "USABLE WITH CAUTION",
        "individual_business_employment_included": False,
        "definitions": {
            "core": {
                "label": "Core",
                "industry_codes": ["I", "J", "M"],
                "description": "Conservative office-oriented benchmark covering information services, finance, and scientific research/technical services.",
                "denominator": DENOMINATORS["core"],
            },
            "core_plus_base": {
                "label": "Core+ Base",
                "industry_codes": ["I", "J", "M", "721", "723", "724", "725"],
                "description": "Core plus selected office-oriented business services: organization management, legal services, consulting and investigation, and advertising.",
                "denominator": DENOMINATORS["core_plus_base"],
                "selected_division_72_district_composition_modelled": True,
            },
        },
        "statistical_sources": [
            {
                "provider": "Shanghai Municipal Statistics Bureau",
                "title": "2023 Economic Census employment by industry division and district (Table 1-9)",
                "url": "https://tjj.sh.gov.cn/tjnj/jjpcnj2023/zk/html/A1-09.xls",
            },
            {
                "provider": "Shanghai Municipal Statistics Bureau",
                "title": "2023 Economic Census legal entities and employment by industry middle group (Table 1-3)",
                "url": "https://tjj.sh.gov.cn/tjnj/jjpcnj2023/zk/html/A1-03.xls",
            },
        ],
        "allocation": {
            "analytical_crs": "EPSG:32651",
            "analytical_grid_metres": 100,
            "hard_controls": "Official district-by-industry employment reconciled to audited fine street/town totals; Pudong functional zones remain separate accounting strata.",
            "base_weights": {
                "jrc_non_residential_built_volume": 0.60,
                "osm_building_function_footprint": 0.25,
                "osm_office_establishments": 0.10,
                "overture_poi_supplement": 0.05,
            },
            "generic_ppml_fitted": False,
            "uniform_allocation_used_as_main": False,
            "control_totals_preserved": True,
        },
        "reach_statistics": {
            "source_grid": "committed unsmoothed 100 m analytical grids",
            "partial_cell_method": source_method["analysis"]["partial_cell_method"],
            "rendered_heatmap_used": False,
        },
        "density_display": density_diagnostics,
        "priority_district_display_scope": [
            "Huangpu", "Xuhui", "Changning", "Jing'an", "Putuo", "Hongkou", "Yangpu", "Pudong"
        ],
        "priority_district_scope_note": "The display grid covers the eight audited reach-relevant districts; percentages use the exact all-Shanghai denominator.",
        "approximate_boundary_disclosure": "Fine controls use approximate OSM boundaries; Pudong functional-zone supports use approximate 2020 statistical polygons.",
        "required_disclosure": REQUIRED_DISCLOSURE,
        "source_hashes": EXPECTED_HASHES,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reach-summary", type=Path, required=True)
    parser.add_argument("--reach-methodology", type=Path, required=True)
    parser.add_argument("--core-plus-grid", type=Path, required=True)
    parser.add_argument("--cluster-validation", type=Path, required=True)
    parser.add_argument("--reach-output", type=Path, required=True)
    parser.add_argument("--methodology-output", type=Path, required=True)
    parser.add_argument("--density-output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for key, path in (
        ("reach_summary", args.reach_summary),
        ("reach_methodology", args.reach_methodology),
        ("core_plus_grid", args.core_plus_grid),
        ("cluster_validation", args.cluster_validation),
    ):
        verify_input_hash(path, key)

    reach_data = build_reach_data(args.reach_summary)
    density, density_diagnostics = build_density(args.core_plus_grid, args.cluster_validation)
    methodology = build_methodology(args.reach_methodology, density_diagnostics)
    write_json(args.reach_output, reach_data)
    write_json(args.methodology_output, methodology)
    write_json(args.density_output, density)

    print(
        json.dumps(
            {
                "reach_records": sum(len(item["records"]) for item in reach_data["benchmarks"].values()),
                "density_features": density_diagnostics["feature_count"],
                "density_retained_share": density_diagnostics["retained_share_of_priority_district_grid"],
                "output_sha256": {
                    "reach": sha256(args.reach_output),
                    "methodology": sha256(args.methodology_output),
                    "density": sha256(args.density_output),
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
