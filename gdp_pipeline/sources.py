"""Network/cache helpers for the three official proxy datasets."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Iterable

import geopandas as gpd
import requests

from .config import (
    JRC_CRS,
    JRC_DATASET,
    JRC_DOI,
    JRC_EPOCH,
    JRC_LICENSE,
    JRC_PRODUCT_URL,
    JRC_RESOLUTION_METRES,
    JRC_TILE_BASE_URL,
    JRC_TILE_SCHEMA_URL,
    OVERTURE_CATALOG_URL,
    OVERTURE_CLIENT_VERSION,
    OVERTURE_DOCS_URL,
    OVERTURE_LICENSE_URL,
    VIIRS_CMR_URL,
    VIIRS_DOI,
    VIIRS_LICENSE,
    VIIRS_NATIVE_RESOLUTION,
    VIIRS_PRODUCT_URL,
    VIIRS_QUALITY_VARIABLE,
    VIIRS_RADIANCE_VARIABLE,
    VIIRS_SHORT_NAME,
    VIIRS_USER_GUIDE_URL,
    VIIRS_VERSION,
    VIIRS_YEAR,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cached_download(
    url: str,
    destination: Path,
    *,
    headers: dict[str, str] | None = None,
    minimum_bytes: int = 1,
) -> Path:
    """Download atomically, or reuse a plausibly complete cached file."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.stat().st_size >= minimum_bytes:
        return destination

    temporary = destination.with_suffix(destination.suffix + ".part")
    if temporary.exists():
        temporary.unlink()
    with requests.get(url, headers=headers, stream=True, timeout=(30, 300)) as response:
        response.raise_for_status()
        with temporary.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    if temporary.stat().st_size < minimum_bytes:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Downloaded file is unexpectedly small: {destination.name}")
    temporary.replace(destination)
    return destination


def _tile_identifier_column(columns: Iterable[str]) -> str:
    candidates = {column.lower(): column for column in columns}
    for name in ("tile_id", "tileid", "tile", "name"):
        if name in candidates:
            return candidates[name]
    raise ValueError("The official GHSL tile schema has no recognizable tile ID column.")


def download_jrc_tiles(
    districts_wgs84: gpd.GeoDataFrame,
    cache_dir: Path,
) -> tuple[list[Path], dict[str, Any]]:
    """Discover and cache only GHSL Mollweide tiles intersecting Shanghai."""

    cache_dir.mkdir(parents=True, exist_ok=True)
    schema_zip = _cached_download(
        JRC_TILE_SCHEMA_URL,
        cache_dir / "GHSL_data_54009_shapefile.zip",
        minimum_bytes=10_000,
    )
    schema = gpd.read_file(f"zip://{schema_zip}")
    if schema.crs is None:
        raise ValueError("The GHSL tile schema does not declare a CRS.")
    id_column = _tile_identifier_column(schema.columns)
    shanghai = districts_wgs84.to_crs(schema.crs).geometry.union_all()
    required = schema.loc[schema.geometry.intersects(shanghai), id_column]
    tile_ids = sorted({str(value).strip() for value in required if str(value).strip()})
    tile_ids = [tile_id for tile_id in tile_ids if re.fullmatch(r"R\d+_C\d+", tile_id)]
    if not tile_ids:
        raise RuntimeError("No official GHSL tile intersects the Shanghai boundary.")

    raster_paths: list[Path] = []
    tile_records: list[dict[str, Any]] = []
    for tile_id in tile_ids:
        stem = (
            "GHS_BUILT_V_NRES_E2020_GLOBE_R2023A_54009_100_"
            f"V1_0_{tile_id}"
        )
        url = f"{JRC_TILE_BASE_URL}/{stem}.zip"
        archive = _cached_download(url, cache_dir / f"{stem}.zip", minimum_bytes=10_000)
        with zipfile.ZipFile(archive) as zipped:
            members = [name for name in zipped.namelist() if name.lower().endswith(".tif")]
            if len(members) != 1:
                raise RuntimeError(f"Expected one GeoTIFF in {archive.name}; found {members}")
            target = cache_dir / Path(members[0]).name
            if not target.exists() or target.stat().st_size == 0:
                zipped.extract(members[0], cache_dir)
                extracted = cache_dir / members[0]
                if extracted != target:
                    extracted.replace(target)
            raster_paths.append(target)
        tile_records.append(
            {
                "tile_id": tile_id,
                "url": url,
                "archive_sha256": sha256_file(archive),
                "raster_file": target.name,
            }
        )

    metadata = {
        "dataset": JRC_DATASET,
        "epoch": JRC_EPOCH,
        "resolution_metres": JRC_RESOLUTION_METRES,
        "crs": JRC_CRS,
        "variable": "non-residential built-up volume (cubic metres)",
        "product_url": JRC_PRODUCT_URL,
        "doi": JRC_DOI,
        "tile_schema_url": JRC_TILE_SCHEMA_URL,
        "license": JRC_LICENSE,
        "tiles": tile_records,
    }
    return raster_paths, metadata


