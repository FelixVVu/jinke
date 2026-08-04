"""Strict production data generator for the Jinke metro + walk reach map.

The default is a no-network dry run. Real ORS requests require both RUN_ORS=true
and an API key supplied by the caller. Production exports are cache-only: they
are refused unless the complete legacy 50-minute cache and every 10/20/30/40
minute cache are present, valid, and unionable with Shapely.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import random
import re
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

LIMITS = (10, 20, 30, 40, 50)
LOWER_LIMITS = (10, 20, 30, 40)
DATA_VERSION = "jinke-reach-v3"
MIN_ORS_INTERVAL_SECONDS = 3.5
DEFAULT_MAX_ORS_CALLS = 200
DEFAULT_MIN_LEGACY_50_ACCEPTED = 150

SHEET_CSV = (
    "https://docs.google.com/spreadsheets/d/"
    "1zgjzTXIxbgGUOkAIhFW3u7HoV529hx_QZc0advznuC8/"
    "export?format=csv&gid=0"
)
ORS_URL = "https://api.openrouteservice.org/v2/isochrones/foot-walking"

_DRIVE_BASE = Path("/content/drive/MyDrive/Jinke50min")


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "run_ors",
    }


@dataclass(frozen=True)
class Config:
    sheet_csv: str = SHEET_CSV
    coords_csv: Path = Path("data/station_coordinates_416.csv")
    web_data_dir: Path = Path("web/public/data")
    audit_dir: Path = _DRIVE_BASE / "audit_outputs"
    legacy_cache_dir: Path = _DRIVE_BASE / "ors_cache_50min"
    cache_dir: Path = _DRIVE_BASE / "ors_cache_multilimit_v1"
    dry_run: bool = not _env_flag("RUN_ORS")
    max_calls: int = int(os.environ.get("MAX_ORS_CALLS", DEFAULT_MAX_ORS_CALLS))
    request_interval: float = float(
        os.environ.get("ORS_REQUEST_INTERVAL", MIN_ORS_INTERVAL_SECONDS)
    )
    min_legacy_50_accepted: int = int(
        os.environ.get(
            "MIN_LEGACY_50_ACCEPTED",
            DEFAULT_MIN_LEGACY_50_ACCEPTED,
        )
    )
    test_mode: bool = _env_flag("TEST_MODE")

    def __post_init__(self) -> None:
        for field_name in (
            "coords_csv",
            "web_data_dir",
            "audit_dir",
            "legacy_cache_dir",
            "cache_dir",
        ):
            object.__setattr__(self, field_name, Path(getattr(self, field_name)))

        if self.request_interval < MIN_ORS_INTERVAL_SECONDS:
            raise ValueError(
                "ORS request_interval must be at least "
                f"{MIN_ORS_INTERVAL_SECONDS:.1f} seconds; "
                f"received {self.request_interval}."
            )
        if self.max_calls < 0:
            raise ValueError("max_calls cannot be negative.")
        if self.min_legacy_50_accepted < 0:
            raise ValueError("min_legacy_50_accepted cannot be negative.")


class CacheValidationError(RuntimeError):
    """Raised when a cache file is missing or is not valid polygon GeoJSON."""


class ORSCallBudgetExhausted(RuntimeError):
    """Raised before an ORS request would exceed MAX_ORS_CALLS."""


def rows_from_csv(path_or_url: str | Path) -> list[dict[str, str]]:
    if str(path_or_url).startswith(("http://", "https://")):
        with urllib.request.urlopen(str(path_or_url), timeout=30) as response:
            text = response.read().decode("utf-8-sig")
    else:
        text = Path(path_or_url).read_text(encoding="utf-8-sig")
    return list(csv.DictReader(text.splitlines()))


def load_stations(cfg: Config) -> list[dict[str, Any]]:
    time_source: str | Path = (
        Path("tests/fixtures/apple_times.csv") if cfg.test_mode else cfg.sheet_csv
    )
    time_rows = rows_from_csv(time_source)
    coordinate_rows = rows_from_csv(cfg.coords_csv)

    coordinates: dict[str, dict[str, str]] = {}
    for row in coordinate_rows:
        station = str(row.get("station", "")).strip()
        if not station:
            raise ValueError("Coordinate CSV contains an empty station name.")
        if station in coordinates:
            raise ValueError(f"Duplicate coordinate row: {station}")
        coordinates[station] = row

    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in time_rows:
        station = str(row.get("station", "")).strip()
        if not station:
            raise ValueError("Google Sheet contains an empty station name.")
        if station in seen:
            raise ValueError(f"Duplicate station in Google Sheet: {station}")
        seen.add(station)

        coordinate = coordinates.get(station)
        if coordinate is None:
            raise ValueError(f"Missing coordinates: {station}")

        try:
            apple = float(row["apple"])
            lon = float(coordinate["lon"])
            lat = float(coordinate["lat"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid station data for {station}: {exc}") from exc

        if not math.isfinite(apple) or apple < 0:
            raise ValueError(f"Invalid Apple transit time for {station}: {apple}")
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError(f"Invalid coordinates for {station}: {lon}, {lat}")

        output.append(
            {
                "ID": row.get("ID"),
                "station": station,
                "apple": apple,
                "lon": lon,
                "lat": lat,
            }
        )

    return output


def classify(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    classified: list[dict[str, Any]] = []
    for row in rows:
        apple = float(row["apple"])
        classified.append(
            {
                **row,
                "selected_limit": limit,
                "remaining_walk_minutes": max(0.0, limit - apple),
                "status": (
                    "included"
                    if apple < limit
                    else "boundary"
                    if apple == limit
                    else "excluded"
                ),
            }
        )
    return classified


def safe_filename(text: str) -> str:
    """Match the filename sanitizer used by the completed legacy notebook."""

    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", str(text))


def cache_key(
    station: str,
    lon: float,
    lat: float,
    seconds: int,
    limit: int,
) -> str:
    raw = json.dumps(
        {
            "station": station,
            "lon": round(float(lon), 7),
            "lat": round(float(lat), 7),
            "seconds": int(seconds),
            "limit": int(limit),
            "version": DATA_VERSION,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def legacy_cache_path(cfg: Config, request: dict[str, Any]) -> Path:
    return cfg.legacy_cache_dir / (
        f"{safe_filename(request['station'])}_{int(request['seconds'])}s.json"
    )


def modern_cache_path(cfg: Config, request: dict[str, Any]) -> Path:
    key = cache_key(
        request["station"],
        request["lon"],
        request["lat"],
        request["seconds"],
        request["limit"],
    )
    return cfg.cache_dir / f"{key}.geojson"


def required_requests(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for limit in LIMITS:
        for row in rows:
            apple = float(row["apple"])
            if apple >= limit:
                continue
            seconds = int(round((limit - apple) * 60))
            if seconds <= 0:
                raise ValueError(
                    f"Non-positive walk duration for {row['station']} at {limit} minutes."
                )
            requests.append(
                {
                    "station": row["station"],
                    "lon": float(row["lon"]),
                    "lat": float(row["lat"]),
                    "apple": apple,
                    "seconds": seconds,
                    "limit": limit,
                }
            )
    return requests


def _polygon_geometries(payload: dict[str, Any]) -> list[Any]:
    if not isinstance(payload, dict):
        raise CacheValidationError("top-level JSON value is not an object")

    feature_collection = payload.get("data", payload)
    if not isinstance(feature_collection, dict):
        raise CacheValidationError("cache data is not an object")
    if feature_collection.get("type") != "FeatureCollection":
        raise CacheValidationError("cache is not a FeatureCollection")

    features = feature_collection.get("features")
    if not isinstance(features, list) or not features:
        raise CacheValidationError("FeatureCollection is empty")

    geometries = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise CacheValidationError(f"feature {index} is not an object")
        geometry_data = feature.get("geometry")
        if not isinstance(geometry_data, dict):
            raise CacheValidationError(f"feature {index} has no geometry")
        try:
            geometry = shape(geometry_data)
        except Exception as exc:
            raise CacheValidationError(
                f"feature {index} geometry cannot be parsed: {exc}"
            ) from exc

        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise CacheValidationError(
                f"feature {index} is {geometry.geom_type}, not Polygon/MultiPolygon"
            )
        if geometry.is_empty or geometry.area <= 0:
            raise CacheValidationError(f"feature {index} polygon is empty")
        if not geometry.is_valid:
            raise CacheValidationError(f"feature {index} polygon is invalid")

        min_lon, min_lat, max_lon, max_lat = geometry.bounds
        bounds = (min_lon, min_lat, max_lon, max_lat)
        if not all(math.isfinite(value) for value in bounds):
            raise CacheValidationError(f"feature {index} bounds are not finite")
        if not (
            -180 <= min_lon <= 180
            and -180 <= max_lon <= 180
            and -90 <= min_lat <= 90
            and -90 <= max_lat <= 90
        ):
            raise CacheValidationError(
                f"feature {index} bounds are outside WGS84: {bounds}"
            )
        geometries.append(geometry)

    return geometries


def validate_geojson_cache(path: Path) -> tuple[bool, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        geometries = _polygon_geometries(payload)
        return True, f"accepted ({len(geometries)} polygon feature(s))"
    except Exception as exc:
        return False, str(exc)


def load_cache_geometries(path: Path) -> list[Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise CacheValidationError(f"missing cache file: {path}") from exc
    except Exception as exc:
        raise CacheValidationError(f"cannot read {path}: {exc}") from exc

    try:
        return _polygon_geometries(payload)
    except CacheValidationError as exc:
        raise CacheValidationError(f"invalid cache {path}: {exc}") from exc


def cache_status(rows: list[dict[str, Any]], cfg: Config) -> dict[str, Any]:
    required_by_limit = {str(limit): 0 for limit in LIMITS}
    cache_hits_by_limit = {str(limit): 0 for limit in LIMITS}
    missing_by_limit = {str(limit): 0 for limit in LIMITS}

    legacy_found = 0
    legacy_accepted = 0
    legacy_rejections: list[dict[str, Any]] = []
    legacy_missing: list[dict[str, Any]] = []
    modern_hits = 0
    modern_rejections: list[dict[str, Any]] = []
    new_requests: list[dict[str, Any]] = []

    for request in required_requests(rows):
        limit_key = str(request["limit"])
        required_by_limit[limit_key] += 1

        if request["limit"] == 50:
            path = legacy_cache_path(cfg, request)
            if not path.exists():
                missing_by_limit[limit_key] += 1
                legacy_missing.append(
                    {
                        "file": str(path),
                        "station": request["station"],
                        "seconds": request["seconds"],
                    }
                )
                continue

            legacy_found += 1
            valid, reason = validate_geojson_cache(path)
            if valid:
                legacy_accepted += 1
                cache_hits_by_limit[limit_key] += 1
            else:
                missing_by_limit[limit_key] += 1
                legacy_rejections.append(
                    {
                        "file": str(path),
                        "station": request["station"],
                        "seconds": request["seconds"],
                        "reason": reason,
                    }
                )
            continue

        path = modern_cache_path(cfg, request)
        if path.exists():
            valid, reason = validate_geojson_cache(path)
            if valid:
                modern_hits += 1
                cache_hits_by_limit[limit_key] += 1
                continue
            modern_rejections.append(
                {
                    "file": str(path),
                    "station": request["station"],
                    "limit": request["limit"],
                    "seconds": request["seconds"],
                    "reason": reason,
                }
            )

        missing_by_limit[limit_key] += 1
        new_requests.append(
            {
                **request,
                "key": path.stem,
                "cache_file": str(path),
            }
        )

    legacy_expected = required_by_limit["50"]
    all_complete = (
        legacy_accepted == legacy_expected
        and not legacy_rejections
        and not legacy_missing
        and not new_requests
        and not modern_rejections
    )

    return {
        "stations_below_limit": required_by_limit.copy(),
        "required_cache_files_by_limit": required_by_limit,
        "cache_hits_by_limit": cache_hits_by_limit,
        "missing_cache_files_by_limit": missing_by_limit,
        "required_cache_files_total": sum(required_by_limit.values()),
        "modern_cache_hits": modern_hits,
        "modern_cache_files_rejected": len(modern_rejections),
        "modern_rejections": modern_rejections,
        "legacy_50_cache_files_expected": legacy_expected,
        "legacy_50_cache_files_found": legacy_found,
        "legacy_50_cache_files_accepted": legacy_accepted,
        "legacy_50_cache_files_rejected": len(legacy_rejections),
        "legacy_50_cache_files_missing": len(legacy_missing),
        "legacy_rejections": legacy_rejections,
        "legacy_missing": legacy_missing,
        "estimated_additional_calls": len(new_requests),
        "requests": new_requests,
        "all_required_caches_complete": all_complete,
    }


def _status_without_requests(status: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in status.items()
        if key not in {"requests", "legacy_missing"}
    }


def assert_legacy_cache_ready(status: dict[str, Any], cfg: Config) -> None:
    expected = int(status["legacy_50_cache_files_expected"])
    accepted = int(status["legacy_50_cache_files_accepted"])
    minimum = min(cfg.min_legacy_50_accepted, expected)

    if expected <= 0:
        raise RuntimeError(
            "Legacy 50-minute cache safety stop: the input data contains no "
            "stations below 50 minutes."
        )

    if accepted < minimum:
        raise RuntimeError(
            "Legacy 50-minute cache safety stop: accepted "
            f"{accepted} of {expected} required files, below the minimum "
            f"safety threshold of {minimum}. Expected production is about 175. "
            f"Confirm Google Drive is mounted and that {cfg.legacy_cache_dir} "
            "contains files such as 金科路_3000s.json. No ORS calls were made."
        )

    rejected = int(status["legacy_50_cache_files_rejected"])
    missing = int(status["legacy_50_cache_files_missing"])
    if accepted != expected or rejected or missing:
        raise RuntimeError(
            "Legacy 50-minute cache is incomplete: accepted "
            f"{accepted}/{expected}, missing {missing}, rejected {rejected}. "
            "The generator will not replace legacy files or make lower-limit "
            "ORS calls until every required 50-minute legacy cache is valid."
        )


def assert_all_caches_complete(
    rows: list[dict[str, Any]],
    cfg: Config,
) -> dict[str, Any]:
    status = cache_status(rows, cfg)
    assert_legacy_cache_ready(status, cfg)

    remaining = int(status["estimated_additional_calls"])
    rejected = int(status["modern_cache_files_rejected"])
    if remaining or rejected:
        raise RuntimeError(
            "Production export blocked: lower-limit caches are incomplete. "
            f"Remaining ORS requests: {remaining}; rejected new cache files: "
            f"{rejected}. Run/resume the full lower-limit stage, then run "
            "validation and export again."
        )
    if not status["all_required_caches_complete"]:
        raise RuntimeError(
            "Production export blocked: required cache validation did not "
            "reach a complete state."
        )
    return status


def missing_requests(
    rows: list[dict[str, Any]],
    cfg: Config,
) -> list[dict[str, Any]]:
    """Return only missing 10/20/30/40-minute requests.

    The 50-minute layer is intentionally legacy-cache-only and is never
    included in this list.
    """

    return cache_status(rows, cfg)["requests"]


class ORSClient:
    def __init__(
        self,
        api_key: str,
        request_interval: float,
        max_calls: int,
        session: Any | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("ORS API key is required.")
        if request_interval < MIN_ORS_INTERVAL_SECONDS:
            raise ValueError(
                "ORS interval cannot be below "
                f"{MIN_ORS_INTERVAL_SECONDS:.1f} seconds."
            )

        if session is None:
            import requests

            session = requests.Session()

        self.api_key = api_key
        self.request_interval = request_interval
        self.max_calls = max_calls
        self.session = session
        self.calls_made = 0
        self.last_request_started: float | None = None

    def _post(self, payload: dict[str, Any]) -> Any:
        if self.calls_made >= self.max_calls:
            raise ORSCallBudgetExhausted(
                f"MAX_ORS_CALLS={self.max_calls} has been reached."
            )

        if self.last_request_started is not None:
            elapsed = time.monotonic() - self.last_request_started
            wait = self.request_interval - elapsed
            if wait > 0:
                time.sleep(wait)

        self.last_request_started = time.monotonic()
        self.calls_made += 1
        return self.session.post(
            ORS_URL,
            headers={
                "Authorization": self.api_key,
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/geo+json, application/json",
            },
            json=payload,
            timeout=180,
        )

    def request_isochrone(
        self,
        request: dict[str, Any],
        max_retries: int = 6,
    ) -> dict[str, Any]:
        payload = {
            "locations": [[request["lon"], request["lat"]]],
            "range": [request["seconds"]],
            "range_type": "time",
            "attributes": ["area", "reachfactor"],
            "smoothing": 20,
        }

        last_response = None
        for attempt in range(max_retries):
            response = self._post(payload)
            last_response = response

            if response.status_code == 200:
                result = response.json()
                _polygon_geometries(result)
                for feature in result["features"]:
                    properties = feature.setdefault("properties", {})
                    properties.update(
                        {
                            "station": request["station"],
                            "apple_min": request["apple"],
                            "walk_sec": request["seconds"],
                            "total_limit_min": request["limit"],
                        }
                    )
                return result

            if response.status_code == 429:
                if self.calls_made >= self.max_calls:
                    raise ORSCallBudgetExhausted(
                        f"MAX_ORS_CALLS={self.max_calls} has been reached."
                    )
                if attempt + 1 >= max_retries:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = max(float(retry_after), 10.0)
                except (TypeError, ValueError):
                    delay = min(30.0 * (attempt + 1), 300.0)
                time.sleep(delay)
                continue

            if response.status_code in {500, 502, 503, 504}:
                if self.calls_made >= self.max_calls:
                    raise ORSCallBudgetExhausted(
                        f"MAX_ORS_CALLS={self.max_calls} has been reached."
                    )
                if attempt + 1 >= max_retries:
                    response.raise_for_status()
                delay = min(
                    max(self.request_interval, 2**attempt + random.random()),
                    180.0,
                )
                time.sleep(delay)
                continue

            response.raise_for_status()

        if last_response is not None:
            last_response.raise_for_status()
        raise RuntimeError(
            f"{request['station']} failed after {max_retries} attempts."
        )


def fill_cache(
    rows: list[dict[str, Any]],
    cfg: Config,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Validate caches and optionally fill missing lower-limit files.

    Valid legacy files are read only. Every newly written cache goes to
    cfg.cache_dir, which is created automatically.
    """

    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    initial_status = cache_status(rows, cfg)
    report: dict[str, Any] = {
        "dry_run": cfg.dry_run,
        "max_ors_calls": cfg.max_calls,
        "request_interval_seconds": cfg.request_interval,
        "initial_status": _status_without_requests(initial_status),
        "initial_missing_requests": initial_status["estimated_additional_calls"],
        "request_preview": initial_status["requests"][:10],
        "ors_calls_made": 0,
        "new_cache_files_written": 0,
        "failures": [],
    }

    assert_legacy_cache_ready(initial_status, cfg)

    if cfg.dry_run:
        report["remaining_requests"] = initial_status["estimated_additional_calls"]
        report["final_status"] = _status_without_requests(initial_status)
        return report

    if not api_key:
        raise RuntimeError(
            "RUN_ORS=True but ORS_API_KEY was not loaded. Add ORS_API_KEY "
            "to Colab Secrets, allow notebook access, and rerun setup."
        )

    client = ORSClient(
        api_key=api_key,
        request_interval=cfg.request_interval,
        max_calls=cfg.max_calls,
    )

    for request in initial_status["requests"]:
        if client.calls_made >= cfg.max_calls:
            break

        destination = modern_cache_path(cfg, request)
        try:
            result = client.request_isochrone(request)
            cache_payload = {"meta": request, "data": result}
            _polygon_geometries(cache_payload)

            temporary = destination.with_name(destination.name + ".tmp")
            temporary.write_text(
                json.dumps(cache_payload, ensure_ascii=False),
                encoding="utf-8",
            )
            temporary.replace(destination)
            report["new_cache_files_written"] += 1
        except ORSCallBudgetExhausted:
            break
        except Exception as exc:
            report["failures"].append(
                {
                    "station": request["station"],
                    "limit": request["limit"],
                    "seconds": request["seconds"],
                    "error": repr(exc),
                }
            )

    final_status = cache_status(rows, cfg)
    report["ors_calls_made"] = client.calls_made
    report["remaining_requests"] = final_status["estimated_additional_calls"]
    report["final_status"] = _status_without_requests(final_status)
    return report


