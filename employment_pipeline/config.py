"""Pinned universe, paths, sources, and modelling choices for employment v1."""

from __future__ import annotations

from pathlib import Path

ANALYSIS_CRS = "EPSG:32651"
SOURCE_CRS = "EPSG:4326"
GRID_SIZE_METRES = 100
LIMITS = (10, 20, 30, 40, 50)

CITY_EMPLOYMENT = 13_099_795
PRIORITY_DISTRICT_EMPLOYMENT = 7_640_573
NOMINAL_FINE_CONTROL_EMPLOYMENT = 7_114_511
NOMINAL_RESIDUAL_EMPLOYMENT = 526_062
EMPLOYMENT_UNIVERSE = (
    "2023 secondary- and tertiary-sector legal-entity workplace employment"
)
REFERENCE_DATE = "2023-12-31"

REPOSITORY_URL = "https://github.com/FelixVVu/jinke.git"
REACH_RELATIVE_PATH = Path("web/public/data/reach-areas.geojson")
CONTROL_CROSSWALK_RELATIVE_PATH = Path(
    "data/employment/manifests/control-crosswalk-2023.csv"
)
DISTRICT_EMPLOYMENT_RELATIVE_PATH = Path(
    "data/employment/manifests/district-employment-2023.csv"
)
RESIDUAL_RELATIVE_PATH = Path("data/employment/manifests/residual-strata.csv")
OSM_BOUNDARY_RELATIVE_PATH = Path(
    "data/employment/raw/boundaries/osm-priority-controls-2026-08-19.geojson"
)
GRID_OUTPUT_RELATIVE_PATH = Path(
    "data/employment/intermediate/employment-allocation-grid.parquet"
)
REACH_OUTPUT_RELATIVE_PATH = Path("web/public/data/reach-employment.json")
METHODOLOGY_OUTPUT_RELATIVE_PATH = Path(
    "web/public/data/employment-methodology.json"
)

OSM_SOURCE_URL = (
    "https://download.openstreetmap.fr/extracts/asia/china/shanghai.osm.pbf"
)
OSM_SNAPSHOT_DATE = "2026-08-19"
OSM_PBF_SHA256 = "cba608c2e67cbd2ee7616dcee6833e575e818237048faabf4c0e447acd6c0b6f"
OSM_LICENSE = "OpenStreetMap contributors, Open Database License 1.0"
OSM_ATTRIBUTION_URL = "https://www.openstreetmap.org/copyright"

JRC_DATASET = "GHS-BUILT-V_NRES_GLOBE_R2023A"
JRC_EPOCH = 2020
JRC_TILE_ID = "R6_C30"
JRC_ARCHIVE_NAME = (
    "GHS_BUILT_V_NRES_E2020_GLOBE_R2023A_54009_100_V1_0_R6_C30.zip"
)
JRC_RASTER_NAME = JRC_ARCHIVE_NAME.replace(".zip", ".tif")
JRC_URL = (
    "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/"
    "GHS_BUILT_V_GLOBE_R2023A/"
    "GHS_BUILT_V_NRES_E2020_GLOBE_R2023A_54009_100/V1-0/tiles/"
    + JRC_ARCHIVE_NAME
)
JRC_ARCHIVE_SHA256 = "7aaa3c63832bccd88ba23f926a81b635f3da8ef7345546abbcf6af7232e3d34d"
JRC_RASTER_SHA256 = "bb7e081ca0f2f2d4fc89892158efbb2dc566711108df097e35fdc874dfd2d607"
JRC_DOI = "https://doi.org/10.2905/AB2F107A-03CD-47A3-85E5-139D8EC63283"
JRC_LICENSE = "European Commission reuse notice (Decision 2011/833/EU)"

OVERTURE_RELEASE = "2026-07-22.0"
OVERTURE_SOURCE_URL = (
    "https://overturemaps.org/download/"
)
OVERTURE_CATALOG_URL = "https://stac.overturemaps.org/catalog.json"
OVERTURE_CLIPPED_SHA256 = (
    "1b25bbe11ccec364562d78617b717f865fb1be4a1018d62a1e4d211662761144"
)
OVERTURE_CLIPPED_ROWS = 20_738
OVERTURE_LICENSE_URL = "https://docs.overturemaps.org/attribution/"
OVERTURE_LICENSE = (
    "Places is multi-license: CDLA Permissive 2.0 or Apache 2.0 by source; "
    "retain release per-source attribution"
)

RESTRICTED_ZONE_API = "https://map.ruiduobao.com/getGsonDB"
RESTRICTED_ZONE_DOCS = (
    "https://map.ruiduobao.com/others/API%E6%96%87%E6%A1%A3.html"
)
RESTRICTED_ZONE_VINTAGE = 2020
RESTRICTED_ZONE_CODES = (
    "310115501000",
    "310115502000",
    "310115503000",
)

OFFICIAL_MAP_URL = "https://shanghai.tianditu.gov.cn/map/views/standardMap.html"
OFFICIAL_ARCGIS_MAP_URL = (
    "http://mape.shanghai-map.net/arcgis/rest/services/SHMAP_D/MapServer"
)
OFFICIAL_MAP_REVIEW_DATE = "2026-08-19"
OFFICIAL_MAP_EXPORT_BBOX_WGS84 = "121.33,31.015,121.83,31.325"
OFFICIAL_MAP_EXPORT_PIXELS = "4096x2540"
OFFICIAL_MAP_BASE_SHA256 = (
    "817441269b0d9074334e41388b0c92868acb202ccdd89c29b4ee29d0223c8fbe"
)
OFFICIAL_MAP_LABEL_SHA256 = (
    "c329d544a994190f7f37b65fef536b2bc0b2e0df4a4f050f8e0dc5e07ac81b7b"
)
OFFICIAL_MAP_OVERLAY_SHA256 = (
    "c86463911ce2c1e36fb168e78f266bc633251ad46c0a25c9b93a0a5ee3af5a8c"
)

PRODUCTION_REACH_SHA256 = (
    "6f039b0661f63c1017a2c4a3bc8f5c4d8fdef207ca10afe987f160642fb5656b"
)

# Deliberately no VIIRS dependency in v1. The source is auxiliary and the official
# numerical annual product requires an Earthdata credential; no synthetic substitute
# or image-tile brightness was used.
VIIRS_USED = False

POI_CATEGORY_RULES = {
    "business_finance": (
        "bank", "finance", "insurance", "investment", "professional_service",
        "corporate_or_business_office", "business", "accounting", "lawyer",
        "real_estate", "cowork", "consult",
    ),
    "industry_logistics": (
        "manufacturer", "factory", "industrial", "warehouse", "logistics",
        "freight", "shipping", "distribution", "wholesale", "machine_service",
        "port", "delivery_service",
    ),
    "education_research": (
        "university", "college", "research", "laboratory", "place_of_learning",
        "campus", "school", "training",
    ),
    "retail_hospitality": (
        "store", "shop", "market", "retail", "restaurant", "cafe", "coffee",
        "hotel", "resort", "lodging", "food", "bar", "bakery",
    ),
    "health_public": (
        "hospital", "clinic", "medical", "pharmacy", "health", "government",
        "public_service", "courthouse", "police", "fire_station",
    ),
}

MODEL_NAMES = ("uniform", "building_volume", "calibrated_workplace")
BOUNDARY_DISPLACEMENT_METRES = 100.0
