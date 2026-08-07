#!/usr/bin/env python3
"""Build the local high-detail Shanghai boundary from a pinned OSM snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from shapely.geometry import MultiPolygon, Polygon, mapping, shape


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data" / "shanghai-boundary-osm-r913067-v155.geojson"
DEFAULT_OCEAN = ROOT / "data" / "shanghai-ocean-openfreemap-z10-20260802.geojson"
DEFAULT_OUTPUT = ROOT / "web" / "public" / "data" / "shanghai-boundary.geojson"
RELATION_ID = 913067
RELATION_VERSION = 155
RELATION_TIMESTAMP = "2026-03-27T14:36:13Z"
RETRIEVED_DATE = "2026-08-07"
SOURCE_SHA256 = "055073cfdba9e1717cfc60626a24cfdd8f93cf0042ce173e97b8ad4b64742969"
OCEAN_SHA256 = "9465528487f7b07b1782b1e794197ce34ed1366ebb111646f31fceaf28257506"
LOCAL_COMPONENT_MAX_DISTANCE_DEGREES = 0.01
DISPLAY_SIMPLIFICATION_DEGREES = 0.00015
MINIMUM_VERTEX_COUNT = 3500


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _vertex_count(geometry: Polygon | MultiPolygon) -> int:
    polygons = geometry.geoms if isinstance(geometry, MultiPolygon) else [geometry]
    return sum(
        len(polygon.exterior.coords)
        + sum(len(interior.coords) for interior in polygon.interiors)
        for polygon in polygons
    )


def _single_polygonal_feature(
    payload: dict[str, Any],
    label: str,
) -> tuple[dict[str, Any], Polygon | MultiPolygon]:
    if payload.get("type") != "FeatureCollection":
        raise ValueError(f"{label} must be a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or len(features) != 1:
        raise ValueError(f"{label} must contain exactly one feature")
    feature = features[0]
    geometry = shape(feature.get("geometry"))
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"{label} must contain Polygon or MultiPolygon geometry")
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError(f"{label} geometry must be valid and nonempty")
    return feature, geometry


def build_boundary_collection(
    source_payload: dict[str, Any],
    ocean_payload: dict[str, Any],
) -> dict[str, Any]:
    source_feature, source_geometry = _single_polygonal_feature(
        source_payload,
        "OSM administrative source",
    )
    properties = source_feature.get("properties") or {}
    if (
        properties.get("osm_type") != "relation"
        or int(properties.get("osm_id", 0)) != RELATION_ID
    ):
        raise ValueError(f"OSM source must be relation {RELATION_ID}")

    components = (
        list(source_geometry.geoms)
        if isinstance(source_geometry, MultiPolygon)
        else [source_geometry]
    )
    components.sort(key=lambda polygon: (-polygon.area, polygon.bounds))
    main_component = components[0]
    local_components = [
        polygon
        for polygon in components
        if polygon is main_component
        or main_component.distance(polygon) <= LOCAL_COMPONENT_MAX_DISTANCE_DEGREES
    ]
    local_components.sort(key=lambda polygon: (-polygon.area, polygon.bounds))
    local_administrative: Polygon | MultiPolygon = (
        local_components[0]
        if len(local_components) == 1
        else MultiPolygon(local_components)
    )
    ocean_feature, ocean_geometry = _single_polygonal_feature(
        ocean_payload,
        "Pinned ocean mask",
    )
    ocean_properties = (
        ocean_payload.get("metadata") or ocean_feature.get("properties") or {}
    )
    if ocean_properties.get("waterClass") != "ocean":
        raise ValueError("Pinned water mask must contain only the ocean class")
    boundary = local_administrative.difference(ocean_geometry).simplify(
        DISPLAY_SIMPLIFICATION_DEGREES,
        preserve_topology=True,
    )

    if boundary.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Prepared Shanghai boundary must remain polygonal")
    if boundary.is_empty or not boundary.is_valid or boundary.area <= 0:
        raise ValueError("Prepared Shanghai boundary must be valid and nonempty")
    vertex_count = _vertex_count(boundary)
    if vertex_count < MINIMUM_VERTEX_COUNT:
        raise ValueError(
            f"Prepared Shanghai boundary is unexpectedly coarse ({vertex_count} vertices)"
        )

    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "Shanghai Municipality",
                    "nameZh": "上海市",
                    "relationID": RELATION_ID,
                    "source": "OpenStreetMap administrative boundary relation 913067",
                    "sourceURL": "https://www.openstreetmap.org/relation/913067",
                    "sourceRevision": f"relation {RELATION_ID}, version {RELATION_VERSION}",
                    "sourceTimestamp": RELATION_TIMESTAMP,
                    "sourceSnapshotSHA256": SOURCE_SHA256,
                    "oceanSource": (
                        "OpenFreeMap/OpenMapTiles ocean polygons derived from "
                        "OpenStreetMap"
                    ),
                    "oceanSourceURL": "https://openfreemap.org/",
                    "oceanTileRevision": "20260802_080001_pt",
                    "oceanTileZoom": 10,
                    "oceanSnapshotSHA256": OCEAN_SHA256,
                    "retrievedAt": RETRIEVED_DATE,
                    "license": "ODbL 1.0",
                    "licenseURL": "https://www.openstreetmap.org/copyright",
                    "attribution": "© OpenStreetMap contributors",
                    "coordinateSystem": "WGS84 longitude/latitude",
                    "geometryScope": (
                        "Shanghai-region administrative components clipped to the "
                        "OpenStreetMap ocean coastline; distant disconnected relation "
                        "components outside the local map/search area are excluded"
                    ),
                    "landFocused": True,
                    "simplificationToleranceDegrees": (
                        DISPLAY_SIMPLIFICATION_DEGREES
                    ),
                    "approximateSimplificationMeters": 17,
                    "sourceComponentCount": len(components),
                    "localAdministrativeComponentCount": len(local_components),
                    "localComponentCount": (
                        len(boundary.geoms)
                        if isinstance(boundary, MultiPolygon)
                        else 1
                    ),
                    "vertexCount": vertex_count,
                },
                "geometry": mapping(boundary),
            }
        ],
    }


def generate(source_path: Path, ocean_path: Path, output_path: Path) -> None:
    source_bytes = source_path.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    if source_hash != SOURCE_SHA256:
        raise ValueError(
            "OSM source snapshot does not match the pinned SHA-256; "
            "review and update provenance before regenerating"
        )
    ocean_bytes = ocean_path.read_bytes()
    ocean_hash = hashlib.sha256(ocean_bytes).hexdigest()
    if ocean_hash != OCEAN_SHA256:
        raise ValueError(
            "Ocean source snapshot does not match the pinned SHA-256; "
            "review and update provenance before regenerating"
        )
    result = build_boundary_collection(
        json.loads(source_bytes),
        json.loads(ocean_bytes),
    )
    serialized = json.dumps(
        result,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{serialized}\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--ocean", type=Path, default=DEFAULT_OCEAN)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    generate(args.source, args.ocean, args.output)
    print(f"Wrote high-detail Shanghai boundary to {args.output}")


if __name__ == "__main__":
    main()
