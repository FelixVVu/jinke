"""Deterministically build jinke_gdp_estimation.ipynb."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

OUTPUT = Path("jinke_gdp_estimation.ipynb")


def source(text: str) -> list[str]:
    normalized = textwrap.dedent(text).strip("\n") + "\n"
    return normalized.splitlines(keepends=True)


def markdown(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": source(text)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source(text),
    }


cells = [
    markdown(
        """
        # Jinke Shanghai GDP estimation

        Run the 11 numbered stages in order from a **fresh Google Colab runtime**.
        This is a separate audit workflow: it reads but never rewrites
        `web/public/data/reach-areas.geojson`, and it does not change stations,
        location search, or the live frontend. Source downloads and intermediates are
        cached below `MyDrive/JinkeGDP/`; rerunning a completed download stage reuses
        the validated cache.

        GDP values are expressed in `100 million current CNY` (亿元). The
        building-heavy and activity-heavy outputs are sensitivity scenarios, not
        confidence intervals.
        """
    ),
    markdown(
        """
        ## Stage 1 — Setup

        **Run this cell first.** It mounts Drive, clones or fast-forwards the Jinke
        repository, installs the pinned geospatial environment, and creates all
        `MyDrive/JinkeGDP/` cache/output directories.
        """
    ),
    code(
        """
        # STAGE 1 — SETUP
        from google.colab import drive
        drive.mount("/content/drive")

        import os
        import subprocess
        import sys
        from pathlib import Path

        REPOSITORY_URL = "https://github.com/FelixVVu/jinke.git"
        REPO_DIR = Path("/content/jinke")
        if (REPO_DIR / ".git").is_dir():
            subprocess.run(["git", "-C", str(REPO_DIR), "fetch", "origin", "--prune"], check=True)
            subprocess.run(["git", "-C", str(REPO_DIR), "checkout", "main"], check=True)
            subprocess.run(["git", "-C", str(REPO_DIR), "pull", "--ff-only", "origin", "main"], check=True)
        else:
            subprocess.run(["git", "clone", REPOSITORY_URL, str(REPO_DIR)], check=True)

        os.chdir(REPO_DIR)
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", "requirements-gdp.txt"],
            check=True,
        )
        if str(REPO_DIR) not in sys.path:
            sys.path.insert(0, str(REPO_DIR))

        DRIVE_ROOT = Path("/content/drive/MyDrive/JinkeGDP")
        SOURCE_ROOT = DRIVE_ROOT / "source"
        JRC_CACHE = SOURCE_ROOT / "jrc"
        VIIRS_CACHE = SOURCE_ROOT / "viirs"
        OVERTURE_CACHE = SOURCE_ROOT / "overture"
        INTERMEDIATE_ROOT = DRIVE_ROOT / "intermediate"
        AUDIT_ROOT = DRIVE_ROOT / "audit_outputs"
        for directory in (
            JRC_CACHE, VIIRS_CACHE, OVERTURE_CACHE, INTERMEDIATE_ROOT, AUDIT_ROOT
        ):
            directory.mkdir(parents=True, exist_ok=True)

        REPO_COMMIT = subprocess.check_output(
            ["git", "-C", str(REPO_DIR), "rev-parse", "HEAD"], text=True
        ).strip()
        print(f"Setup complete at repository commit {REPO_COMMIT}.")
        """
    ),
    markdown(
        """
        ## Stage 2 — Check Earthdata Secret

        In Colab, open **Secrets**, add `EARTHDATA_TOKEN`, and grant this notebook
        access. **Run this cell after Stage 1.** The secret is kept only in memory;
        its value is never displayed or written to Drive.
        """
    ),
    code(
        """
        # STAGE 2 — CHECK EARTHDATA SECRET
        from google.colab import userdata

        EARTHDATA_TOKEN = userdata.get("EARTHDATA_TOKEN")
        if not isinstance(EARTHDATA_TOKEN, str) or not EARTHDATA_TOKEN.strip():
            raise RuntimeError("Add EARTHDATA_TOKEN to Colab Secrets and grant notebook access.")
        print("EARTHDATA_TOKEN is available; its value has not been displayed or stored.")
        """
    ),
    markdown(
        """
        ## Stage 3 — Download/cache JRC

        **Run after Stages 1–2.** This reads the pinned district boundary only to
        discover the official GHSL Mollweide tile index, then downloads the Shanghai-
        intersecting 2020 non-residential 100 m tiles. Existing ZIPs and GeoTIFFs are
        reused.
        """
    ),
    code(
        """
        # STAGE 3 — DOWNLOAD/CACHE JRC
        import geopandas as gpd

        from gdp_pipeline.config import DISTRICT_BOUNDARY_RELATIVE_PATH
        from gdp_pipeline.sources import download_jrc_tiles

        discovery_districts = gpd.read_file(REPO_DIR / DISTRICT_BOUNDARY_RELATIVE_PATH)
        discovery_districts = discovery_districts.to_crs("EPSG:4326")
        jrc_rasters, jrc_metadata = download_jrc_tiles(discovery_districts, JRC_CACHE)
        print("JRC cache ready:", [path.name for path in jrc_rasters])
        """
    ),
    markdown(
        """
        ## Stage 4 — Download/cache NASA VNP46A4

        **Run after Stage 3.** CMR discovers only Version 2 annual 2025 HDF5 science
        granules intersecting Shanghai. Downloads use the in-memory Earthdata bearer
        token, then discard the variable. No visual imagery is used.
        """
    ),
    code(
        """
        # STAGE 4 — DOWNLOAD/CACHE NASA VNP46A4
        from gdp_pipeline.sources import download_viirs_granules

        shanghai_bounds = tuple(discovery_districts.total_bounds)
        viirs_granules, viirs_metadata = download_viirs_granules(
            shanghai_bounds, VIIRS_CACHE, EARTHDATA_TOKEN
        )
        del EARTHDATA_TOKEN
        print("VIIRS numerical granule cache ready:", [path.name for path in viirs_granules])
        """
    ),
    markdown(
        """
        ## Stage 5 — Download/cache Overture Places

        **Run after Stage 4.** The official Overture Python client resolves the latest
        STAC release and transfers only `type=place` rows in the Shanghai bounding
        box, then retains only geometries intersecting the exact 16-district union.
        A valid release-specific GeoParquet cache is reused.
        """
    ),
    code(
        """
        # STAGE 5 — DOWNLOAD/CACHE OVERTURE PLACES
        from gdp_pipeline.sources import download_overture_places

        overture_places_path, overture_metadata = download_overture_places(
            discovery_districts, OVERTURE_CACHE
        )
        print(
            f"Overture {overture_metadata['release']} cache ready: "
            f"{overture_places_path.name} "
            f"({overture_metadata['rows_intersecting_shanghai']:,} Shanghai places)"
        )
        """
    ),
    markdown(
        """
        ## Stage 6 — Load district boundaries and GDP

        **Run after Stage 5.** This validates exactly 16 unique valid districts, a
        single common 2025 year, complete name matching, and the separate official
        Shanghai city total. It does not revise any source GDP value.
        """
    ),
    code(
        """
        # STAGE 6 — LOAD DISTRICT BOUNDARIES AND GDP
        from gdp_pipeline.config import (
            CITY_GDP_RELATIVE_PATH,
            DISTRICT_BOUNDARY_RELATIVE_PATH,
            DISTRICT_GDP_RELATIVE_PATH,
        )
        from gdp_pipeline.inputs import load_district_inputs

        districts_wgs84, districts_metric, district_gdp, city_gdp = load_district_inputs(
            REPO_DIR / DISTRICT_BOUNDARY_RELATIVE_PATH,
            REPO_DIR / DISTRICT_GDP_RELATIVE_PATH,
            REPO_DIR / CITY_GDP_RELATIVE_PATH,
        )
        print(
            f"Validated {len(districts_metric)} districts for {int(district_gdp.year.iloc[0])}; "
            f"raw district sum={district_gdp.gdp_100m_cny.sum():,.2f} 亿元, "
            f"official Shanghai={float(city_gdp.gdp_100m_cny):,.2f} 亿元."
        )
        """
    ),
    markdown(
        """
        ## Stage 7 — Build 100 m proxy grid

        **Run after Stage 6.** This is the longest processing stage. It builds the
        EPSG:32651 lattice clipped to district geometry; conservatively reprojects JRC
        volume; applies VNP46A4 quality `== 0`; assigns native 15-arc-second radiance
        to cell centres without claiming 100 m detail; classifies Overture economic
        places; and normalizes all proxies within district.
        """
    ),
    code(
        """
        # STAGE 7 — BUILD 100 M PROXY GRID
        from gdp_pipeline.grid import (
            add_composite_weights,
            add_jrc_building_volume,
            add_overture_poi_intensity,
            add_viirs_radiance,
            build_100m_grid,
        )

        grid = build_100m_grid(districts_metric)
        grid = add_jrc_building_volume(grid, jrc_rasters)
        grid = add_viirs_radiance(grid, viirs_granules)
        economic_places_path = OVERTURE_CACHE / (
            f"economic-places-{overture_metadata['release']}.parquet"
        )
        grid, economic_places = add_overture_poi_intensity(
            grid,
            districts_metric,
            overture_places_path,
            economic_places_path=economic_places_path,
        )
        grid = add_composite_weights(grid)
        proxy_grid_path = INTERMEDIATE_ROOT / "shanghai-proxy-grid.parquet"
        grid.to_parquet(proxy_grid_path, index=False)
        print(
            f"Proxy grid ready: {len(grid):,} clipped cells; "
            f"{len(economic_places):,} economically relevant POIs. "
            f"Saved {proxy_grid_path}."
        )
        """
    ),
    markdown(
        """
        ## Stage 8 — Calibrate district GDP

        **Run after Stage 7.** The cell discloses one proportional city reconciliation
        factor and allocates each reconciled district target under the central and two
        sensitivity scenarios. Raw district source values remain unchanged.
        """
    ),
    code(
        """
        # STAGE 8 — CALIBRATE DISTRICT GDP
        from gdp_pipeline.calibration import allocate_district_gdp, build_district_calibration

        district_calibration, reconciliation_factor = build_district_calibration(
            district_gdp, city_gdp
        )
        grid = allocate_district_gdp(grid, district_calibration)
        calibrated_grid_path = INTERMEDIATE_ROOT / "shanghai-calibrated-grid.parquet"
        grid.to_parquet(calibrated_grid_path, index=False)
        print(
            f"Reconciliation factor={reconciliation_factor:.12f}; "
            f"disclosed city-minus-district gap="
            f"{float(city_gdp.gdp_100m_cny) - district_gdp.gdp_100m_cny.sum():,.2f} 亿元."
        )
        """
    ),
    markdown(
        """
        ## Stage 9 — Intersect with Jinke reach polygons

        **Run after Stage 8.** This hashes and reads the existing production
        `reach-areas.geojson`, projects an in-memory copy to the metric CRS, and uses
        clipped-cell intersection fractions. The source file is not modified.
        """
    ),
    code(
        """
        # STAGE 9 — INTERSECT WITH JINKE REACH POLYGONS
        from gdp_pipeline.config import REACH_RELATIVE_PATH
        from gdp_pipeline.reach import calculate_reach_gdp, load_production_reach_areas

        reach_path = REPO_DIR / REACH_RELATIVE_PATH
        reaches_metric, reach_sha256 = load_production_reach_areas(reach_path, grid.crs)
        reach_analysis = calculate_reach_gdp(
            grid, reaches_metric, float(city_gdp.gdp_100m_cny)
        )
        reach_intermediate_path = INTERMEDIATE_ROOT / "reach-gdp-analysis.csv"
        reach_analysis.to_csv(reach_intermediate_path, index=False)
        display(reach_analysis)
        """
    ),
    markdown(
        """
        ## Stage 10 — Validation

        **Run after Stage 9.** Every required invariant is fail-closed: 16 districts,
        five limits, nonnegative GDP, district and city calibration tolerances,
        monotonic reach totals, nonempty source coverage, valid projected geometry,
        and no prohibited source endpoint.
        """
    ),
    code(
        """
        # STAGE 10 — VALIDATION
        import json

        from gdp_pipeline.methodology import build_methodology
        from gdp_pipeline.sources import sha256_file
        from gdp_pipeline.validation import validate_outputs

        source_metadata = {
            "jrc": jrc_metadata,
            "viirs": viirs_metadata,
            "overture": overture_metadata,
            "repository": {"url": REPOSITORY_URL, "commit": REPO_COMMIT},
        }
        methodology = build_methodology(
            source_metadata=source_metadata,
            district_gdp=district_gdp,
            city_gdp=city_gdp,
            reconciliation_factor=reconciliation_factor,
            reach_path=REACH_RELATIVE_PATH,
            reach_sha256=reach_sha256,
            boundary_sha256=sha256_file(REPO_DIR / DISTRICT_BOUNDARY_RELATIVE_PATH),
        )
        validation_report = validate_outputs(
            districts_metric=districts_metric,
            district_gdp=district_gdp,
            grid=grid,
            calibration=district_calibration,
            reach=reach_analysis,
            official_city_gdp_100m_cny=float(city_gdp.gdp_100m_cny),
            source_metadata=source_metadata,
        )
        print(json.dumps(validation_report, ensure_ascii=False, indent=2))
        """
    ),
    markdown(
        """
        ## Stage 11 — Export `gdp-web-data.zip`

        **Run only after Stage 10 passes.** Detailed audit outputs go to
        `MyDrive/JinkeGDP/audit_outputs/`. The ZIP is checked to contain exactly
        `reach-economy.json` and `gdp-methodology.json`; the 100 m grid is never put
        in the website ZIP. This stage does not copy files into the live UI or deploy.
        """
    ),
    code(
        """
        # STAGE 11 — EXPORT GDP-WEB-DATA.ZIP
        from gdp_pipeline.export import export_audit_outputs

        exported = export_audit_outputs(
            audit_dir=AUDIT_ROOT,
            grid=grid,
            calibration=district_calibration,
            reach=reach_analysis,
            methodology=methodology,
            validation_report=validation_report,
        )
        for name, path in exported.items():
            print(f"{name}: {path}")
        print("Export complete. No website files were changed and nothing was deployed.")
        """
    ),
]

notebook = {
    "cells": cells,
    "metadata": {
        "colab": {"name": OUTPUT.name, "provenance": []},
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}


def main() -> None:
    OUTPUT.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
