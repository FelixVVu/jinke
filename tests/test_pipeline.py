import json
import zipfile
from pathlib import Path

import pytest
from shapely.geometry import shape

from pipeline import generate
from pipeline.generate import (
    Config,
    build_outputs,
    cache_key,
    cache_status,
    classify,
    fill_cache,
    legacy_cache_path,
    missing_requests,
    modern_cache_path,
    required_requests,
)


def polygon_payload(x=121.5, y=31.2, size=0.001):
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [x, y],
                            [x + size, y],
                            [x + size, y + size],
                            [x, y + size],
                            [x, y],
                        ]
                    ],
                },
            }
        ],
    }


def config_for(tmp_path, **overrides):
    values = {
        "web_data_dir": tmp_path / "web",
        "audit_dir": tmp_path / "audit_outputs",
        "legacy_cache_dir": tmp_path / "ors_cache_50min",
        "cache_dir": tmp_path / "ors_cache_multilimit_v1",
        "dry_run": True,
        "max_calls": 200,
        "request_interval": 3.5,
        "min_legacy_50_accepted": 0,
    }
    values.update(overrides)
    return Config(**values)


def write_cache(path, payload=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload or polygon_payload(), ensure_ascii=False),
        encoding="utf-8",
    )


def write_all_required_caches(rows, cfg):
    for request in required_requests(rows):
        path = (
            legacy_cache_path(cfg, request)
            if request["limit"] == 50
            else modern_cache_path(cfg, request)
        )
        x = float(request["lon"])
        y = float(request["lat"])
        write_cache(path, polygon_payload(x=x, y=y))


def test_limit_classification_excludes_boundary_zero_second_requests(tmp_path):
    rows = [
        {"station": "A", "apple": 9, "lon": 1, "lat": 2},
        {"station": "B", "apple": 10, "lon": 1, "lat": 2},
        {"station": "C", "apple": 11, "lon": 1, "lat": 2},
    ]
    classified = classify(rows, 10)
    assert [row["status"] for row in classified] == [
        "included",
        "boundary",
        "excluded",
    ]

    requests = missing_requests(classified, config_for(tmp_path))
    assert all(request["seconds"] > 0 for request in requests)
    assert not any(
        request["station"] == "B" and request["limit"] == 10
        for request in requests
    )
    assert not any(
        request["station"] == "C" and request["limit"] == 10
        for request in requests
    )


def test_cache_key_includes_limit_duration_station_and_coordinates():
    baseline = cache_key("A", 1, 2, 60, 10)
    assert baseline != cache_key("A", 1, 2, 120, 10)
    assert baseline != cache_key("A", 1, 2, 60, 20)
    assert baseline != cache_key("B", 1, 2, 60, 10)
    assert baseline != cache_key("A", 1.1, 2, 60, 10)


def test_minimum_ors_interval_is_enforced(tmp_path):
    with pytest.raises(ValueError, match="at least 3.5 seconds"):
        config_for(tmp_path, request_interval=3.49)


def test_legacy_readable_filename_is_accepted_and_never_modified(tmp_path):
    rows = [
        {
            "station": "金科路",
            "apple": 0,
            "lon": 121.597836,
            "lat": 31.2064028,
        }
    ]
    cfg = config_for(tmp_path, min_legacy_50_accepted=1)
    legacy_request = next(
        request
        for request in required_requests(rows)
        if request["limit"] == 50
    )
    path = legacy_cache_path(cfg, legacy_request)
    assert path.name == "金科路_3000s.json"

    write_cache(path)
    original = path.read_bytes()
    report = fill_cache(rows, cfg)

    assert report["initial_status"]["legacy_50_cache_files_accepted"] == 1
    assert report["initial_missing_requests"] == 4
    assert report["remaining_requests"] == 4
    assert cfg.cache_dir.is_dir()
    assert path.read_bytes() == original
    assert {request["limit"] for request in missing_requests(rows, cfg)} == {
        10,
        20,
        30,
        40,
    }


def test_close_to_zero_legacy_cache_stops_before_any_ors_call(tmp_path):
    rows = [
        {
            "station": "金科路",
            "apple": 0,
            "lon": 121.597836,
            "lat": 31.2064028,
        }
    ]
    cfg = config_for(
        tmp_path,
        dry_run=False,
        min_legacy_50_accepted=1,
    )

    with pytest.raises(RuntimeError, match="accepted 0 of 1.*No ORS calls"):
        fill_cache(rows, cfg, api_key="unused-test-key")

    assert cfg.cache_dir.is_dir()
    assert list(cfg.cache_dir.iterdir()) == []


def test_expected_production_dry_run_counts_are_175_and_173(tmp_path):
    rows = []
    groups = [(4, 5), (8, 15), (30, 25), (73, 35), (60, 45)]
    station_index = 0
    for count, apple in groups:
        for _ in range(count):
            rows.append(
                {
                    "station": f"站{station_index}",
                    "apple": apple,
                    "lon": 121.0 + station_index * 0.00001,
                    "lat": 31.0,
                }
            )
            station_index += 1

    cfg = config_for(tmp_path, min_legacy_50_accepted=150)
    for request in required_requests(rows):
        if request["limit"] == 50:
            write_cache(legacy_cache_path(cfg, request))

    report = fill_cache(rows, cfg)
    status = report["initial_status"]
    assert status["legacy_50_cache_files_accepted"] == 175
    assert report["initial_missing_requests"] == 173
    assert status["required_cache_files_by_limit"] == {
        "10": 4,
        "20": 12,
        "30": 42,
        "40": 115,
        "50": 175,
    }


