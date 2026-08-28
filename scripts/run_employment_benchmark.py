#!/usr/bin/env python3
"""Run the independent employment benchmark from a repository checkout."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from employment_pipeline.run import main


if __name__ == "__main__":
    main()
