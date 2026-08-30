"""Extend the reviewed office-employment allocation to all Shanghai districts.

The committed eight-district grids are immutable inputs to this extension.  Only
the eight previously unavailable districts are gridded and allocated here; their
cells are then appended to the committed rows.  Official Fifth Economic Census
fine totals are used where published.  Minhang and Jinshan remain clearly
labelled district-level fallbacks because compatible fine tables were not found.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyogrio
import shapely

from employment_pipeline.config import ANALYSIS_CRS
from employment_pipeline.grid import (
    POI_COLUMNS,
    add_jrc_nonresidential_volume,
    classify_workplace_category,
)
from office_employment_pipeline.control_reconciliation import (
    CORE_CODES,
    OFFICE_CODES,
    SCENARIOS,
    SELECTED_72_CODES,
    construct_control_industry_matrix,
)
from office_employment_pipeline.district_controls import (
    CORE_EMPLOYMENT,
    CORE_PLUS_EMPLOYMENT,
)
from office_employment_pipeline.source_audit import EMPLOYMENT_UNIVERSE, REFERENCE_DATE
from office_employment_pipeline.spatial import (
    FUNCTION_COLUMNS,
    PRIORITY_DISTRICTS,
    WEIGHTING_SCENARIOS,
    _aggregate_to_physical_cells,
    _control_diagnostic_records,
    _grid_metadata,
    _matrix_totals,
    allocate_integer_control_matrix,
    attach_building_evidence,
    build_control_industry_weights,
    extract_building_evidence,
    sha256_file,
)


GRID_SIZE_METRES = 100
ALL_DISTRICTS = (
    "黄浦区",
    "徐汇区",
    "长宁区",
    "静安区",
    "普陀区",
    "虹口区",
    "杨浦区",
    "闵行区",
    "宝山区",
    "嘉定区",
    "浦东新区",
    "金山区",
    "松江区",
    "青浦区",
    "奉贤区",
    "崇明区",
)
OUTER_DISTRICTS = tuple(
    district for district in ALL_DISTRICTS if district not in PRIORITY_DISTRICTS
)

OSM_SOURCE_URL = "https://download.openstreetmap.fr/extracts/asia/china/shanghai.osm.pbf"
OSM_SNAPSHOT_DATE = "2026-08-30"
OSM_SHA256 = "0b307452336c5984f1a894cc514e5d67663cee8d5eca55c0b1b4cb1505e44319"
OSM_LICENSE = "OpenStreetMap contributors, Open Database License 1.0"
JRC_SHA256 = "bb7e081ca0f2f2d4fc89892158efbb2dc566711108df097e35fdc874dfd2d607"
OVERTURE_RELEASE = "2026-07-22.0"
OVERTURE_PART_SHA256 = "8c2c2432eccdefa5c65882d255112fa2e6dcf54bdaa23c108cf118eb56e5be06"
OVERTURE_CLIPPED_ROWS = 20_738
DISTRICT_BOUNDARY_SHA256 = "279b11087234db63728b35c9970174f7f536505763401127e4eed3b7e0e7340e"
PRIORITY_BASELINE_FILE_SHA256 = {
    "core": "13963900c459f4ff12672c2af52cff66fc4da4f58f68c321ec0bddcfeafb0af0",
    "base": "433acd3ef11fc7570e0e06d5a0fa2da49fecedc1cf65a6b120b3087197ae6abb",
    "composition": "76239b9e0786f86ff0b0e3f6b9e2c0decf2a23b7c7ac29a2ede9881c50ae69af",
    "weighting": "c09fbfd7c3e3b8d4cd8913eecf79f7456dc90ec2ba394134bfff1cfa966027ce",
}

SOURCE_URLS = {
    "宝山区": "https://xxgk.shbsq.gov.cn/article.html?infoid=32cde990-f9fa-496d-8a12-54b34e699b42",
    "嘉定区": "https://www.jiading.gov.cn/upload/tongji/ContentManage/Article/File/8880f9029c32450584bcba4b0f341050.pdf",
    "松江区": "https://www.songjiang.gov.cn/shsj_main/6fe2fe14-800b-4242-b74b-abdaba8eecc5/8888bc4a-2f90-4d61-a978-35850f81cdef/上海市松江区第五次经济普查主要数据公报.pdf",
    "青浦区": "https://www.shqp.gov.cn/stat/stat/upload/202511/1112_120139_477.pdf",
    "奉贤区": "https://www.fengxian.gov.cn/tzgg/20250801/93379.html",
    "崇明区": "https://www.shcm.gov.cn/shcm/ecef415d-3c63-47da-bfd3-311441208d44/87e9346e-af5c-4ac3-acbd-902d9d8f0cf7/上海市崇明区第五次全国经济普查主要数据公报（第一号）.pdf",
    "闵行区": "https://tjj.sh.gov.cn/tjnj/jjpcnj2023/zk/html/A1-02.xls",
    "金山区": "https://tjj.sh.gov.cn/tjnj/jjpcnj2023/zk/html/A1-02.xls",
}

# Each tuple is (published control name, published value).  Exact tables publish
# people; Baoshan publishes 0.01 wan persons; Jiading publishes percentage shares.
OFFICIAL_ROWS: dict[str, list[tuple[str, float]]] = {
    "宝山区": [
        ("友谊路街道", 4.78), ("吴淞街道", 3.50), ("张庙街道", 1.56),
        ("罗店镇", 4.95), ("大场镇", 8.32), ("杨行镇", 15.01),
        ("月浦镇", 6.17), ("罗泾镇", 1.96), ("顾村镇", 7.81),
        ("高境镇", 10.22), ("庙行镇", 2.89), ("淞南镇", 3.42),
        ("宝山高新区", 5.54),
    ],
    "嘉定区": [
        ("安亭镇", 18.4), ("江桥镇", 15.0), ("马陆镇", 14.9),
        ("南翔镇", 14.4), ("嘉定工业区", 8.9), ("外冈镇", 6.2),
        ("徐行镇", 5.7), ("真新街道", 5.3), ("菊园新区", 4.2),
        ("华亭镇", 2.4), ("新成路街道", 2.3), ("嘉定镇街道", 2.2),
    ],
    "松江区": [
        ("岳阳街道", 35808), ("永丰街道", 33857), ("方松街道", 35607),
        ("中山街道", 82534), ("广富林街道", 20170), ("九里亭街道", 15407),
        ("泗泾镇", 51348), ("佘山镇", 35298), ("车墩镇", 62668),
        ("新桥镇", 91342), ("洞泾镇", 39075), ("九亭镇", 84087),
        ("泖港镇", 17633), ("石湖荡镇", 31171), ("新浜镇", 12597),
        ("叶榭镇", 21982), ("小昆山镇", 29215), ("松江经济技术开发区", 148013),
    ],
    "青浦区": [
        ("赵巷镇", 24884), ("徐泾镇", 92417), ("华新镇", 76670),
        ("重固镇", 22117), ("白鹤镇", 19514), ("朱家角镇", 34734),
        ("练塘镇", 21255), ("金泽镇", 28099), ("夏阳街道", 46519),
        ("盈浦街道", 27515), ("香花桥街道", 151474),
    ],
    "奉贤区": [
        ("南桥镇", 108793), ("奉城镇", 47863), ("庄行镇", 33026),
        ("金汇镇", 54973), ("四团镇", 32678), ("青村镇", 48451),
        ("柘林镇", 28160), ("海湾镇", 8812), ("西渡街道", 27641),
        ("头桥街道", 9039), ("海湾旅游区", 7087), ("工业综合开发区", 77502),
        ("杭州湾开发区", 30548), ("东方美谷集团", 35719),
        ("临港奉贤分区", 17017), ("市化工区（奉贤）", 11740),
    ],
    "崇明区": [
        ("城桥镇", 46830), ("堡镇", 10443), ("新河镇", 6444),
        ("庙镇", 4877), ("竖新镇", 5472), ("向化镇", 5672),
        ("三星镇", 2400), ("港沿镇", 4303), ("中兴镇", 3407),
        ("陈家镇", 12059), ("绿华镇", 1186), ("港西镇", 3135),
        ("建设镇", 4314), ("新海镇", 2033), ("东平镇", 2640),
        ("长兴镇", 32990), ("新村乡", 2968), ("横沙乡", 3003),
        ("前卫农场", 791), ("东平林场", 633), ("上实现代农业园区", 428),
    ],
}

DISTRICT_TOTALS = {
    "闵行区": 1_278_262,
    "宝山区": 766_004,
    "嘉定区": 873_958,
    "金山区": 393_752,
    "松江区": 852_240,
    "青浦区": 549_805,
    "奉贤区": 583_748,
    "崇明区": 161_453,
}

RESIDUALS = {
    "宝山区": (4_784, "finance", "geographic rows exclude finance; rounded rows reconciled to district less official J"),
    "嘉定区": (9_871, "finance", "published geographic shares exclude finance"),
    "松江区": (4_428, "unsubdivided_publication_difference", "published row sum is below the table total; no row-level reason is stated"),
    "青浦区": (4_607, "finance", "geographic rows exclude finance"),
    "奉贤区": (4_699, "directly_managed_finance", "geographic rows exclude directly managed finance"),
    "崇明区": (5_425, "finance", "geographic rows exclude finance"),
}

OSM_NAME_ALIASES = {"菊园新区": "菊园街道"}
DISTRICT_OVERLAY_CONTROLS = {
    "宝山高新区",
    "嘉定工业区",
    "松江经济技术开发区",
    "头桥街道",
    "工业综合开发区",
    "杭州湾开发区",
    "东方美谷集团",
    "临港奉贤分区",
    "市化工区（奉贤）",
    "前卫农场",
    "东平林场",
    "上实现代农业园区",
}
FUNCTIONAL_CONTROLS = {
    "宝山高新区",
    "嘉定工业区",
    "松江经济技术开发区",
    "海湾旅游区",
    "工业综合开发区",
    "杭州湾开发区",
    "东方美谷集团",
    "临港奉贤分区",
    "市化工区（奉贤）",
    "前卫农场",
    "东平林场",
    "上实现代农业园区",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _proportional_integer(values: np.ndarray, total: int) -> np.ndarray:
    raw = values.astype(float) / float(values.sum()) * int(total)
    rounded = np.floor(raw).astype(np.int64)
    remainder = int(total) - int(rounded.sum())
    order = np.lexsort((np.arange(len(raw)), -(raw - rounded)))
    rounded[order[:remainder]] += 1
    if int(rounded.sum()) != int(total):
        raise RuntimeError("Proportional controlled rounding failed.")
    return rounded


def build_outer_control_ledger() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return reconciled outer-district fine controls and residual strata."""

    records: list[dict[str, Any]] = []
    for district in OUTER_DISTRICTS:
        if district in {"闵行区", "金山区"}:
            records.append(
                {
                    "district": district,
                    "accounting_stratum_id": f"{district}-district-fallback",
                    "official_control_name_2023": f"{district} district total",
                    "control_type": "district_fallback",
                    "employment_published": DISTRICT_TOTALS[district],
                    "employment_reconciled": DISTRICT_TOTALS[district],
                    "rounding_lower": DISTRICT_TOTALS[district],
                    "rounding_upper": DISTRICT_TOTALS[district],
                    "publication_unit": "people",
                    "row_is_official_fine_control": False,
                    "fine_table_status": "no compatible Fifth Economic Census fine table located",
                    "source_url": SOURCE_URLS[district],
                    "source_table": "Shanghai district total A1-02",
                    "boundary_support": "district_fallback",
                    "osm_match_name": "",
                    "geometry_is_approximate": True,
                }
            )
            continue

        source_rows = OFFICIAL_ROWS[district]
        residual = RESIDUALS[district][0]
        fine_target = DISTRICT_TOTALS[district] - residual
        if district == "宝山区":
            published = np.array([value * 10_000 for _, value in source_rows])
            reconciled = _proportional_integer(published, fine_target)
            lower = np.floor(published - 50).astype(int)
            upper = np.ceil(published + 50).astype(int)
            unit = "10,000 persons, two decimals"
            source_table = "Table 1-5"
            status = "official rounded counts; constrained within published rounding intervals"
        elif district == "嘉定区":
            published = np.array([value for _, value in source_rows])
            reconciled = _proportional_integer(published, fine_target)
            lower = np.floor(np.maximum(0, published - 0.05) / 100 * fine_target).astype(int)
            upper = np.ceil((published + 0.05) / 100 * fine_target).astype(int)
            unit = "percentage of geographically allocated employment, one decimal"
            source_table = "geographic employment infographic"
            status = "official rounded shares; maximum-entropy proportional counts constrained to fine subtotal"
        else:
            published = np.array([value for _, value in source_rows], dtype=float)
            reconciled = published.astype(np.int64)
            lower = reconciled.copy()
            upper = reconciled.copy()
            unit = "people"
            source_table = "geographic employment table"
            status = "official exact count"
        if int(reconciled.sum()) != fine_target:
            raise RuntimeError(f"Fine controls do not reconcile for {district}.")

        for index, ((name, published_value), count) in enumerate(
            zip(source_rows, reconciled, strict=True), start=1
        ):
            control_type = (
                "functional_zone"
                if name in FUNCTIONAL_CONTROLS
                else ("street" if "街道" in name else ("township" if name.endswith("乡") else "town"))
            )
            support = "district_overlay" if name in DISTRICT_OVERLAY_CONTROLS else "osm_relation"
            records.append(
                {
                    "district": district,
                    "accounting_stratum_id": f"outer-{district}-{index:02d}",
                    "official_control_name_2023": name,
                    "control_type": control_type,
                    "employment_published": published_value,
                    "employment_reconciled": int(count),
                    "rounding_lower": int(lower[index - 1]),
                    "rounding_upper": int(upper[index - 1]),
                    "publication_unit": unit,
                    "row_is_official_fine_control": True,
                    "fine_table_status": status,
                    "source_url": SOURCE_URLS[district],
                    "source_table": source_table,
                    "boundary_support": support,
                    "osm_match_name": OSM_NAME_ALIASES.get(name, name) if support == "osm_relation" else "",
                    "geometry_is_approximate": True,
                }
            )

    controls = pd.DataFrame(records)
    residual_records = []
    for district, (employment, residual_class, reason) in RESIDUALS.items():
        residual_records.append(
            {
                "district": district,
                "residual_id": f"outer-{district}-residual",
                "residual_class": residual_class,
                "employment_nominal": employment,
                "rounding_lower": employment,
                "rounding_upper": employment,
                "reason": reason,
                "central_rule": "district-wide workplace-evidence overlay",
                "central_is_spatially_allocated": True,
                "employment_universe": EMPLOYMENT_UNIVERSE,
                "reference_date": REFERENCE_DATE,
            }
        )
    residuals = pd.DataFrame(residual_records)
    observed = controls.groupby("district")["employment_reconciled"].sum().add(
        residuals.groupby("district")["employment_nominal"].sum(), fill_value=0
    )
    if observed.astype(int).to_dict() != DISTRICT_TOTALS:
        raise RuntimeError(f"Outer-district control ledger does not reconcile: {observed}")
    return controls, residuals


