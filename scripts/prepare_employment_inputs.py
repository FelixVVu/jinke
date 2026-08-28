#!/usr/bin/env python3
"""Acquire pinned employment inputs and rebuild the immutable manifests."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from employment_pipeline.manifests import sha256_file, write_manifests
from employment_pipeline.sources import acquire_all_open_sources


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-cache", type=Path, required=True)
    parser.add_argument(
        "--xuhui-bulletin",
        type=Path,
        required=True,
        help="Original Xuhui Fifth Economic Census bulletin PDF (not committed).",
    )
    args = parser.parse_args()
    repository_root = args.repository_root.resolve()
    source_cache = args.source_cache.resolve()
    xuhui_bulletin = args.xuhui_bulletin.resolve()
    if not xuhui_bulletin.is_file():
        raise FileNotFoundError(xuhui_bulletin)
    acquired = acquire_all_open_sources(
        source_cache,
        repository_root / "data/economy/shanghai-district-boundaries.geojson",
    )
    manifests = write_manifests(
        repository_root=repository_root,
        osm_pbf_path=acquired["osm_pbf"],
        xuhui_pdf_sha256=sha256_file(xuhui_bulletin),
    )
    for name, path in {**acquired, **manifests}.items():
        if isinstance(path, list):
            print(f"{name}: {', '.join(str(item) for item in path)}")
        else:
            print(f"{name}: {path}")


if __name__ == "__main__":
    main()
