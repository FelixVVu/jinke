"""Build the office-employment spatial framework without reach intersections."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from office_employment_pipeline.spatial import write_spatial_outputs
from office_employment_pipeline.spatial_report import write_spatial_review_report
from office_employment_pipeline.validation_maps import (
    evaluate_weighting_cluster_sensitivity,
    render_cluster_validation_maps,
    update_summary_with_clusters,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--osm-pbf",
        type=Path,
        default=None,
        help="Hash-pinned 2026-08-23 Shanghai OSM PBF; required only to rebuild evidence.",
    )
    parser.add_argument(
        "--restricted-zone-directory",
        type=Path,
        required=True,
        help=(
            "Non-repository directory containing the three hash-pinned Pudong "
            "2020 statistical-zone GeoJSON files."
        ),
    )
    args = parser.parse_args()
    paths = write_spatial_outputs(
        args.repository_root.resolve(),
        osm_pbf_path=args.osm_pbf,
        restricted_zone_directory=args.restricted_zone_directory,
    )
    cluster_path = paths["spatial_root"] / "outputs/cluster-validation.csv"
    clusters = render_cluster_validation_maps(
        paths["core_plus"],
        paths["maps"],
        cluster_path,
        paths["legacy_clusters"],
    )
    evaluate_weighting_cluster_sensitivity(
        paths["weighting_sensitivity"],
        paths["spatial_root"] / "outputs/cluster-weighting-sensitivity.csv",
    )
    update_summary_with_clusters(paths["summary"], clusters)
    write_spatial_review_report(paths["spatial_root"])


if __name__ == "__main__":
    main()