def discover_viirs_granules(bounds: tuple[float, float, float, float]) -> list[str]:
    west, south, east, north = bounds
    response = requests.get(
        VIIRS_CMR_URL,
        params={
            "short_name": VIIRS_SHORT_NAME,
            "version": VIIRS_VERSION,
            "temporal": f"{VIIRS_YEAR}-01-01T00:00:00Z,{VIIRS_YEAR}-12-31T23:59:59Z",
            "bounding_box": f"{west},{south},{east},{north}",
            "page_size": 200,
        },
        timeout=60,
    )
    response.raise_for_status()
    entries = response.json().get("feed", {}).get("entry", [])
    year_marker = f".A{VIIRS_YEAR}001."
    links: set[str] = set()
    for entry in entries:
        for link in entry.get("links", []):
            href = str(link.get("href", ""))
            if (
                href.startswith(("https://", "http://"))
                and year_marker in href
                and href.lower().endswith(".h5")
            ):
                links.add(href)
    if not links:
        raise RuntimeError(
            f"CMR returned no {VIIRS_SHORT_NAME} v{VIIRS_VERSION} {VIIRS_YEAR} granule "
            "intersecting Shanghai."
        )
    return sorted(links)


def download_viirs_granules(
    bounds: tuple[float, float, float, float],
    cache_dir: Path,
    earthdata_token: str,
) -> tuple[list[Path], dict[str, Any]]:
    """Cache numerical HDF5 granules without logging or persisting the token."""

    if not isinstance(earthdata_token, str) or not earthdata_token.strip():
        raise ValueError("EARTHDATA_TOKEN is unavailable; add it to Colab Secrets.")
    cache_dir.mkdir(parents=True, exist_ok=True)
    urls = discover_viirs_granules(bounds)
    paths = [
        _cached_download(
            url,
            cache_dir / Path(url).name,
            headers={"Authorization": f"Bearer {earthdata_token.strip()}"},
            minimum_bytes=1_000_000,
        )
        for url in urls
    ]
    metadata = {
        "dataset": VIIRS_SHORT_NAME,
        "year": VIIRS_YEAR,
        "version": VIIRS_VERSION,
        "product_type": "annual numerical nighttime-light science product",
        "native_resolution": VIIRS_NATIVE_RESOLUTION,
        "native_crs": "geographic latitude/longitude",
        "radiance_variable": VIIRS_RADIANCE_VARIABLE,
        "radiance_units": "nW cm^-2 sr^-1",
        "quality_variable": VIIRS_QUALITY_VARIABLE,
        "quality_rule": "quality == 0 (NASA good-quality flag; 1, 2, and 255 excluded)",
        "resampling_disclosure": (
            "Native 15-arc-second radiance is assigned by nearest native-pixel centre "
            "to 100 m analysis-cell centres; this does not create 100 m VIIRS detail."
        ),
        "cmr_discovery_url": VIIRS_CMR_URL,
        "product_url": VIIRS_PRODUCT_URL,
        "doi": VIIRS_DOI,
        "user_guide_url": VIIRS_USER_GUIDE_URL,
        "license": VIIRS_LICENSE,
        "granules": [
            {"url": url, "file": path.name, "sha256": sha256_file(path)}
            for url, path in zip(urls, paths, strict=True)
        ],
    }
    return paths, metadata


