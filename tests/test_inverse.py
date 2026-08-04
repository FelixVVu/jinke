import json
from pathlib import Path

from shapely.geometry import shape

from scripts.generate_outside_reach_areas import LIMITS, generate


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "web" / "public" / "data"
BOUNDARY_PATH = DATA_DIR / "shanghai-boundary.geojson"
REACH_PATH = DATA_DIR / "reach-areas.geojson"
OUTSIDE_PATH = DATA_DIR / "outside-reach-areas.geojson"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_inverse_file_is_deterministically_regenerated(tmp_path):
    regenerated = tmp_path / "outside-reach-areas.geojson"
    generate(BOUNDARY_PATH, REACH_PATH, regenerated)
    assert regenerated.read_bytes() == OUTSIDE_PATH.read_bytes()


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
    assert properties["sourceURL"].startswith("https://www.geoboundaries.org/")
    assert properties["sourceRevision"] == "9469f09"
    assert properties["license"] == "Public Domain"
    assert "geoBoundaries" in properties["attribution"]
