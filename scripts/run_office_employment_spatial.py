"""Build the office-employment spatial framework without reach intersections."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from office_employment_pipeline.spatial import write_spatial_outputs
from office_employment_pipeline.spatial_report import write_spatial_review_report
from office_employment_pipeline.validation_maps import (
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
    args = parser.parse_args()
    paths = write_spatial_outputs(
        args.repository_root.resolve(), osm_pbf_path=args.osm_pbf
    )
    cluster_path = paths["spatial_root"] / "outputs/cluster-validation.csv"
    clusters = render_cluster_validation_maps(
        paths["core_plus"], paths["maps"], cluster_path
    )
    update_summary_with_clusters(paths["summary"], clusters)
    write_spatial_review_report(paths["spatial_root"])


if __name__ == "__main__":
    main()
