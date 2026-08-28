"""Reproducible acquisition for open inputs and non-redistributed zone supports."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

import geopandas as gpd
import pyarrow.compute as pc
import pyarrow.dataset as ds
import requests
import shapely

from .config import (
    JRC_ARCHIVE_NAME,
    JRC_ARCHIVE_SHA256,
    JRC_RASTER_NAME,
    JRC_RASTER_SHA256,
    JRC_URL,
    OSM_PBF_SHA256,
    OSM_SOURCE_URL,
    OVERTURE_CLIPPED_SHA256,
    OVERTURE_RELEASE,
    RESTRICTED_ZONE_API,
    RESTRICTED_ZONE_CODES,
)
from .boundaries import ZONE_EXPECTED_HASHES
from .manifests import sha256_file

OVERTURE_PART_URL = (
    "https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/"
    "release/2026-07-22.0/theme%3Dplaces/type%3Dplace/"
    "part-00015-f754b4ac-fcf9-5991-bcbd-90e439ba21a0-c000.zstd.parquet"
)
OVERTURE_PART_NAME = "overture-place-part-00015-2026-07-22.0.parquet"


def _download(url: str, destination: Path, *, minimum_bytes: int) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size >= minimum_bytes:
        return destination
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    with requests.get(url, stream=True, timeout=(30, 600)) as response:
        response.raise_for_status()
        with temporary.open("wb") as handle:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    handle.write(chunk)
    if temporary.stat().st_size < minimum_bytes:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Downloaded file is unexpectedly small: {destination}")
    temporary.replace(destination)
    return destination


def acquire_osm(cache_dir: Path) -> Path:
    path = _download(
        OSM_SOURCE_URL,
        cache_dir / "shanghai-2026-08-19.osm.pbf",
        minimum_bytes=20_000_000,
    )
    if sha256_file(path) != OSM_PBF_SHA256:
        raise RuntimeError("OSM snapshot differs from the frozen SHA-256.")
    return path


def acquire_jrc(cache_dir: Path) -> Path:
    archive = _download(
        JRC_URL,
        cache_dir / JRC_ARCHIVE_NAME,
        minimum_bytes=1_000_000,
    )
    if sha256_file(archive) != JRC_ARCHIVE_SHA256:
        raise RuntimeError("JRC archive differs from the frozen SHA-256.")
    raster = cache_dir / JRC_RASTER_NAME
    if not raster.is_file():
        with zipfile.ZipFile(archive) as zipped:
            with zipped.open(JRC_RASTER_NAME) as source, raster.open("wb") as target:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    target.write(chunk)
    if sha256_file(raster) != JRC_RASTER_SHA256:
        raise RuntimeError("Extracted JRC raster differs from the frozen SHA-256.")
    return raster


def acquire_overture_places(cache_dir: Path, district_boundary_path: Path) -> Path:
    """Download the one STAC-selected partition and clip to exact Shanghai."""

    source = _download(
        OVERTURE_PART_URL,
        cache_dir / OVERTURE_PART_NAME,
        minimum_bytes=600_000_000,
    )
    destination = cache_dir / f"overture-places-shanghai-{OVERTURE_RELEASE}.parquet"
    if destination.is_file() and sha256_file(destination) == OVERTURE_CLIPPED_SHA256:
        return destination
    districts = gpd.read_file(district_boundary_path).to_crs("EPSG:4326")
    west, south, east, north = (float(value) for value in districts.total_bounds)
    filter_expression = (
        (pc.field("bbox", "xmin") < east)
        & (pc.field("bbox", "xmax") > west)
        & (pc.field("bbox", "ymin") < north)
        & (pc.field("bbox", "ymax") > south)
    )
    table = ds.dataset(source, format="parquet").to_table(filter=filter_expression)
    frame = table.to_pandas()
    frame = gpd.GeoDataFrame(
        frame,
        geometry=shapely.from_wkb(frame.pop("geometry")),
        crs="EPSG:4326",
    )
    exact = districts.geometry.union_all()
    frame = frame.loc[frame.geometry.intersects(exact)].copy()
    if len(frame) != 20_738:
        raise RuntimeError(f"Expected 20,738 exact-Shanghai Places; found {len(frame)}.")
    frame.to_parquet(destination, index=False)
    if sha256_file(destination) != OVERTURE_CLIPPED_SHA256:
        raise RuntimeError(
            "Clipped Overture bytes differ. Check the pinned pyarrow/geopandas versions; "
            "the row set may still be identical but must not be silently repinned."
        )
    return destination


def acquire_restricted_zone_supports(cache_dir: Path) -> list[Path]:
    """Acquire audit-use geometries outside git and enforce exact hashes."""

    paths: list[Path] = []
    for code in RESTRICTED_ZONE_CODES:
        destination = cache_dir / f"{code}-ruiduobao-2020.geojson"
        if not destination.is_file():
            response = requests.get(
                RESTRICTED_ZONE_API,
                params={"code": code, "year": 2020},
                timeout=120,
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            if payload.get("status") != "success" or not payload.get("filepath"):
                raise RuntimeError(f"Ruiduobao did not export zone {code}: {payload}")
            file_url = "https://map.ruiduobao.com" + quote(
                str(payload["filepath"]), safe="/:"
            )
            raw = requests.get(file_url, timeout=120)
            raw.raise_for_status()
            destination.write_bytes(raw.content)
        observed = sha256_file(destination)
        if observed != ZONE_EXPECTED_HASHES[code]:
            raise RuntimeError(f"Restricted zone {code} hash differs: {observed}")
        paths.append(destination)
    return paths


def acquire_all_open_sources(cache_dir: Path, district_boundary_path: Path) -> dict[str, Any]:
    return {
        "osm_pbf": acquire_osm(cache_dir),
        "jrc_raster": acquire_jrc(cache_dir),
        "overture_places": acquire_overture_places(cache_dir, district_boundary_path),
        "restricted_zone_supports": acquire_restricted_zone_supports(cache_dir),
    }