def test_live_fill_writes_only_new_cache_directory_with_call_budget(
    tmp_path,
    monkeypatch,
):
    rows = [
        {
            "station": "金科路",
            "apple": 0,
            "lon": 121.597836,
            "lat": 31.2064028,
        }
    ]
    cfg = config_for(
        tmp_path,
        dry_run=False,
        max_calls=1,
        min_legacy_50_accepted=1,
    )
    legacy_request = next(
        request
        for request in required_requests(rows)
        if request["limit"] == 50
    )
    legacy = legacy_cache_path(cfg, legacy_request)
    write_cache(legacy)
    legacy_before = legacy.read_bytes()

    class FakeORSClient:
        def __init__(self, api_key, request_interval, max_calls):
            self.calls_made = 0
            self.max_calls = max_calls

        def request_isochrone(self, request):
            self.calls_made += 1
            return polygon_payload(request["lon"], request["lat"])

    monkeypatch.setattr(generate, "ORSClient", FakeORSClient)
    report = fill_cache(rows, cfg, api_key="test-key")

    assert report["ors_calls_made"] == 1
    assert report["new_cache_files_written"] == 1
    assert report["remaining_requests"] == 3
    assert len(list(cfg.cache_dir.glob("*.geojson"))) == 1
    assert legacy.read_bytes() == legacy_before


def test_ors_retry_never_exceeds_http_call_budget_or_waits_past_it(monkeypatch):
    class RateLimitedResponse:
        status_code = 429
        headers = {"Retry-After": "60"}

        def raise_for_status(self):
            raise AssertionError("raise_for_status should not replace budget stop")

    class FakeSession:
        def __init__(self):
            self.posts = 0

        def post(self, *args, **kwargs):
            self.posts += 1
            return RateLimitedResponse()

    sleeps = []
    session = FakeSession()
    client = generate.ORSClient(
        api_key="test-key",
        request_interval=3.5,
        max_calls=1,
        session=session,
    )
    monkeypatch.setattr(generate.time, "sleep", sleeps.append)

    with pytest.raises(generate.ORSCallBudgetExhausted, match="MAX_ORS_CALLS=1"):
        client.request_isochrone(
            {
                "station": "金科路",
                "apple": 0,
                "lon": 121.597836,
                "lat": 31.2064028,
                "seconds": 600,
                "limit": 10,
            }
        )

    assert session.posts == 1
    assert client.calls_made == 1
    assert sleeps == []


def test_export_is_blocked_until_every_real_cache_is_valid(tmp_path):
    rows = [
        {
            "station": "金科路",
            "apple": 0,
            "lon": 121.597836,
            "lat": 31.2064028,
        }
    ]
    cfg = config_for(tmp_path, min_legacy_50_accepted=1)
    legacy_request = next(
        request
        for request in required_requests(rows)
        if request["limit"] == 50
    )
    write_cache(legacy_cache_path(cfg, legacy_request))

    with pytest.raises(RuntimeError, match="lower-limit caches are incomplete"):
        build_outputs(rows, cfg)

    assert not (cfg.web_data_dir / "manifest.json").exists()
    assert not (cfg.audit_dir / "web-data.zip").exists()


def test_complete_export_uses_shapely_union_and_exact_zip_contents(tmp_path):
    rows = [
        {"station": "A", "apple": 0, "lon": 121.0, "lat": 31.0},
        {"station": "B", "apple": 0, "lon": 121.01, "lat": 31.0},
    ]
    cfg = config_for(tmp_path, min_legacy_50_accepted=2)
    write_all_required_caches(rows, cfg)

    manifest = build_outputs(rows, cfg)
    areas = json.loads(
        (cfg.web_data_dir / "reach-areas.geojson").read_text(encoding="utf-8")
    )
    saved_manifest = json.loads(
        (cfg.web_data_dir / "manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["production_data"] is True
    assert saved_manifest["production_data"] is True
    assert saved_manifest["all_five_layers_complete"] is True
    assert saved_manifest["geometry_union"] == "shapely.unary_union"
    assert [
        feature["properties"]["limit"] for feature in areas["features"]
    ] == [10, 20, 30, 40, 50]

    for feature in areas["features"]:
        geometry = shape(feature["geometry"])
        assert geometry.geom_type in {"Polygon", "MultiPolygon"}
        assert geometry.is_valid and not geometry.is_empty
        # Two disjoint 0.001 x 0.001 squares remain two real polygons.
        # A bounding-box fallback would have a much larger area.
        assert geometry.area == pytest.approx(0.000002)

    zip_path = cfg.audit_dir / "web-data.zip"
    with zipfile.ZipFile(zip_path) as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            "reach-areas.geojson",
            "stations.geojson",
        }


def test_invalid_modern_cache_is_rejected_and_production_stays_blocked(tmp_path):
    rows = [
        {
            "station": "金科路",
            "apple": 0,
            "lon": 121.597836,
            "lat": 31.2064028,
        }
    ]
    cfg = config_for(tmp_path, min_legacy_50_accepted=1)
    write_all_required_caches(rows, cfg)

    first_lower = next(
        request
        for request in required_requests(rows)
        if request["limit"] == 10
    )
    modern_cache_path(cfg, first_lower).write_text("{bad json", encoding="utf-8")

    status = cache_status(rows, cfg)
    assert status["modern_cache_files_rejected"] == 1
    assert status["estimated_additional_calls"] == 1
    assert status["all_required_caches_complete"] is False

    with pytest.raises(RuntimeError, match="lower-limit caches are incomplete"):
        build_outputs(rows, cfg)
    assert not (cfg.web_data_dir / "manifest.json").exists()
