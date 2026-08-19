"""Build the immutable census, cross-walk, boundary, and source manifests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import pyogrio

from .config import (
    ANALYSIS_CRS,
    CITY_EMPLOYMENT,
    EMPLOYMENT_UNIVERSE,
    JRC_ARCHIVE_NAME,
    JRC_ARCHIVE_SHA256,
    JRC_DATASET,
    JRC_DOI,
    JRC_LICENSE,
    JRC_RASTER_NAME,
    JRC_RASTER_SHA256,
    JRC_URL,
    OSM_ATTRIBUTION_URL,
    OSM_LICENSE,
    OSM_PBF_SHA256,
    OSM_SNAPSHOT_DATE,
    OSM_SOURCE_URL,
    OVERTURE_CATALOG_URL,
    OVERTURE_CLIPPED_ROWS,
    OVERTURE_CLIPPED_SHA256,
    OVERTURE_LICENSE_URL,
    OVERTURE_LICENSE,
    OVERTURE_RELEASE,
    OVERTURE_SOURCE_URL,
    OFFICIAL_ARCGIS_MAP_URL,
    OFFICIAL_MAP_BASE_SHA256,
    OFFICIAL_MAP_EXPORT_BBOX_WGS84,
    OFFICIAL_MAP_EXPORT_PIXELS,
    OFFICIAL_MAP_LABEL_SHA256,
    OFFICIAL_MAP_OVERLAY_SHA256,
    OFFICIAL_MAP_REVIEW_DATE,
    OFFICIAL_MAP_URL,
    PRODUCTION_REACH_SHA256,
    REFERENCE_DATE,
    RESTRICTED_ZONE_API,
    RESTRICTED_ZONE_CODES,
    RESTRICTED_ZONE_DOCS,
    RESTRICTED_ZONE_VINTAGE,
    SOURCE_CRS,
)
from .seed_data import (
    CITY_TABLE_URL,
    CODE_REFERENCE_URL,
    CONTROLS,
    DISTRICTS,
    RESIDUALS,
    SOURCE_INFO,
    XUHUI_INDIVIDUAL_BUSINESS_EMPLOYMENT,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def district_manifest() -> pd.DataFrame:
    rows = [
        {
            "district": district,
            "district_en": district_en,
            "employment": employment,
            "priority_district": priority,
            "reference_date": REFERENCE_DATE,
            "employment_universe": EMPLOYMENT_UNIVERSE,
            "individual_business_included": False,
            "individual_business_employment_reported_separately": (
                17_098 if district == "徐汇区" else pd.NA
            ),
            "individual_business_source_reference": (
                "Xuhui Table 1-8, printed/PDF page 8; excluded from benchmark"
                if district == "徐汇区"
                else "not transcribed for this benchmark"
            ),
            "source_url": CITY_TABLE_URL,
            "source_table": "A1-02",
        }
        for district, district_en, employment, priority in DISTRICTS
    ]
    frame = pd.DataFrame(rows)
    if int(frame["employment"].sum()) != CITY_EMPLOYMENT:
        raise AssertionError("The 16 official district totals do not equal 13,099,795.")
    return frame


def control_manifest() -> pd.DataFrame:
    frame = pd.DataFrame(CONTROLS)
    frame["official_control_code_2023"] = frame[
        "official_control_code_2023"
    ].astype("string")
    frame["accounting_stratum_id"] = frame["accounting_stratum_id"].astype("string")
    frame["osm_relation_id"] = frame["osm_relation_id"].astype("Int64")
    if len(frame) != 116 or frame["accounting_stratum_id"].duplicated().any():
        raise AssertionError("Control manifest must contain 116 unique accounting strata.")
    if int(frame["employment_reconciled"].sum()) != 7_114_511:
        raise AssertionError("Fine-control employment must reconcile to 7,114,511.")
    if frame.loc[frame["control_type"] != "functional_zone", "osm_relation_id"].isna().any():
        raise AssertionError("Every ordinary control must have a pinned OSM relation ID.")
    return frame


def residual_manifest() -> pd.DataFrame:
    frame = pd.DataFrame(RESIDUALS)
    district = district_manifest().set_index("district")["employment"]
    controls = control_manifest().groupby("district")["employment_reconciled"].sum()
    expected = district.reindex(controls.index) - controls
    actual = frame.set_index("district")["employment_nominal"].reindex(expected.index)
    if not actual.equals(expected.astype(actual.dtype)):
        raise AssertionError(f"Residuals do not reconcile to district totals: {actual - expected}")
    if int(frame["employment_nominal"].sum()) != 526_062:
        raise AssertionError("Priority residual employment must equal 526,062.")
    frame["lower_bound_reach_rule"] = "zero residual workers enter the reach numerator"
    frame["upper_bound_reach_rule"] = "all residual workers enter the reach numerator"
    frame["employment_universe"] = EMPLOYMENT_UNIVERSE
    frame["reference_date"] = REFERENCE_DATE
    return frame


def extract_osm_controls(pbf_path: Path) -> gpd.GeoDataFrame:
    """Extract only the 113 pinned admin-level-8 OSM relations."""

    if sha256_file(pbf_path) != OSM_PBF_SHA256:
        raise ValueError("OSM PBF hash differs from the frozen 2026-08-19 snapshot.")
    crosswalk = control_manifest()
    ordinary = crosswalk.loc[crosswalk["control_type"] != "functional_zone"].copy()
    relation_ids = ordinary["osm_relation_id"].astype(str)
    source = pyogrio.read_dataframe(
        pbf_path,
        layer="multipolygons",
        columns=["osm_id", "name", "admin_level", "boundary"],
    )
    source["osm_id"] = source["osm_id"].astype("string")
    selected = source.loc[source["osm_id"].isin(set(relation_ids))].copy()
    if len(selected) != 113 or selected["osm_id"].duplicated().any():
        raise ValueError(f"Expected 113 unique OSM relations; extracted {len(selected)}.")
    selected = selected.merge(
        ordinary[
            [
                "district",
                "official_control_code_2023",
                "official_control_name_2023",
                "osm_relation_id",
            ]
        ].assign(osm_id=relation_ids.to_numpy()),
        on="osm_id",
        how="inner",
        validate="one_to_one",
    )
    mismatch = selected.loc[
        selected["name"] != selected["official_control_name_2023"],
        ["osm_id", "name", "official_control_name_2023"],
    ]
    if not mismatch.empty:
        raise ValueError(f"OSM names do not exactly match the frozen cross-walk:\n{mismatch}")
    if not selected["admin_level"].eq("8").all():
        raise ValueError("Every selected OSM relation must have admin_level=8.")
    if not selected["boundary"].eq("administrative").all():
        raise ValueError("Every selected OSM relation must be administrative.")
    if selected.geometry.isna().any() or selected.geometry.is_empty.any():
        raise ValueError("An OSM control has empty geometry.")
    if not selected.geometry.is_valid.all():
        invalid = selected.loc[~selected.geometry.is_valid, "name"].tolist()
        raise ValueError(f"Invalid OSM control geometry: {invalid}")
    selected = selected.rename(columns={"name": "osm_name", "osm_id": "osm_relation_id_source"})
    selected["geometry_is_approximate"] = True
    selected["source_snapshot_date"] = OSM_SNAPSHOT_DATE
    selected["source_pbf_sha256"] = OSM_PBF_SHA256
    selected["source_url"] = OSM_SOURCE_URL
    selected["license"] = OSM_LICENSE
    selected = selected[
        [
            "district",
            "official_control_code_2023",
            "official_control_name_2023",
            "osm_name",
            "osm_relation_id_source",
            "admin_level",
            "boundary",
            "geometry_is_approximate",
            "source_snapshot_date",
            "source_pbf_sha256",
            "source_url",
            "license",
            "geometry",
        ]
    ].sort_values("official_control_code_2023")
    return gpd.GeoDataFrame(selected, geometry="geometry", crs=source.crs).to_crs(SOURCE_CRS)


def boundary_manifest(extracted_sha256: str) -> pd.DataFrame:
    controls = control_manifest()
    rows: list[dict[str, Any]] = []
    for control in controls.itertuples(index=False):
        is_zone = control.control_type == "functional_zone"
        rows.append(
            {
                "district": control.district,
                "accounting_stratum_id": control.accounting_stratum_id,
                "control_name": control.official_control_name_2023,
                "control_type": control.control_type,
                "boundary_source": (
                    "Ruiduobao 2020 statistical polygon"
                    if is_zone
                    else "OpenStreetMap admin_level=8 relation"
                ),
                "source_feature_id": (
                    control.accounting_stratum_id if is_zone else int(control.osm_relation_id)
                ),
                "source_url": RESTRICTED_ZONE_API if is_zone else OSM_SOURCE_URL,
                "source_vintage": RESTRICTED_ZONE_VINTAGE if is_zone else OSM_SNAPSHOT_DATE,
                "source_crs": SOURCE_CRS,
                "analysis_crs": ANALYSIS_CRS,
                "geometry_is_approximate": True,
                "license_or_terms": (
                    "academic/education reference only; commercial use prohibited"
                    if is_zone
                    else OSM_LICENSE
                ),
                "redistribution_status": (
                    "source geometry not redistributed; acquisition instructions and derived non-reconstructable statistics only"
                    if is_zone
                    else "redistributable under ODbL with attribution/share-alike"
                ),
                "repository_geometry_file": (
                    "" if is_zone else "data/employment/raw/boundaries/osm-priority-controls-2026-08-19.geojson"
                ),
                "repository_geometry_sha256": "" if is_zone else extracted_sha256,
                "official_map_validation_required": True,
                "official_map_validation_status": "pending",
            }
        )
    return pd.DataFrame(rows)


def source_manifest(
    *,
    extracted_osm_sha256: str,
    xuhui_pdf_sha256: str,
) -> pd.DataFrame:
    bulletin_rows = []
    seen: set[str] = set()
    for control in CONTROLS:
        district = control["district"]
        if district in seen:
            continue
        seen.add(district)
        bulletin_rows.append(
            {
                "source_id": f"epc5-{district}",
                "source_type": "official employment bulletin",
                "title": f"{district} Fifth National Economic Census main data bulletin no. 1",
                "publisher": f"{district} Statistics Bureau",
                "reference_date_or_vintage": REFERENCE_DATE,
                "snapshot_or_retrieval_date": "2026-08-19",
                "url": control["publication_url"],
                "local_or_repository_file": "uploaded original; not redistributed" if district == "徐汇区" else "not redistributed",
                "sha256": xuhui_pdf_sha256 if district == "徐汇区" else "",
                "license_or_terms": "official publication; source citation retained",
                "reuse_status": "tabular facts transcribed with citation",
                "used_for": "fine-control employment, units, rounding, and exclusions",
                "notes": (
                    control["geographic_table_exclusions"]
                    + (
                        "; Table 1-8 separately reports 17,098 individual-business "
                        "workers and Table 1-7 reports 7,559 individual businesses; "
                        "both are excluded"
                        if district == "徐汇区"
                        else ""
                    )
                ),
            }
        )
    rows = [
        {
            "source_id": "shanghai-epc5-district-control",
            "source_type": "official employment table",
            "title": "Shanghai Fifth National Economic Census district legal-entity employment table A1-02",
            "publisher": "Shanghai Municipal Statistics Bureau",
            "reference_date_or_vintage": REFERENCE_DATE,
            "snapshot_or_retrieval_date": "2026-08-17",
            "url": CITY_TABLE_URL,
            "local_or_repository_file": "not redistributed",
            "sha256": "",
            "license_or_terms": "official statistical publication",
            "reuse_status": "tabular facts transcribed with citation",
            "used_for": "fixed city and 16-district denominator controls",
            "notes": "13,099,795 legal-entity workers; individual businesses excluded",
        },
        {
            "source_id": "nbs-2023-statistical-codes",
            "source_type": "official code reference",
            "title": "2023 statistical zoning-code publication route",
            "publisher": "National Bureau of Statistics of China",
            "reference_date_or_vintage": "2023",
            "snapshot_or_retrieval_date": "2026-08-19",
            "url": CODE_REFERENCE_URL,
            "local_or_repository_file": "data/employment/manifests/control-crosswalk-2023.csv",
            "sha256": "",
            "license_or_terms": "official code publication",
            "reuse_status": "codes/names transcribed and cross-checked",
            "used_for": "immutable 2023 control identity",
            "notes": "No fuzzy or silent name matching is performed at runtime.",
        },
        {
            "source_id": "osm-shanghai-2026-08-19",
            "source_type": "open vector boundary",
            "title": "OpenStreetMap Shanghai extract",
            "publisher": "OpenStreetMap contributors; extract by download.openstreetmap.fr",
            "reference_date_or_vintage": OSM_SNAPSHOT_DATE,
            "snapshot_or_retrieval_date": OSM_SNAPSHOT_DATE,
            "url": OSM_SOURCE_URL,
            "local_or_repository_file": "source PBF cached outside git; extracted 113-control GeoJSON in repository",
            "sha256": OSM_PBF_SHA256,
            "license_or_terms": OSM_LICENSE,
            "reuse_status": "extracted geometry redistributed under ODbL",
            "used_for": "113 ordinary street/town control geometries",
            "notes": f"Attribution: {OSM_ATTRIBUTION_URL}; extracted GeoJSON SHA-256 {extracted_osm_sha256}",
        },
        {
            "source_id": "jrc-ghsl-nres-2020",
            "source_type": "non-residential built-volume raster",
            "title": JRC_DATASET,
            "publisher": "European Commission Joint Research Centre",
            "reference_date_or_vintage": "2020 epoch; R2023A release",
            "snapshot_or_retrieval_date": "2026-08-19",
            "url": JRC_URL,
            "local_or_repository_file": f"external cache/{JRC_ARCHIVE_NAME}; extracted {JRC_RASTER_NAME}",
            "sha256": JRC_ARCHIVE_SHA256,
            "license_or_terms": JRC_LICENSE,
            "reuse_status": "source raster acquired reproducibly; not committed",
            "used_for": "building-volume and calibrated workplace models",
            "notes": f"DOI {JRC_DOI}; extracted raster SHA-256 {JRC_RASTER_SHA256}",
        },
        {
            "source_id": "overture-places-2026-07-22",
            "source_type": "open place/establishment points",
            "title": "Overture Maps Places",
            "publisher": "Overture Maps Foundation",
            "reference_date_or_vintage": OVERTURE_RELEASE,
            "snapshot_or_retrieval_date": "2026-08-19",
            "url": OVERTURE_SOURCE_URL,
            "local_or_repository_file": "external exact-Shanghai cache; not committed",
            "sha256": OVERTURE_CLIPPED_SHA256,
            "license_or_terms": f"{OVERTURE_LICENSE}; {OVERTURE_LICENSE_URL}",
            "reuse_status": "derived predictors and aggregate diagnostics committed",
            "used_for": "interpretable workplace-category predictors and finance residual surface",
            "notes": (
                f"{OVERTURE_CLIPPED_ROWS} exact-Shanghai rows; catalog "
                f"{OVERTURE_CATALOG_URL}; predictor snapshot post-dates the 2023 "
                "employment reference date and is used only as a spatial proxy"
            ),
        },
        {
            "source_id": "pudong-zone-statistical-polygons-2020",
            "source_type": "restricted fallback vector boundary",
            "title": "Ruiduobao China divisions map township/statistical polygons",
            "publisher": "Ruiduobao",
            "reference_date_or_vintage": str(RESTRICTED_ZONE_VINTAGE),
            "snapshot_or_retrieval_date": "2026-08-19",
            "url": RESTRICTED_ZONE_DOCS,
            "local_or_repository_file": "not committed; reacquire exact codes 310115501000-310115503000",
            "sha256": "per-feature hashes documented in methodology",
            "license_or_terms": "academic/education reference only; commercial use prohibited",
            "reuse_status": "source geometry not redistributed",
            "used_for": "fallback central and sensitivity supports for three immutable Pudong accounting strata",
            "notes": "API township geometries are approximately 2020 even when later names are requested.",
        },
        {
            "source_id": "shanghai-tianditu-official-map-validation",
            "source_type": "authoritative display/validation map",
            "title": "Shanghai Tianditu standard map; SHMAP_D and SHMAP_LAN services",
            "publisher": "Shanghai Planning and Natural Resources Bureau / Shanghai Surveying and Mapping Institute",
            "reference_date_or_vintage": OFFICIAL_MAP_REVIEW_DATE,
            "snapshot_or_retrieval_date": OFFICIAL_MAP_REVIEW_DATE,
            "url": OFFICIAL_MAP_URL,
            "local_or_repository_file": "display exports and review overlay retained outside git",
            "sha256": f"base={OFFICIAL_MAP_BASE_SHA256}; labels={OFFICIAL_MAP_LABEL_SHA256}; overlay={OFFICIAL_MAP_OVERLAY_SHA256}",
            "license_or_terms": "authoritative display service; source images not redistributed",
            "reuse_status": "validation observations and non-reconstructable hashes committed",
            "used_for": "visual validation of reach-relevant boundary segments",
            "notes": f"service {OFFICIAL_ARCGIS_MAP_URL}; bbox {OFFICIAL_MAP_EXPORT_BBOX_WGS84}; pixels {OFFICIAL_MAP_EXPORT_PIXELS}",
        },
        {
            "source_id": "pudong-official-zone-planning-scopes",
            "source_type": "official planning-scope evidence",
            "title": "FTZ Bonded Area, Jinqiao ETDZ, and Zhangjiang official planning documents",
            "publisher": "Pudong New Area government and zone administrations",
            "reference_date_or_vintage": "2022-2025 publications",
            "snapshot_or_retrieval_date": "2026-08-19",
            "url": "https://www.pudong.gov.cn/zwgk/14478.gkml_zhzw_ghjh/2024/138/326950.html",
            "local_or_repository_file": "not redistributed",
            "sha256": "",
            "license_or_terms": "official publications; cited for validation",
            "reuse_status": "reported areas and scope descriptions only",
            "used_for": "functional-zone reported-area morphology sensitivity",
            "notes": "Additional exact URLs are retained in intermediate/pudong-zone-sensitivity.csv; planning scope is not equated with census accounting scope.",
        },
        {
            "source_id": "jinke-production-reach-polygons",
            "source_type": "pinned production analysis input",
            "title": "Existing Jinke production reach polygons",
            "publisher": "Jinke repository",
            "reference_date_or_vintage": "main at 4a50a1abb623b11328eeab514e6086d35281fe7e",
            "snapshot_or_retrieval_date": "2026-08-19",
            "url": "https://github.com/FelixVVu/jinke/blob/main/web/public/data/reach-areas.geojson",
            "local_or_repository_file": "web/public/data/reach-areas.geojson",
            "sha256": PRODUCTION_REACH_SHA256,
            "license_or_terms": "repository asset",
            "reuse_status": "read only; hash-pinned and never regenerated",
            "used_for": "exact 10/20/30/40/50-minute intersections",
            "notes": "Pipeline fails closed if this hash changes.",
        },
    ]
    return pd.DataFrame(rows + bulletin_rows)


def rounding_constraints() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"district": "徐汇区", "constraint": "sum of 13 displayed rows", "nominal": 954_400, "lower": 953_750, "upper_exclusive": 955_050, "central_rule": "published nominal midpoints"},
            {"district": "静安区", "constraint": "sum of 14 displayed rows", "nominal": 917_000, "lower": 910_000, "upper_exclusive": 924_000, "central_rule": "published nominal midpoints"},
            {"district": "普陀区", "constraint": "sum of 10 displayed rows", "nominal": 512_000, "lower": 507_000, "upper_exclusive": 517_000, "central_rule": "published nominal midpoints"},
            {"district": "浦东新区", "constraint": "street subtotal", "nominal": 695_000, "lower": 694_500, "upper_exclusive": 695_500, "central_rule": "least-squares row reconciliation (-250 each)"},
            {"district": "浦东新区", "constraint": "town subtotal", "nominal": 1_099_000, "lower": 1_098_500, "upper_exclusive": 1_099_500, "central_rule": "published nominal midpoints"},
            {"district": "浦东新区", "constraint": "functional-zone subtotal", "nominal": 821_000, "lower": 820_500, "upper_exclusive": 821_500, "central_rule": "published nominal midpoints"},
        ]
    )


def xuhui_individual_business_manifest() -> pd.DataFrame:
    rows = [
        {
            "district": "徐汇区",
            "industry": industry,
            "individual_business_employment": employment,
            "unit": "persons",
            "table_page_reference": "Table 1-8, printed/PDF page 8",
            "employment_universe": "individual-business workers (separate universe)",
            "included_in_benchmark_denominator": False,
            "publication_url": SOURCE_INFO["徐汇区"]["url"],
        }
        for industry, employment in XUHUI_INDIVIDUAL_BUSINESS_EMPLOYMENT
    ]
    frame = pd.DataFrame(rows)
    if int(frame["individual_business_employment"].sum()) != 17_098:
        raise AssertionError("Xuhui individual-business rows must sum to 17,098.")
    return frame


def write_manifests(
    *,
    repository_root: Path,
    osm_pbf_path: Path,
    xuhui_pdf_sha256: str,
) -> dict[str, Path]:
    manifest_dir = repository_root / "data/employment/manifests"
    boundary_path = (
        repository_root
        / "data/employment/raw/boundaries/osm-priority-controls-2026-08-19.geojson"
    )
    manifest_dir.mkdir(parents=True, exist_ok=True)
    boundary_path.parent.mkdir(parents=True, exist_ok=True)

    controls = control_manifest()
    districts = district_manifest()
    residuals = residual_manifest()
    extracted = extract_osm_controls(osm_pbf_path)
    extracted.to_file(boundary_path, driver="GeoJSON", index=False)
    boundary_sha = sha256_file(boundary_path)

    paths = {
        "controls": manifest_dir / "control-crosswalk-2023.csv",
        "districts": manifest_dir / "district-employment-2023.csv",
        "residuals": manifest_dir / "residual-strata.csv",
        "boundaries": manifest_dir / "boundary-manifest.csv",
        "sources": manifest_dir / "source-manifest.csv",
        "rounding": manifest_dir / "rounding-constraints.csv",
        "xuhui_individual_business": (
            manifest_dir / "xuhui-individual-business-employment-2023.csv"
        ),
        "osm_geometry": boundary_path,
    }
    controls.to_csv(paths["controls"], index=False)
    districts.to_csv(paths["districts"], index=False)
    residuals.to_csv(paths["residuals"], index=False)
    boundary_manifest(boundary_sha).to_csv(paths["boundaries"], index=False)
    source_manifest(
        extracted_osm_sha256=boundary_sha,
        xuhui_pdf_sha256=xuhui_pdf_sha256,
    ).to_csv(paths["sources"], index=False)
    rounding_constraints().to_csv(paths["rounding"], index=False)
    xuhui_individual_business_manifest().to_csv(
        paths["xuhui_individual_business"], index=False
    )
    return paths