def latest_overture_release() -> str:
    response = requests.get(OVERTURE_CATALOG_URL, timeout=60)
    response.raise_for_status()
    catalog = response.json()
    latest = str(catalog.get("latest", "")).strip().rstrip("/").split("/")[-1]
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}\.\d+", latest):
        raise RuntimeError(f"Unexpected Overture latest release identifier: {latest!r}")
    return latest


def download_overture_places(
    districts_wgs84: gpd.GeoDataFrame,
    cache_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    """Use the official client, then cache only Places intersecting Shanghai."""

    if districts_wgs84.crs is None:
        raise ValueError("Shanghai districts must declare a CRS for Overture clipping.")
    districts_wgs84 = districts_wgs84.to_crs("EPSG:4326")
    bounds = tuple(float(value) for value in districts_wgs84.total_bounds)
    shanghai = districts_wgs84.geometry.union_all()
    release = latest_overture_release()
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_dir / f"places-{release}.parquet"
    if destination.exists() and destination.stat().st_size > 10_000:
        places = gpd.read_parquet(destination)
        if places.empty:
            raise RuntimeError(f"Cached Overture file is empty: {destination}")
        if places.crs is None:
            raise RuntimeError(f"Cached Overture file has no CRS: {destination}")
    else:
        temporary = cache_dir / f"places-{release}.part.parquet"
        temporary.unlink(missing_ok=True)
        bbox = ",".join(f"{value:.8f}" for value in bounds)
        subprocess.run(
            [
                "overturemaps",
                "download",
                f"--bbox={bbox}",
                "-f",
                "geoparquet",
                "--type=place",
                "--release",
                release,
                "-o",
                str(temporary),
            ],
            check=True,
        )
        places = gpd.read_parquet(temporary)
        if places.empty:
            temporary.unlink(missing_ok=True)
            raise RuntimeError("The official Overture client returned no Shanghai Places.")
        if places.crs is None:
            temporary.unlink(missing_ok=True)
            raise RuntimeError("The official Overture client output has no CRS.")
        places = places.to_crs("EPSG:4326")
        places = places.loc[places.geometry.intersects(shanghai)].copy()
        if places.empty:
            temporary.unlink(missing_ok=True)
            raise RuntimeError("No Overture Places intersect the exact Shanghai boundary.")
        places.to_parquet(temporary, index=False)
        temporary.replace(destination)

    places_wgs84 = places.to_crs("EPSG:4326")
    if not places_wgs84.geometry.intersects(shanghai).all():
        raise RuntimeError("Cached Overture Places include features outside Shanghai.")

    metadata = {
        "dataset": "Overture Maps Places",
        "release": release,
        "feature_type": "place",
        "download_scope": {
            "query_bbox_wgs84": list(bounds),
            "cached_filter": "geometry intersects the pinned 16-district Shanghai union",
        },
        "official_client": f"overturemaps=={OVERTURE_CLIENT_VERSION}",
        "catalog_url": OVERTURE_CATALOG_URL,
        "documentation_url": OVERTURE_DOCS_URL,
        "license_url": OVERTURE_LICENSE_URL,
        "license_summary": (
            "Places combines sources under CDLA Permissive 2.0, Apache 2.0, "
            "and CC0; see the release attribution page."
        ),
        "file": destination.name,
        "sha256": sha256_file(destination),
        "rows_intersecting_shanghai": int(len(places)),
    }
    return destination, metadata


def write_source_manifest(path: Path, records: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
