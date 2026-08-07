import json
from pathlib import Path

from shapely.geometry import shape

from scripts.generate_outside_reach_areas import LIMITS, generate
from scripts.prepare_shanghai_boundary import (
    DISPLAY_SIMPLIFICATION_DEGREES,
    MINIMUM_VERTEX_COUNT,
    OCEAN_SHA256,
    SOURCE_SHA256,
    generate as generate_boundary,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "web" / "public" / "data"
BOUNDARY_PATH = DATA_DIR / "shanghai-boundary.geojson"
REACH_PATH = DATA_DIR / "reach-areas.geojson"
OUTSIDE_PATH = DATA_DIR / "outside-reach-areas.geojson"
BOUNDARY_SOURCE_PATH = ROOT / "data" / "shanghai-boundary-osm-r913067-v155.geojson"
OCEAN_SOURCE_PATH = ROOT / "data" / "shanghai-ocean-openfreemap-z10-20260802.geojson"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_inverse_file_is_deterministically_regenerated(tmp_path):
    regenerated = tmp_path / "outside-reach-areas.geojson"
    generate(BOUNDARY_PATH, REACH_PATH, regenerated)
    assert regenerated.read_bytes() == OUTSIDE_PATH.read_bytes()


def test_boundary_file_is_deterministically_regenerated(tmp_path):
    regenerated = tmp_path / "shanghai-boundary.geojson"
    generate_boundary(BOUNDARY_SOURCE_PATH, OCEAN_SOURCE_PATH, regenerated)
    assert regenerated.read_bytes() == BOUNDARY_PATH.read_bytes()


def test_inverse_geometries_are_exactly_shanghai_minus_each_reach_area():
    boundary_payload = load(BOUNDARY_PATH)
    reach_payload = load(REACH_PATH)
    outside_payload = load(OUTSIDE_PATH)

    assert boundary_payload["type"] == "FeatureCollection"
    assert len(boundary_payload["features"]) == 1
    boundary = shape(boundary_payload["features"][0]["geometry"])
    assert boundary.geom_type in {"Polygon", "MultiPolygon"}
    assert boundary.is_valid and not boundary.is_empty

    reaches = {
        int(feature["properties"]["limit"]): shape(feature["geometry"])
        for feature in reach_payload["features"]
    }
    assert set(reaches) == set(LIMITS)

    assert outside_payload["type"] == "FeatureCollection"
    assert len(outside_payload["features"]) == 5
    assert [
        int(feature["properties"]["limit"])
        for feature in outside_payload["features"]
    ] == list(LIMITS)

    for feature in outside_payload["features"]:
        limit = int(feature["properties"]["limit"])
        outside = shape(feature["geometry"])
        expected = boundary.difference(reaches[limit])

        assert outside.geom_type in {"Polygon", "MultiPolygon"}
        assert outside.is_valid and not outside.is_empty
        assert boundary.covers(outside)
        assert outside.intersection(reaches[limit]).area <= 1e-12
        assert outside.equals(expected)


def test_boundary_source_license_and_attribution_are_documented():
    properties = load(BOUNDARY_PATH)["features"][0]["properties"]
    assert properties["name"] == "Shanghai Municipality"
    assert properties["relationID"] == 913067
    assert properties["sourceURL"] == "https://www.openstreetmap.org/relation/913067"
    assert properties["sourceRevision"] == "relation 913067, version 155"
    assert properties["sourceSnapshotSHA256"] == SOURCE_SHA256
    assert properties["oceanSnapshotSHA256"] == OCEAN_SHA256
    assert properties["oceanTileRevision"] == "20260802_080001_pt"
    assert properties["oceanTileZoom"] == 10
    assert properties["license"] == "ODbL 1.0"
    assert properties["licenseURL"] == "https://www.openstreetmap.org/copyright"
    assert properties["attribution"] == "© OpenStreetMap contributors"


def test_boundary_is_detailed_local_shanghai_geometry():
    feature = load(BOUNDARY_PATH)["features"][0]
    boundary = shape(feature["geometry"])
    properties = feature["properties"]

    assert boundary.geom_type == "MultiPolygon"
    assert boundary.is_valid and not boundary.is_empty
    assert len(boundary.geoms) == 23
    assert properties["sourceComponentCount"] == 11
    assert properties["localAdministrativeComponentCount"] == 2
    assert properties["localComponentCount"] == 23
    assert properties["landFocused"] is True
    assert (
        properties["simplificationToleranceDegrees"]
        == DISPLAY_SIMPLIFICATION_DEGREES
    )
    assert properties["approximateSimplificationMeters"] == 17
    assert properties["vertexCount"] >= MINIMUM_VERTEX_COUNT
    assert 120.8 < boundary.bounds[0] < 121.0
    assert 30.6 < boundary.bounds[1] < 30.8
    assert 122.2 < boundary.bounds[2] < 122.3
    assert 31.8 < boundary.bounds[3] < 32.0