def _validate_union_geometry(geometry: Any, limit: int) -> None:
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise RuntimeError(
            f"{limit}-minute Shapely union produced {geometry.geom_type}, "
            "not Polygon/MultiPolygon."
        )
    if geometry.is_empty or geometry.area <= 0:
        raise RuntimeError(f"{limit}-minute Shapely union is empty.")
    if not geometry.is_valid:
        raise RuntimeError(f"{limit}-minute Shapely union is invalid.")


def _write_outputs_atomically(
    payloads: dict[str, str],
    web_data_dir: Path,
    audit_dir: Path,
) -> Path:
    web_data_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)

    for name, text in payloads.items():
        destination = web_data_dir / name
        temporary = destination.with_name(destination.name + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(destination)

    zip_path = audit_dir / "web-data.zip"
    temporary_zip = zip_path.with_name(zip_path.name + ".tmp")
    with zipfile.ZipFile(
        temporary_zip,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for name, text in payloads.items():
            archive.writestr(name, text)
    temporary_zip.replace(zip_path)
    return zip_path


def build_outputs(
    rows: list[dict[str, Any]],
    cfg: Config,
) -> dict[str, Any]:
    """Build production outputs only from complete, validated real caches."""

    status = assert_all_caches_complete(rows, cfg)
    requests = required_requests(rows)
    requests_by_limit = {
        limit: [request for request in requests if request["limit"] == limit]
        for limit in LIMITS
    }

    area_features: list[dict[str, Any]] = []
    for limit in LIMITS:
        layer_geometries = []
        for request in requests_by_limit[limit]:
            path = (
                legacy_cache_path(cfg, request)
                if limit == 50
                else modern_cache_path(cfg, request)
            )
            layer_geometries.extend(load_cache_geometries(path))

        if not layer_geometries:
            raise RuntimeError(
                f"Production export blocked: {limit}-minute layer has no polygons."
            )

        union_geometry = unary_union(layer_geometries)
        _validate_union_geometry(union_geometry, limit)
        area_features.append(
            {
                "type": "Feature",
                "properties": {
                    "limit": limit,
                    "included_stations": sum(
                        float(row["apple"]) < limit for row in rows
                    ),
                    "boundary_stations": sum(
                        float(row["apple"]) == limit for row in rows
                    ),
                    "source_polygon_count": len(layer_geometries),
                },
                "geometry": mapping(union_geometry),
            }
        )

    if [feature["properties"]["limit"] for feature in area_features] != list(LIMITS):
        raise RuntimeError("Production export blocked: not all five layers were built.")

    station_features = [
        {
            "type": "Feature",
            "properties": {
                "station": row["station"],
                "apple": row["apple"],
                "is_jinke": row["station"] == "金科路",
            },
            "geometry": {
                "type": "Point",
                "coordinates": [row["lon"], row["lat"]],
            },
        }
        for row in rows
    ]

    manifest = {
        "data_version": DATA_VERSION,
        "limits": list(LIMITS),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_sheet": cfg.sheet_csv,
        "geometry_union": "shapely.unary_union",
        "legacy_50_cache_files_accepted": status[
            "legacy_50_cache_files_accepted"
        ],
        "lower_limit_cache_files_accepted": sum(
            status["cache_hits_by_limit"][str(limit)]
            for limit in LOWER_LIMITS
        ),
        "all_five_layers_complete": True,
        "production_data": True,
    }

    documents = {
        "manifest.json": manifest,
        "reach-areas.geojson": {
            "type": "FeatureCollection",
            "features": area_features,
        },
        "stations.geojson": {
            "type": "FeatureCollection",
            "features": station_features,
        },
    }
    payloads = {
        name: json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        for name, document in documents.items()
    }

    zip_path = _write_outputs_atomically(
        payloads,
        cfg.web_data_dir,
        cfg.audit_dir,
    )
    manifest["zip_path"] = str(zip_path)
    return manifest


def main() -> None:
    cfg = Config()
    rows = load_stations(cfg)
    report = fill_cache(rows, cfg, os.environ.get("ORS_API_KEY"))
    output: dict[str, Any] = {"request_report": report}

    if not cfg.dry_run and report["remaining_requests"] == 0:
        output["manifest"] = build_outputs(rows, cfg)
    elif not cfg.dry_run:
        output["export"] = (
            "Skipped: required lower-limit caches are still incomplete."
        )

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