def load_outer_districts(path: Path) -> gpd.GeoDataFrame:
    if _sha256(path) != DISTRICT_BOUNDARY_SHA256:
        raise RuntimeError("Shanghai district boundary source changed.")
    districts = gpd.read_file(path).to_crs(ANALYSIS_CRS)
    districts = districts.loc[districts["district"].isin(OUTER_DISTRICTS)].copy()
    districts["geometry"] = shapely.make_valid(districts.geometry.array)
    if set(districts["district"]) != set(OUTER_DISTRICTS):
        raise RuntimeError("Outer district boundary coverage is incomplete.")
    if districts.geometry.is_empty.any() or not districts.geometry.is_valid.all():
        raise RuntimeError("Outer district boundaries are invalid or empty.")
    order = {district: index for index, district in enumerate(OUTER_DISTRICTS)}
    return districts.assign(_order=districts["district"].map(order)).sort_values("_order").drop(columns="_order").reset_index(drop=True)


def attach_outer_control_geometry(
    controls: pd.DataFrame,
    districts: gpd.GeoDataFrame,
    osm_pbf_path: Path,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    if _sha256(osm_pbf_path) != OSM_SHA256:
        raise RuntimeError("Outer-district OSM snapshot changed.")
    admin = pyogrio.read_dataframe(
        osm_pbf_path,
        layer="multipolygons",
        columns=["osm_id", "name", "admin_level", "boundary"],
        where="boundary = 'administrative' AND (admin_level = '8' OR admin_level = '9')",
    )
    admin = admin.loc[admin.geometry.notna()].copy()
    admin["geometry"] = shapely.make_valid(admin.geometry.array)
    admin = admin.loc[~admin.geometry.is_empty].to_crs(ANALYSIS_CRS)
    district_geometries = districts.set_index("district")["geometry"]
    geometry: list[Any] = []
    manifest: list[dict[str, Any]] = []
    for row in controls.itertuples(index=False):
        parent = district_geometries.loc[row.district]
        if row.boundary_support == "osm_relation":
            matches = admin.loc[admin["name"].eq(row.osm_match_name)].copy()
            matches["parent_overlap_m2"] = matches.geometry.intersection(parent).area
            matches = matches.loc[matches["parent_overlap_m2"] > 1.0]
            if len(matches) != 1:
                raise RuntimeError(
                    f"Expected one exact OSM boundary for {row.district}/{row.official_control_name_2023}; found {len(matches)}."
                )
            match = matches.iloc[0]
            support_geometry = shapely.intersection(match.geometry, parent)
            relation_id = str(match.osm_id)
            source_name = str(match["name"])
            source = "OpenStreetMap exact-name administrative relation clipped to parent district"
        else:
            support_geometry = parent
            relation_id = ""
            source_name = ""
            source = "approximate parent-district overlay; no reusable matching fine polygon"
        if support_geometry.is_empty or not support_geometry.is_valid:
            raise RuntimeError(f"Invalid support geometry for {row.accounting_stratum_id}.")
        geometry.append(support_geometry)
        manifest.append(
            {
                "district": row.district,
                "accounting_stratum_id": row.accounting_stratum_id,
                "control_name": row.official_control_name_2023,
                "boundary_support": row.boundary_support,
                "boundary_source": source,
                "osm_relation_id": relation_id,
                "osm_relation_name": source_name,
                "osm_snapshot_date": OSM_SNAPSHOT_DATE if relation_id else "",
                "geometry_is_approximate": True,
                "area_km2": float(shapely.area(support_geometry) / 1e6),
            }
        )
    result = gpd.GeoDataFrame(controls.copy(), geometry=geometry, crs=ANALYSIS_CRS)
    return result, pd.DataFrame(manifest)


def build_outer_cell_lattice(districts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    frames: list[gpd.GeoDataFrame] = []
    size = GRID_SIZE_METRES
    for district_row in districts[["district", "geometry"]].itertuples(index=False):
        geometry = district_row.geometry
        minx, miny, maxx, maxy = geometry.bounds
        min_col, max_col = math.floor(minx / size), math.ceil(maxx / size) - 1
        min_row, max_row = math.floor(miny / size), math.ceil(maxy / size) - 1
        cols, rows = np.meshgrid(
            np.arange(min_col, max_col + 1, dtype=np.int32),
            np.arange(min_row, max_row + 1, dtype=np.int32),
        )
        cols, rows = cols.ravel(), rows.ravel()
        squares = shapely.box(cols * size, rows * size, (cols + 1) * size, (rows + 1) * size)
        keep = shapely.intersects(squares, geometry)
        clipped = shapely.intersection(squares[keep], geometry)
        areas = shapely.area(clipped)
        positive = areas > 1e-8
        cols, rows, clipped, areas = cols[keep][positive], rows[keep][positive], clipped[positive], areas[positive]
        frames.append(
            gpd.GeoDataFrame(
                {
                    "district": district_row.district,
                    "grid_col": cols,
                    "grid_row": rows,
                    "center_x": (cols.astype(float) + 0.5) * size,
                    "center_y": (rows.astype(float) + 0.5) * size,
                    "cell_area_m2": areas,
                    "area_fraction": areas / float(size * size),
                },
                geometry=clipped,
                crs=ANALYSIS_CRS,
            )
        )
    grid = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs=ANALYSIS_CRS)
    grid["cell_id"] = grid["district"] + ":" + grid["grid_row"].astype(str) + ":" + grid["grid_col"].astype(str)
    if grid["cell_id"].duplicated().any() or grid.geometry.is_empty.any() or not grid.geometry.is_valid.all():
        raise RuntimeError("Outer physical cell lattice is invalid.")
    order = {district: index for index, district in enumerate(OUTER_DISTRICTS)}
    grid["_order"] = grid["district"].map(order)
    return grid.sort_values(["_order", "grid_row", "grid_col"], kind="mergesort").drop(columns="_order").reset_index(drop=True)


def clip_overture_places(source_path: Path, district_path: Path, destination: Path) -> Path:
    if _sha256(source_path) != OVERTURE_PART_SHA256:
        raise RuntimeError("Overture source partition changed.")
    districts = gpd.read_file(district_path).to_crs("EPSG:4326")
    west, south, east, north = (float(value) for value in districts.total_bounds)
    expression = (
        (pc.field("bbox", "xmin") < east)
        & (pc.field("bbox", "xmax") > west)
        & (pc.field("bbox", "ymin") < north)
        & (pc.field("bbox", "ymax") > south)
    )
    table = ds.dataset(source_path, format="parquet").to_table(filter=expression)
    frame = table.to_pandas()
    frame = gpd.GeoDataFrame(frame, geometry=shapely.from_wkb(frame.pop("geometry")), crs="EPSG:4326")
    frame = frame.loc[frame.geometry.intersects(districts.geometry.union_all())].copy()
    if len(frame) != OVERTURE_CLIPPED_ROWS:
        raise RuntimeError(f"Expected {OVERTURE_CLIPPED_ROWS} Shanghai places; found {len(frame)}.")
    frame.to_parquet(destination, index=False, compression="zstd")
    return destination


def _primary_category(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("primary") or "").strip().lower()
    if hasattr(value, "as_py"):
        return _primary_category(value.as_py())
    return ""


def add_overture_to_physical_cells(
    cells: gpd.GeoDataFrame,
    districts: gpd.GeoDataFrame,
    places_path: Path,
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    places = gpd.read_parquet(places_path)
    basic = places["categories"].map(_primary_category)
    categories = basic.map(classify_workplace_category)
    confidence = pd.to_numeric(places["confidence"], errors="coerce").fillna(0.5).clip(0, 1)
    selected = places[["id", "geometry"]].copy()
    selected["workplace_category"] = categories
    selected["confidence"] = confidence
    selected = selected.loc[selected["workplace_category"].notna()].to_crs(ANALYSIS_CRS)
    joined = gpd.sjoin(selected, districts[["district", "geometry"]], how="inner", predicate="within").drop(columns="index_right")
    joined = joined.drop_duplicates("id", keep="first")
    joined["grid_col"] = np.floor(joined.geometry.x / GRID_SIZE_METRES).astype(np.int32)
    joined["grid_row"] = np.floor(joined.geometry.y / GRID_SIZE_METRES).astype(np.int32)
    grouped = joined.groupby(["district", "grid_row", "grid_col", "workplace_category"])["confidence"].sum().unstack(fill_value=0.0).reset_index()
    grouped = grouped.rename(columns={category: f"poi_{category}" for category in grouped.columns if category not in {"district", "grid_row", "grid_col"}})
    output = cells.merge(grouped, on=["district", "grid_row", "grid_col"], how="left", validate="one_to_one")
    output = gpd.GeoDataFrame(output, geometry="geometry", crs=cells.crs)
    for column in POI_COLUMNS:
        if column not in output:
            output[column] = 0.0
        output[column] = output[column].fillna(0.0).astype(float)
    return output, {
        "input_places": int(len(places)),
        "outer_workplace_relevant_places": int(len(joined)),
        "outer_cells_with_workplace_places": int((output[list(POI_COLUMNS)].sum(axis=1) > 0).sum()),
        "overture_release": OVERTURE_RELEASE,
        "clipped_places_sha256": _sha256(places_path),
    }


def build_outer_support(
    cells: gpd.GeoDataFrame,
    controls: gpd.GeoDataFrame,
    residuals: pd.DataFrame,
    districts: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    evidence_columns = [
        "jrc_nres_volume_m3",
        *POI_COLUMNS,
        *[f"osm_{column}_footprint_m2" for column in FUNCTION_COLUMNS],
        "osm_office_establishment_count",
    ]
    frames: list[pd.DataFrame] = []
    for control in controls.itertuples(index=False):
        candidate_index = cells.sindex.query(control.geometry, predicate="intersects")
        candidates = cells.iloc[candidate_index].copy()
        areas = shapely.area(shapely.intersection(candidates.geometry.array, control.geometry))
        candidates = candidates.loc[areas > 1e-8].copy()
        areas = areas[areas > 1e-8]
        candidates["physical_cell_id"] = candidates["cell_id"]
        candidates["physical_cell_area_m2"] = candidates["cell_area_m2"]
        candidates["support_cell_area_m2"] = areas
        candidates["support_area_share_of_physical_cell"] = areas / candidates["cell_area_m2"]
        for column in evidence_columns:
            candidates[column] = candidates[column].astype(float) * candidates["support_area_share_of_physical_cell"]
        candidates["accounting_stratum_id"] = str(control.accounting_stratum_id)
        candidates["control_name"] = control.official_control_name_2023
        candidates["control_type"] = control.control_type
        candidates["official_control_total_employment"] = int(control.employment_reconciled)
        candidates["support_kind"] = control.boundary_support
        candidates["restricted_geometry"] = False
        frames.append(candidates)
    for residual in residuals.itertuples(index=False):
        candidates = cells.loc[cells["district"].eq(residual.district)].copy()
        candidates["physical_cell_id"] = candidates["cell_id"]
        candidates["physical_cell_area_m2"] = candidates["cell_area_m2"]
        candidates["support_cell_area_m2"] = candidates["cell_area_m2"]
        candidates["support_area_share_of_physical_cell"] = 1.0
        candidates["accounting_stratum_id"] = str(residual.residual_id)
        candidates["control_name"] = str(residual.residual_id)
        candidates["control_type"] = "residual"
        candidates["official_control_total_employment"] = int(residual.employment_nominal)
        candidates["support_kind"] = "district_residual_overlay"
        candidates["restricted_geometry"] = False
        frames.append(candidates)
    columns = [
        "district", "physical_cell_id", "grid_row", "grid_col", "accounting_stratum_id",
        "control_name", "control_type", "official_control_total_employment", "support_kind",
        "restricted_geometry", "support_cell_area_m2", "physical_cell_area_m2",
        "support_area_share_of_physical_cell", *evidence_columns,
    ]
    support = pd.concat([frame[columns] for frame in frames], ignore_index=True)
    support["accounting_stratum_id"] = support["accounting_stratum_id"].astype(str)
    support["support_cell_id"] = support["accounting_stratum_id"] + ":" + support["physical_cell_id"]
    if support["support_cell_id"].duplicated().any():
        raise RuntimeError("Outer support has duplicate control/cell rows.")
    return support, {
        "outer_support_record_count": int(len(support)),
        "outer_accounting_control_count": int(support["accounting_stratum_id"].nunique()),
        "outer_controls_with_district_overlay": int(controls["boundary_support"].isin(["district_overlay", "district_fallback"]).sum()),
    }


def allocate_outer_grids(
    cells: gpd.GeoDataFrame,
    support: pd.DataFrame,
    matrix: pd.DataFrame,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame, gpd.GeoDataFrame, pd.DataFrame]:
    diagnostics: list[dict[str, Any]] = []
    cache: dict[tuple[str, str], tuple[pd.Series, dict[str, dict[str, Any]]]] = {}

    def weights_for(weighting: str, code: str):
        key = (weighting, code)
        if key not in cache:
            cache[key] = build_control_industry_weights(support, code, WEIGHTING_SCENARIOS[weighting]["shares"])
        return cache[key]

    def allocate(scenario: str, weighting: str, code: str) -> pd.Series:
        weights, realized = weights_for(weighting, code)
        totals = _matrix_totals(matrix, scenario, code)
        values = allocate_integer_control_matrix(support, weights, totals)
        diagnostics.extend(_control_diagnostic_records(support, values, weights, realized, totals, industry_code=code, scenario=scenario, weighting_scenario=weighting))
        return values

    base_support = {code: allocate("base", "base", code) for code in OFFICE_CODES}
    base_physical = _aggregate_to_physical_cells(cells, support, {f"cell_employment_{code}": value for code, value in base_support.items()})
    core = _grid_metadata(base_physical)
    for code in CORE_CODES:
        core[f"cell_employment_{code}"] = base_physical[f"cell_employment_{code}"]
    core["cell_employment_core"] = core[[f"cell_employment_{code}" for code in CORE_CODES]].sum(axis=1)
    core["employment_definition"] = "Core office-oriented employment: I + J + M"
    core["control_grain"] = "official fine control where published; disclosed district fallback otherwise"
    core["weighting_scenario"] = "base"
    core["geometry_is_approximate"] = True
    core["boundary_source"] = "OSM 2026-08-30 exact-name relations or disclosed district overlay"
    core["employment_universe"] = EMPLOYMENT_UNIVERSE
    core["reference_date"] = REFERENCE_DATE
    core["reach_intersection_calculated"] = False

    base = _grid_metadata(base_physical)
    base["cell_employment_core"] = core["cell_employment_core"]
    for code in SELECTED_72_CODES:
        base[f"cell_employment_{code}"] = base_physical[f"cell_employment_{code}"]
    base["cell_employment_selected_72_base"] = base[[f"cell_employment_{code}" for code in SELECTED_72_CODES]].sum(axis=1)
    base["cell_employment_core_plus_base"] = base["cell_employment_core"] + base["cell_employment_selected_72_base"]
    base["employment_definition"] = "Core+ Base: Core I+J+M plus selected 721/723/724/725"
    base["control_grain"] = core["control_grain"]
    base["weighting_scenario"] = "base"
    base["core_is_hard_control"] = True
    base["selected_72_district_composition_is_modelled"] = True
    base["geometry_is_approximate"] = True
    base["boundary_source"] = core["boundary_source"]
    base["employment_universe"] = EMPLOYMENT_UNIVERSE
    base["reference_date"] = REFERENCE_DATE
    base["reach_intersection_calculated"] = False

    composition = _grid_metadata(base_physical)
    composition["cell_employment_core"] = core["cell_employment_core"]
    for scenario in SCENARIOS:
        for code in SELECTED_72_CODES:
            support_values = base_support[code] if scenario == "base" else allocate(scenario, "base", code)
            composition[f"cell_employment_{code}_{scenario}"] = _aggregate_to_physical_cells(cells, support, {"value": support_values})["value"]
        composition[f"cell_employment_selected_72_{scenario}"] = composition[[f"cell_employment_{code}_{scenario}" for code in SELECTED_72_CODES]].sum(axis=1)
        composition[f"cell_employment_core_plus_{scenario}"] = composition["cell_employment_core"] + composition[f"cell_employment_selected_72_{scenario}"]
    composition["cell_employment_core_plus_low_minus_base"] = composition["cell_employment_core_plus_low_office_intensity"] - composition["cell_employment_core_plus_base"]
    composition["cell_employment_core_plus_high_minus_base"] = composition["cell_employment_core_plus_high_office_intensity"] - composition["cell_employment_core_plus_base"]
    composition["core_is_hard_control"] = True
    composition["selected_72_district_composition_is_modelled"] = True
    composition["control_grain"] = core["control_grain"]
    composition["geometry_is_approximate"] = True
    composition["boundary_source"] = core["boundary_source"]
    composition["employment_universe"] = EMPLOYMENT_UNIVERSE
    composition["reference_date"] = REFERENCE_DATE
    composition["reach_intersection_calculated"] = False

    weighting = _grid_metadata(base_physical)
    for weighting_scenario in WEIGHTING_SCENARIOS:
        if weighting_scenario == "base":
            physical = base_physical
        else:
            allocations = {code: allocate("base", weighting_scenario, code) for code in OFFICE_CODES}
            physical = _aggregate_to_physical_cells(cells, support, {f"cell_employment_{code}": value for code, value in allocations.items()})
        weighting[f"cell_employment_core_plus_{weighting_scenario}"] = physical[[f"cell_employment_{code}" for code in OFFICE_CODES]].sum(axis=1)
    weighting["cell_employment_building_volume_dominant_minus_base"] = weighting["cell_employment_core_plus_building_volume_dominant"] - weighting["cell_employment_core_plus_base"]
    weighting["cell_employment_workplace_evidence_emphasis_minus_base"] = weighting["cell_employment_core_plus_workplace_evidence_emphasis"] - weighting["cell_employment_core_plus_base"]
    weighting["control_grain"] = core["control_grain"]
    weighting["geometry_is_approximate"] = True
    weighting["employment_universe"] = EMPLOYMENT_UNIVERSE
    weighting["reference_date"] = REFERENCE_DATE
    weighting["reach_intersection_calculated"] = False

    diagnostic = pd.DataFrame(diagnostics)
    if (diagnostic["reconciliation_difference"] != 0).any() or diagnostic["uniform_fallback_used"].any():
        raise RuntimeError("Outer allocation failed accounting or evidence availability.")
    return core, base, composition, weighting, diagnostic


def _combine_grids(priority_path: Path, outer: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, str]:
    priority = gpd.read_parquet(priority_path)
    # This path becomes the all-city artifact after the first run. Restrict it
    # back to the reviewed eight-district baseline before appending the outer
    # allocation, so repeat runs cannot duplicate already-added districts.
    priority = priority.loc[priority["district"].isin(PRIORITY_DISTRICTS)].copy()
    priority_value_hash = hashlib.sha256(
        pd.util.hash_pandas_object(priority.drop(columns="geometry"), index=False).values.tobytes()
        + b"".join(priority.geometry.to_wkb())
    ).hexdigest()
    missing = set(priority.columns) - set(outer.columns)
    extra = set(outer.columns) - set(priority.columns)
    if missing or extra:
        raise RuntimeError(f"Outer grid schema differs; missing={sorted(missing)}, extra={sorted(extra)}")
    combined = gpd.GeoDataFrame(pd.concat([priority, outer[priority.columns]], ignore_index=True), geometry="geometry", crs=priority.crs)
    if combined["cell_id"].duplicated().any():
        raise RuntimeError("All-city grid has duplicate physical cell IDs.")
    return combined, priority_value_hash


def write_all_city_spatial_outputs(
    repository_root: Path,
    *,
    osm_pbf_path: Path,
    jrc_raster_path: Path,
    overture_partition_path: Path,
    cache_directory: Path,
) -> dict[str, Path]:
    repository_root = repository_root.resolve()
    output_root = repository_root / "data/office_employment/spatial"
    intermediate = output_root / "intermediate"
    outputs = output_root / "outputs"
    manifests = output_root / "manifests"
    for path in (intermediate, outputs, manifests, cache_directory):
        path.mkdir(parents=True, exist_ok=True)

    protected_priority_paths = {
        "core": outputs / "core-employment-grid-100m.parquet",
        "base": outputs / "core-plus-base-employment-grid-100m.parquet",
        "composition": outputs / "core-plus-sensitivity-grid-100m.parquet",
        "weighting": outputs / "core-plus-weighting-sensitivity-grid-100m.parquet",
    }
    priority_frames = {
        name: gpd.read_parquet(path).loc[
            lambda frame: frame["district"].isin(PRIORITY_DISTRICTS)
        ].copy()
        for name, path in protected_priority_paths.items()
    }
    priority_bytes = PRIORITY_BASELINE_FILE_SHA256.copy()

    district_path = repository_root / "data/economy/shanghai-district-boundaries.geojson"
    districts = load_outer_districts(district_path)
    controls, residuals = build_outer_control_ledger()
    controls_geometry, boundary_manifest = attach_outer_control_geometry(controls, districts, osm_pbf_path)
    cells = build_outer_cell_lattice(districts)
    if _sha256(jrc_raster_path) != JRC_SHA256:
        raise RuntimeError("JRC raster changed.")
    cells = add_jrc_nonresidential_volume(cells, jrc_raster_path)
    clipped_places = cache_directory / f"overture-places-shanghai-{OVERTURE_RELEASE}.parquet"
    if not clipped_places.is_file():
        clip_overture_places(overture_partition_path, district_path, clipped_places)
    cells, overture_quality = add_overture_to_physical_cells(cells, districts, clipped_places)
    evidence, building_quality = extract_building_evidence(
        osm_pbf_path,
        cells,
        expected_sha256=OSM_SHA256,
        source_snapshot_date=OSM_SNAPSHOT_DATE,
    )
    evidence_path = intermediate / "building-function-evidence-outer-districts-100m.parquet"
    evidence.to_parquet(evidence_path, index=False, compression="zstd")
    cells = attach_building_evidence(cells, evidence)
    support, support_quality = build_outer_support(cells, controls_geometry, residuals, districts)

    district_industry = pd.read_csv(
        repository_root / "data/office_employment/intermediate/district-industry-employment-2023.csv",
        dtype={"industry_code": str},
    )
    subgroup = pd.read_csv(
        repository_root / "data/office_employment/scenarios/district-business-services-subgroup-scenarios-2023.csv",
        dtype={"industry_code": str},
    )
    matrix, matrix_diagnostics = construct_control_industry_matrix(
        controls,
        residuals,
        district_industry,
        subgroup,
        priority_districts=OUTER_DISTRICTS,
    )
    outer_core, outer_base, outer_composition, outer_weighting, outer_diagnostics = allocate_outer_grids(cells, support, matrix)

    all_grids: dict[str, gpd.GeoDataFrame] = {}
    priority_row_hashes: dict[str, str] = {}
    for name, outer_grid in {
        "core": outer_core,
        "base": outer_base,
        "composition": outer_composition,
        "weighting": outer_weighting,
    }.items():
        combined, priority_row_hash = _combine_grids(protected_priority_paths[name], outer_grid)
        all_grids[name] = combined
        priority_row_hashes[name] = priority_row_hash

    if int(all_grids["core"]["cell_employment_core"].sum()) != CORE_EMPLOYMENT:
        raise RuntimeError("All-city Core grid does not equal the fixed city denominator.")
    for scenario in SCENARIOS:
        if int(all_grids["composition"][f"cell_employment_core_plus_{scenario}"].sum()) != CORE_PLUS_EMPLOYMENT:
            raise RuntimeError(f"All-city Core+ {scenario} grid does not equal the fixed denominator.")
    for scenario in WEIGHTING_SCENARIOS:
        if int(all_grids["weighting"][f"cell_employment_core_plus_{scenario}"].sum()) != CORE_PLUS_EMPLOYMENT:
            raise RuntimeError(f"All-city weighting {scenario} does not equal the fixed denominator.")

    for name, path in protected_priority_paths.items():
        all_grids[name].to_parquet(path, index=False, compression="zstd")

    old_matrix_path = intermediate / "control-industry-matrix-2023.csv"
    old_matrix = pd.read_csv(old_matrix_path, dtype={"accounting_stratum_id": str, "industry_code": str})
    old_matrix = old_matrix.loc[old_matrix["district"].isin(PRIORITY_DISTRICTS)]
    combined_matrix = pd.concat([old_matrix, matrix], ignore_index=True)
    combined_matrix.to_csv(old_matrix_path, index=False)
    old_matrix_diag_path = intermediate / "control-industry-reconciliation.csv"
    old_matrix_diag = pd.read_csv(old_matrix_diag_path)
    old_matrix_diag = old_matrix_diag.loc[old_matrix_diag["district"].isin(PRIORITY_DISTRICTS)]
    pd.concat([old_matrix_diag, matrix_diagnostics], ignore_index=True).to_csv(old_matrix_diag_path, index=False)
    old_diagnostic_path = outputs / "allocation-diagnostics.csv"
    old_diagnostic = pd.read_csv(old_diagnostic_path, dtype={"accounting_stratum_id": str, "industry_code": str})
    old_diagnostic = old_diagnostic.loc[old_diagnostic["district"].isin(PRIORITY_DISTRICTS)]
    pd.concat([old_diagnostic, outer_diagnostics], ignore_index=True).to_csv(old_diagnostic_path, index=False)

    controls_path = manifests / "outer-district-control-totals-2023.csv"
    residuals_path = manifests / "outer-district-residual-strata-2023.csv"
    boundaries_path = manifests / "outer-district-boundary-manifest.csv"
    controls.to_csv(controls_path, index=False)
    residuals.to_csv(residuals_path, index=False)
    boundary_manifest.to_csv(boundaries_path, index=False)

    full_matrix = pd.read_csv(old_matrix_path, dtype={"accounting_stratum_id": str, "industry_code": str})
    summary = json.loads((outputs / "spatial-allocation-summary.json").read_text(encoding="utf-8"))
    summary.update(
        {
            "schema_version": 3,
            "spatial_scope": "all 16 Shanghai districts",
            "spatial_scope_districts": list(ALL_DISTRICTS),
            "all_city_grid_cell_count": int(len(all_grids["core"])),
            "priority_grid_cell_count": int(len(priority_frames["core"])),
            "outer_grid_cell_count": int(len(outer_core)),
            "all_city_core_allocated_employment": int(all_grids["core"]["cell_employment_core"].sum()),
            "all_city_core_plus_allocated_employment": {scenario: int(all_grids["composition"][f"cell_employment_core_plus_{scenario}"].sum()) for scenario in SCENARIOS},
            "all_city_core_plus_weighting_sensitivity": {scenario: int(all_grids["weighting"][f"cell_employment_core_plus_{scenario}"].sum()) for scenario in WEIGHTING_SCENARIOS},
            "outer_official_fine_control_count": int(controls["row_is_official_fine_control"].sum()),
            "outer_district_fallback_control_count": int((~controls["row_is_official_fine_control"]).sum()),
            "outer_residual_overlay_count": int(len(residuals)),
            "all_city_accounting_stratum_count": int(full_matrix["accounting_stratum_id"].nunique()),
            "priority_grid_rows_preserved_without_reallocation": True,
            "priority_grid_source_sha256_before_extension": priority_bytes,
            "priority_row_content_sha256": priority_row_hashes,
            "source_quality_outer_extension": {**overture_quality, **building_quality, **support_quality},
            "reach_intersection_calculated": False,
            "reach_percentage_calculated": False,
            "approximate_boundary_disclosure": (
                "All ordinary fine supports use exact-name OSM relations clipped to approximate parent-district boundaries. "
                "Controls without reusable polygons use disclosed district overlays; Minhang and Jinshan use district totals because compatible fine tables were not found. "
                "The original eight-district rows and Pudong functional-zone treatment are unchanged."
            ),
        }
    )
    output_hashes = {
        "core_grid": sha256_file(protected_priority_paths["core"]),
        "core_plus_base_grid": sha256_file(protected_priority_paths["base"]),
        "core_plus_sensitivity_grid": sha256_file(protected_priority_paths["composition"]),
        "core_plus_weighting_sensitivity_grid": sha256_file(protected_priority_paths["weighting"]),
        "control_industry_matrix": sha256_file(old_matrix_path),
        "control_industry_reconciliation": sha256_file(old_matrix_diag_path),
        "allocation_diagnostics": sha256_file(old_diagnostic_path),
    }
    summary["output_sha256"] = {**summary.get("output_sha256", {}), **output_hashes}
    summary_path = outputs / "spatial-allocation-summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path = outputs / "all-city-extension-report.md"
    report_path.write_text(
        "# Office-employment all-city spatial extension\n\n"
        f"The analytical grid now covers all 16 districts ({len(all_grids['core']):,} physical 100 m cells). "
        "The reviewed eight-district rows were copied without reallocation.\n\n"
        f"- Core: {int(all_grids['core']['cell_employment_core'].sum()):,}\n"
        f"- Core+ Base/Low/High: {CORE_PLUS_EMPLOYMENT:,} in every composition scenario\n"
        f"- Official outer fine controls: {int(controls['row_is_official_fine_control'].sum())}\n"
        f"- District fallback controls: {int((~controls['row_is_official_fine_control']).sum())} (Minhang and Jinshan)\n"
        f"- Outer residual overlays: {len(residuals)}\n\n"
        "No GDP, all-employment, reach-polygon, station, search, basemap, or Site source was modified.\n",
        encoding="utf-8",
    )
    return {
        **protected_priority_paths,
        "summary": summary_path,
        "report": report_path,
        "controls": controls_path,
        "residuals": residuals_path,
        "boundaries": boundaries_path,
        "evidence": evidence_path,
        "matrix": old_matrix_path,
        "diagnostics": old_diagnostic_path,
    }
