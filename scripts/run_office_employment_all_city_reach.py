#!/usr/bin/env python3
"""Calculate exact reach results from the committed all-city office grids."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from office_employment_pipeline.all_city_reach import run_all_city_office_reach_analysis


if __name__ == "__main__":
    paths = run_all_city_office_reach_analysis(Path(__file__).resolve().parents[1])
    print(f"All-city office reach report: {paths['report']}")
    print(f"All-city office reach summary: {paths['reach_summary']}")
