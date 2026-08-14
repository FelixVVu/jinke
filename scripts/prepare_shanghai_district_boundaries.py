"""Filter pinned geoBoundaries CHN ADM3 data to Shanghai's 16 districts."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

SOURCE_URL = (
    "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/"
    "releaseData/gbOpen/CHN/ADM3/geoBoundaries-CHN-ADM3-all.zip"
)
SOURCE_SHA256 = "b0c9e98f6f92e894bb5f65208af0ea5a9b982b020b75bc73e9151cb94da5bbe8"
OUTPUT = Path("data/economy/shanghai-district-boundaries.geojson")

DISTRICTS = {
    "62558664B30058220699094": ("宝山区", "Baoshan District"),
    "62558664B73657719469436": ("长宁区", "Changning District"),
    "62558664B47664669283193": ("崇明区", "Chongming District"),
    "62558664B92208349849242": ("奉贤区", "Fengxian District"),
    "62558664B69815106766578": ("虹口区", "Hongkou District"),
    "62558664B15620574866891": ("黄浦区", "Huangpu District"),
    "62558664B43292361433828": ("嘉定区", "Jiading District"),
    "62558664B60000117234666": ("静安区", "Jing'an District"),
    "62558664B68011662992689": ("金山区", "Jinshan District"),
    "62558664B76759395272944": ("闵行区", "Minhang District"),
    "62558664B78645465192316": ("浦东新区", "Pudong New District"),
    "62558664B37655815188257": ("普陀区", "Putuo District"),
    "62558664B37530369632792": ("青浦区", "Qingpu District"),
    "62558664B53892596451413": ("松江区", "Songjiang District"),
    "62558664B58068800824486": ("徐汇区", "Xuhui District"),
    "62558664B19255580098954": ("杨浦区", "Yangpu District"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=Path("/tmp/geoboundaries-chn-adm3.zip"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    if not args.archive.exists():
        args.archive.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(SOURCE_URL, args.archive)
    actual_sha = sha256(args.archive)
    if actual_sha != SOURCE_SHA256:
        raise RuntimeError(
            f"Pinned geoBoundaries archive checksum mismatch: {actual_sha} != {SOURCE_SHA256}"
        )

    with zipfile.ZipFile(args.archive) as archive:
        name = "geoBoundaries-CHN-ADM3.geojson"
        source = json.loads(archive.read(name))
    selected = []
    for feature in source["features"]:
        shape_id = feature["properties"].get("shapeID")
        if shape_id not in DISTRICTS:
            continue
        district, district_en = DISTRICTS[shape_id]
        if feature["properties"].get("shapeName") != district_en:
            raise RuntimeError(f"Pinned feature name changed for {shape_id}.")
        selected.append(
            {
                "type": "Feature",
                "properties": {
                    "district": district,
                    "district_en": district_en,
                    "source_shape_id": shape_id,
                },
                "geometry": feature["geometry"],
            }
        )
    selected.sort(key=lambda feature: feature["properties"]["district"])
    if len(selected) != 16:
        found = {feature["properties"]["source_shape_id"] for feature in selected}
        raise RuntimeError(f"Expected 16 districts; missing IDs: {sorted(set(DISTRICTS) - found)}")

    output = {
        "type": "FeatureCollection",
        "name": "Shanghai districts (16), pinned from geoBoundaries gbOpen CHN ADM3",
        "metadata": {
            "source_url": SOURCE_URL,
            "source_archive_sha256": SOURCE_SHA256,
            "source_commit": "9469f09",
            "boundary_id": "CHN-ADM3-62558664",
            "boundary_year": "2017",
            "build_date": "2023-12-12",
            "source": "Lee Beryman, OpenStreetMap",
            "license": "Open Data Commons Open Database License 1.0",
            "license_url": "https://www.openstreetmap.org/copyright",
            "derivation": "Exact feature-ID filter; source geometry is not simplified.",
        },
        "features": selected,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Wrote {len(selected)} districts to {args.output}")


if __name__ == "__main__":
    main()
