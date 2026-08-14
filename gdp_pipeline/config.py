"""Pinned sources and transparent modelling choices for GDP estimation."""

from __future__ import annotations

from pathlib import Path

GRID_SIZE_METRES = 100
ANALYSIS_CRS = "EPSG:32651"
LIMITS = (10, 20, 30, 40, 50)

SCENARIOS = {
    "central": {"building": 0.50, "lights": 0.25, "poi": 0.25},
    "building_heavy": {"building": 0.60, "lights": 0.20, "poi": 0.20},
    "activity_heavy": {"building": 0.40, "lights": 0.35, "poi": 0.25},
}

REPOSITORY_URL = "https://github.com/FelixVVu/jinke.git"
REACH_RELATIVE_PATH = Path("web/public/data/reach-areas.geojson")
DISTRICT_BOUNDARY_RELATIVE_PATH = Path(
    "data/economy/shanghai-district-boundaries.geojson"
)
DISTRICT_GDP_RELATIVE_PATH = Path("data/economy/shanghai-district-gdp.csv")
CITY_GDP_RELATIVE_PATH = Path("data/economy/shanghai-city-gdp.csv")

JRC_DATASET = "GHS-BUILT-V_NRES_GLOBE_R2023A"
JRC_EPOCH = 2020
JRC_RESOLUTION_METRES = 100
JRC_CRS = "ESRI:54009"
JRC_TILE_SCHEMA_URL = (
    "https://human-settlement.emergency.copernicus.eu/download/"
    "GHSL_data_54009_shapefile.zip"
)
JRC_TILE_BASE_URL = (
    "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/"
    "GHS_BUILT_V_GLOBE_R2023A/"
    "GHS_BUILT_V_NRES_E2020_GLOBE_R2023A_54009_100/V1-0/tiles"
)
JRC_PRODUCT_URL = "https://human-settlement.emergency.copernicus.eu/ghs_buV2023.php"
JRC_DOI = "https://doi.org/10.2905/AB2F107A-03CD-47A3-85E5-139D8EC63283"
JRC_LICENSE = "European Commission reuse notice (Decision 2011/833/EU)"

VIIRS_SHORT_NAME = "VNP46A4"
VIIRS_YEAR = 2025
VIIRS_VERSION = "2"
VIIRS_CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
VIIRS_PRODUCT_URL = "https://www.earthdata.nasa.gov/data/catalog/lpcloud-vnp46a4-002"
VIIRS_DOI = "https://doi.org/10.5067/VIIRS/VNP46A4.002"
VIIRS_USER_GUIDE_URL = (
    "https://www.earthdata.nasa.gov/s3fs-public/2025-05/"
    "BlackMarbleUserGuide_Collection2.0.pdf"
)
VIIRS_RADIANCE_VARIABLE = "NearNadir_Composite_Snow_Free"
VIIRS_QUALITY_VARIABLE = "NearNadir_Composite_Snow_Free_Quality"
VIIRS_NATIVE_RESOLUTION = "15 arc seconds (about 400-500 m at Shanghai latitude)"
VIIRS_LICENSE = "NASA Earth Science data are openly available under NASA data policy"

OVERTURE_CATALOG_URL = "https://stac.overturemaps.org/catalog.json"
OVERTURE_DOCS_URL = "https://docs.overturemaps.org/getting-data/overturemaps-py/"
OVERTURE_LICENSE_URL = "https://docs.overturemaps.org/attribution/"
OVERTURE_CLIENT_VERSION = "1.0.1"

BOUNDARY_SOURCE_URL = (
    "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/"
    "releaseData/gbOpen/CHN/ADM3/geoBoundaries-CHN-ADM3-all.zip"
)
BOUNDARY_METADATA_URL = "https://www.geoboundaries.org/api/current/gbOpen/CHN/ADM3/"
BOUNDARY_LICENSE = "Open Data Commons Open Database License 1.0"

# Substring rules are intentionally broad enough to cover Overture's Basic
# category vocabulary while remaining easy to audit. A place is counted once,
# in the first matching group. No class-specific multiplier is applied.
ECONOMIC_POI_RULES = {
    "retail_commerce": (
        "shop", "store", "market", "mall", "retail", "supermarket",
        "convenience", "department_store", "wholesale", "car_dealer",
    ),
    "food_hospitality": (
        "restaurant", "cafe", "coffee", "bar", "pub", "bakery", "hotel",
        "hostel", "lodging", "food", "fast_food",
    ),
    "business_finance": (
        "office", "bank", "finance", "insurance", "business", "company",
        "cowork", "real_estate", "professional_service",
    ),
    "industry_logistics": (
        "factory", "industrial", "warehouse", "logistics", "freight",
        "manufactur", "distribution", "port",
    ),
    "transport": (
        "station", "airport", "terminal", "transport", "parking",
        "metro", "subway", "railway", "bus",
    ),
    "health": (
        "hospital", "clinic", "medical", "dentist", "pharmacy", "health",
        "veterinary",
    ),
    "education_research": (
        "school", "college", "university", "education", "research",
        "laboratory", "training",
    ),
    "culture_recreation": (
        "museum", "theatre", "theater", "cinema", "stadium", "sports",
        "gym", "attraction", "gallery", "amusement", "recreation",
    ),
    "public_services": (
        "government", "courthouse", "police", "fire_station", "post_office",
        "library", "community_centre", "community_center",
    ),
}
