#!/usr/bin/env python3
"""Reproduce the 50-minute structural-certainty audit without refitting a model."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from employment_pipeline.structural import (  # noqa: E402
    AREA_FRACTION_TOLERANCE,
    run_structural_certainty,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--area-fraction-tolerance",
        type=float,
        default=AREA_FRACTION_TOLERANCE,
    )
    args = parser.parse_args()
    result = run_structural_certainty(
        args.repository_root,
        tolerance=args.area_fraction_tolerance,
    )
    answers = result["summary"]["answers"]
    bound = result["summary"]["allocation_free_fine_control_bound"]
    print(
        "Fine-control structural bound: "
        f"{bound['lower_employment']:.0f}–{bound['upper_employment']:.0f} "
        f"({bound['lower_shanghai_percentage']:.3f}%–"
        f"{bound['upper_shanghai_percentage']:.3f}%)"
    )
    print(
        "A/B current-numerator shares: "
        f"{answers['A_official_census_determined_percentage_of_current_numerator']:.3f}% / "
        f"{answers['B_partial_spatial_allocation_percentage_of_current_numerator']:.3f}%"
    )


if __name__ == "__main__":
    main()
