#!/usr/bin/env python3
"""Build only the missing eight-district office-employment spatial extension."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from office_employment_pipeline.all_city import write_all_city_spatial_outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--osm-pbf", type=Path, required=True)
    parser.add_argument("--jrc-raster", type=Path, required=True)
    parser.add_argument("--overture-partition", type=Path, required=True)
    parser.add_argument("--cache-directory", type=Path, required=True)
    args = parser.parse_args()
    paths = write_all_city_spatial_outputs(
        args.repository_root,
        osm_pbf_path=args.osm_pbf.resolve(),
        jrc_raster_path=args.jrc_raster.resolve(),
        overture_partition_path=args.overture_partition.resolve(),
        cache_directory=args.cache_directory.resolve(),
    )
    print(f"All-city Core grid: {paths['core']}")
    print(f"All-city Core+ Base grid: {paths['base']}")
    print(f"All-city extension report: {paths['report']}")


if __name__ == "__main__":
    main()
