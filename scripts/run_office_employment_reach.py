"""Calculate office-employment reach results from committed 100 m grids."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from office_employment_pipeline.reach import run_office_reach_analysis


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--restricted-zone-directory",
        type=Path,
        required=True,
        help="Temporary directory containing the three hash-pinned Pudong supports",
    )
    args = parser.parse_args()
    paths = run_office_reach_analysis(
        args.repository_root,
        args.restricted_zone_directory,
    )
    print(f"Office reach report: {paths['report']}")
    print(f"Office reach results: {paths['reach_summary']}")


if __name__ == "__main__":
    main()
