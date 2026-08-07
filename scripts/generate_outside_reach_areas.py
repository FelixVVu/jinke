#!/usr/bin/env python3
"""Build Shanghai-only inverse reach polygons from committed static data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, mapping, shape
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "web" / "public" / "data"
DEFAULT_BOUNDARY = DATA_DIR / "shanghai-boundary.geojson"
DEFAULT_REACH = DATA_DIR / "reach-areas.geojson"
DEFAULT_OUTPUT = DATA_DIR / "outside-reach-areas.geojson"
LIMITS = (10, 20, 30, 40, 50)
AREA_TOLERANCE = 1e-12


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _features(payload: dict[str, Any], label: str) -> list[dict[str, Any]]:
    if payload.get("type") != "FeatureCollection":
        raise ValueError(f"{label} must be a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError(f"{label} must contain at least one feature")
    return features


def _valid_polygon(feature: dict[str, Any], label: str) -> Polygon | MultiPolygon:
    geometry = shape(feature.get("geometry"))
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"{label} must be Polygon or MultiPolygon")
    if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
        raise ValueError(f"{label} must be valid and nonempty")
    return geometry


def _polygonal_part(geometry: Any, label: str) -> Polygon | MultiPolygon:
    if isinstance(geometry, (Polygon, MultiPolygon)):
        result = geometry
    elif isinstance(geometry, GeometryCollection):
        polygons = [
            part
            for part in geometry.geoms
            if isinstance(part, (Polygon, MultiPolygon)) and not part.is_empty
        ]
        result = unary_union(polygons)
    else:
        raise ValueError(f"{label} produced {geometry.geom_type}, not polygon data")

    if result.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"{label} did not produce Polygon or MultiPolygon")
    if result.is_empty or not result.is_valid or result.area <= 0:
        raise ValueError(f"{label} produced invalid or empty geometry")
    return result


def build_inverse_collection(
    boundary_payload: dict[str, Any],
    reach_payload: dict[str, Any],
) -> dict[str, Any]:
    boundary_features = _features(boundary_payload, "Shanghai boundary")
    boundary_properties = boundary_features[0].get("properties") or {}
    boundary = _polygonal_part(
        unary_union(
            [
                _valid_polygon(feature, f"Shanghai boundary feature {index}")
                for index, feature in enumerate(boundary_features)
            ]
        ),
        "Shanghai boundary union",
    )

    reach_features = _features(reach_payload, "Reach areas")
    if len(reach_features) != len(LIMITS):
        raise ValueError("Reach areas must contain exactly five features")

    reach_by_limit: dict[int, Polygon | MultiPolygon] = {}
    for index, feature in enumerate(reach_features):
        try:
            limit = int(feature["properties"]["limit"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Reach feature {index} has no valid limit") from exc
        if limit in reach_by_limit:
            raise ValueError(f"Reach areas contain duplicate limit {limit}")
        reach_by_limit[limit] = _valid_polygon(
            feature,
            f"Reach feature for {limit} minutes",
        )

    if set(reach_by_limit) != set(LIMITS):
        raise ValueError(f"Reach limits must be exactly {list(LIMITS)}")

    output_features = []
    for limit in LIMITS:
        reach = reach_by_limit[limit]
        outside = _polygonal_part(
            boundary.difference(reach),
            f"Outside geometry for {limit} minutes",
        )

        if not boundary.covers(outside):
            raise ValueError(f"Outside geometry for {limit} escapes Shanghai")
        overlap_area = outside.intersection(reach).area
        if overlap_area > AREA_TOLERANCE:
            raise ValueError(
                f"Outside geometry for {limit} overlaps reach area by {overlap_area}"
            )

        output_features.append(
            {
                "type": "Feature",
                "properties": {
                    "boundary": "Shanghai Municipality",
                    "limit": limit,
                    "mode": "outside-reach",
                },
                "geometry": mapping(outside),
            }
        )

    return {
        "type": "FeatureCollection",
        "metadata": {
            "boundarySource": boundary_properties.get("source"),
            "boundarySourceURL": boundary_properties.get("sourceURL"),
            "license": boundary_properties.get("license"),
            "licenseURL": boundary_properties.get("licenseURL"),
            "attribution": boundary_properties.get("attribution"),
        },
        "features": output_features,
    }


def generate(boundary_path: Path, reach_path: Path, output_path: Path) -> None:
    result = build_inverse_collection(
        _read_json(boundary_path),
        _read_json(reach_path),
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
    parser.add_argument("--boundary", type=Path, default=DEFAULT_BOUNDARY)
    parser.add_argument("--reach", type=Path, default=DEFAULT_REACH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    generate(args.boundary, args.reach, args.output)
    print(f"Wrote five Shanghai-only inverse features to {args.output}")


if __name__ == "__main__":
    main()
