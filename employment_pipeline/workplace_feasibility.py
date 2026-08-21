"""Reproducible feasibility diagnostics for targeted workplace-data refinement.

This module does not allocate employment and does not fit a model.  It freezes the
source-audit inventory for the controls prioritized by the 50-minute structural
certainty decomposition and quantifies how much of the *existing* three-model
spread could be removed under transparent source-effectiveness scenarios.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CITY_EMPLOYMENT


MODEL_COLUMNS = [
    "uniform_jobs_inside",
    "building_jobs_inside",
    "ppml_jobs_inside",
]

TARGET_CONTROLS = [
    "金桥经济技术开发区",
    "广中路街道",
    "三林镇",
    "张江高科技园区",
    "徐家汇街道",
    "天目西路街道",
    "周浦镇",
    "五角场街道",
    "仙霞新村街道",
    "宝山路街道",
    "陆家嘴街道",
    "北外滩街道",
    "外滩街道",
    "新泾镇",
]

STATUS = {
    "金桥经济技术开发区": "STRONG INDEPENDENT PROXY AVAILABLE",
    "广中路街道": "STRONG INDEPENDENT PROXY AVAILABLE",
    "三林镇": "ONLY EXISTING JRC/POI-TYPE PROXIES AVAILABLE",
    "张江高科技园区": "STRONG INDEPENDENT PROXY AVAILABLE",
    "徐家汇街道": "STRONG INDEPENDENT PROXY AVAILABLE",
    "天目西路街道": "STRONG INDEPENDENT PROXY AVAILABLE",
    "周浦镇": "ONLY EXISTING JRC/POI-TYPE PROXIES AVAILABLE",
    "五角场街道": "STRONG INDEPENDENT PROXY AVAILABLE",
    "仙霞新村街道": "ONLY EXISTING JRC/POI-TYPE PROXIES AVAILABLE",
    "宝山路街道": "ONLY EXISTING JRC/POI-TYPE PROXIES AVAILABLE",
    "陆家嘴街道": "STRONG INDEPENDENT PROXY AVAILABLE",
    "北外滩街道": "NO PRACTICAL IMPROVEMENT AVAILABLE",
    "外滩街道": "NO PRACTICAL IMPROVEMENT AVAILABLE",
    "新泾镇": "ONLY EXISTING JRC/POI-TYPE PROXIES AVAILABLE",
}

# Rank within the 14-control acquisition queue.  Lower is easier/cheaper.
FEASIBILITY_RANK = {
    "徐家汇街道": 1,
    "天目西路街道": 2,
    "五角场街道": 3,
    "广中路街道": 4,
    "陆家嘴街道": 5,
    "宝山路街道": 6,
    "仙霞新村街道": 7,
    "新泾镇": 8,
    "外滩街道": 9,
    "北外滩街道": 10,
    "金桥经济技术开发区": 11,
    "张江高科技园区": 12,
    "三林镇": 13,
    "周浦镇": 14,
}

FEASIBILITY_COST = {
    "徐家汇街道": "LOW-MEDIUM: compact ordinary control; open building data plus multiple metro anchors",
    "天目西路街道": "LOW-MEDIUM: compact ordinary control; open building data plus rail/metro anchors",
    "五角场街道": "LOW-MEDIUM: compact ordinary control; official commercial/innovation anchors plus metro",
    "广中路街道": "LOW-MEDIUM: compact ordinary control and a large existing model disagreement",
    "陆家嘴街道": "LOW-MEDIUM: strong official office-stock validation, but almost fully inside",
    "宝山路街道": "MEDIUM: mixed land use; building and station proxies are indirect",
    "仙霞新村街道": "MEDIUM: office/residential mixture; mobile work population materially preferable",
    "新泾镇": "MEDIUM: mixed town and only 3.34% of support inside",
    "外滩街道": "LOW acquisition cost but negligible benefit because 99.30% of support is inside",
    "北外滩街道": "LOW acquisition cost but negligible benefit because 99.74% of support is inside",
    "金桥经济技术开发区": "HIGH: negotiated workplace data plus census-zone membership/support resolution",
    "张江高科技园区": "HIGH: negotiated workplace data plus census-zone membership/support resolution",
    "三林镇": "HIGH: mixed town; a workplace-population grid or insured-establishment census is needed",
    "周浦镇": "HIGH: mixed town; a workplace-population grid or insured-establishment census is needed",
}

PREFERRED_EVIDENCE = {
    "金桥经济技术开发区": "2023 work-population grid plus an authoritative census-zone establishment roster/polygon",
    "广中路街道": "CMAB building function/volume pilot, validated with work-population grid or insured establishments",
    "三林镇": "2023 work-population grid; enterprise insured counts only as a secondary check",
    "张江高科技园区": "2023 work-population grid plus an authoritative census-zone establishment roster/polygon",
    "徐家汇街道": "CMAB plus 2023 work-population grid; metro exits as validation only",
    "天目西路街道": "CMAB plus 2023 work-population grid; rail/metro exits as validation only",
    "周浦镇": "2023 work-population grid; enterprise insured counts only as a secondary check",
    "五角场街道": "CMAB plus 2023 work-population grid; metro and official anchors as validation",
    "仙霞新村街道": "2023 work-population grid or geocoded insured-establishment counts",
    "宝山路街道": "2023 work-population grid or geocoded insured-establishment counts",
    "陆家嘴街道": "official office-stock/occupancy plus work-population grid; low marginal value",
    "北外滩街道": "no acquisition recommended; official total is already effectively inside",
    "外滩街道": "no acquisition recommended; official total is already effectively inside",
    "新泾镇": "work-population grid only if purchased as part of a broader package",
}

CONTROL_SPECIFIC_UTILITY = {
    "金桥经济技术开发区": "Largest local spread; industrial/office building functions can test concentration, but only a zone-member roster or workplace grid can overcome the approximate census-zone support.",
    "广中路街道": "Second-largest spread and the largest ordinary-control disagreement; building-level function can directly test whether JRC concentrates too much employment inside the small reached segment.",
    "三林镇": "Mixed residential, logistics, commercial, and institutional land use makes generic building/POI weights weak; repeated work-population observations are the useful discriminator.",
    "张江高科技园区": "Large workforce and boundary uncertainty; R&D/industrial building functions help, but the support is already 95.85% inside and planning-area statistics do not identify the census stratum.",
    "徐家汇街道": "Dense office/retail/education nodes and multiple stations make building-level function and mobile work population highly discriminating across the reach boundary.",
    "天目西路街道": "Rail-station, office, hotel, and wholesale clusters are spatially concentrated; building-level function and work population can distinguish the reached southern/eastern portion.",
    "周浦镇": "Mixed town with new development and industrial/medical anchors; public building classes alone are unlikely to map workplace intensity reliably.",
    "五角场街道": "University, office, retail, and innovation clusters are identifiable at building level; mobile work population would separate them from surrounding residential blocks.",
    "仙霞新村街道": "Office corridors coexist with large residential compounds; mobile work population or insured-establishment points are needed to avoid treating floor area as workplace intensity.",
    "宝山路街道": "Small mixed inner-city control; fine building data can test morphology, but workplace counts remain indirect.",
    "陆家嘴街道": "Official office stock and occupancy strongly validate the employment-center signal, but 97.28% of the support is already inside so numerator leverage is limited.",
    "北外滩街道": "Only 0.26% of the support is outside and the three-model spread is 0.0026 Shanghai points; additional data cannot practically improve the headline range.",
    "外滩街道": "Only 0.70% of the support is outside and the three-model spread is 0.0061 Shanghai points; additional data cannot practically improve the headline range.",
    "新泾镇": "Only 3.34% of a mixed town is inside; mobile work population could verify the small reached edge, but the maximum three-model leverage is only 0.0193 Shanghai points.",
}

OFFICIAL_CONTEXT = {
    "金桥经济技术开发区": {
        "provider": "Pudong New Area Statistics Bureau",
        "title": "Pudong Statistical Yearbook 2025, Table 20-2: Jinqiao ETDZ",
        "url": "https://www.pudong.gov.cn/assets/xls/tjj/2025/%E7%AC%AC%E4%BA%8C%E5%8D%81%E7%AF%87%20%E9%87%8D%E7%82%B9%E5%BC%80%E5%8F%91%E5%8C%BA%E5%92%8C%E8%A1%97%E9%95%87.pdf",
        "year": "2023 and 2024",
        "resolution": "whole reported Jinqiao zone",
        "measure": "end-term employed persons, enterprise registrations, industrial output",
        "usefulness": "Direct aggregate validation: 208,500 employed persons in 2023, close to but not identical with the rounded 203,000 census stratum. No inside/outside or subarea split; table scope is not proven identical to the census accounting stratum.",
    },
    "张江高科技园区": {
        "provider": "Pudong New Area Statistics Bureau",
        "title": "Pudong Statistical Yearbook 2025, Table 20-3: Zhangjiang Area",
        "url": "https://www.pudong.gov.cn/assets/xls/tjj/2025/%E7%AC%AC%E4%BA%8C%E5%8D%81%E7%AF%87%20%E9%87%8D%E7%82%B9%E5%BC%80%E5%8F%91%E5%8C%BA%E5%92%8C%E8%A1%97%E9%95%87.pdf",
        "year": "2023 and 2024",
        "resolution": "whole reported Zhangjiang area",
        "measure": "end-term employed persons and economic indicators",
        "usefulness": "Direct aggregate context, but the reported Zhangjiang area includes multiple planning/industrial areas and is not the 469,000-worker census accounting stratum; no subarea split.",
    },
    "陆家嘴街道": {
        "provider": "Pudong New Area Statistics Bureau",
        "title": "Pudong Statistical Yearbook 2025, Table 20-1: Lujiazui Finance and Trade Zone",
        "url": "https://www.pudong.gov.cn/assets/xls/tjj/2025/%E7%AC%AC%E4%BA%8C%E5%8D%81%E7%AF%87%20%E9%87%8D%E7%82%B9%E5%BC%80%E5%8F%91%E5%8C%BA%E5%92%8C%E8%A1%97%E9%95%87.pdf",
        "year": "2023 and 2024",
        "resolution": "whole Lujiazui Finance and Trade Zone",
        "measure": "228 office buildings, 16.0 million m2 office floor area, 81.9% occupancy in 2023",
        "usefulness": "Strong aggregate office-stock validation, but the finance-and-trade-zone scope is broader than Lujiazui Street and contains no exact-reach subarea split.",
    },
    "广中路街道": {
        "provider": "Hongkou District Government",
        "title": "Shanghai Hongkou High-Tech Industrial Development Zone overview",
        "url": "https://www.shhk.gov.cn/xwzx/002008/002008025/002008025001/20230731/c9cce5bf-ca13-4df4-bfb6-692ec3abeffa.html",
        "year": "2023",
        "resolution": "eight non-contiguous parcels across Hongkou",
        "measure": "68 key office buildings, 34 industrial parks, approximately 20,000 registered enterprises",
        "usefulness": "Identifies office/park anchors relevant to Guangzhong Road, but not employees and not a complete street-level establishment file.",
    },
    "北外滩街道": {
        "provider": "Hongkou District Government",
        "title": "Shanghai Hongkou High-Tech Industrial Development Zone overview",
        "url": "https://www.shhk.gov.cn/xwzx/002008/002008025/002008025001/20230731/c9cce5bf-ca13-4df4-bfb6-692ec3abeffa.html",
        "year": "2023",
        "resolution": "eight non-contiguous parcels across Hongkou",
        "measure": "office-building, industrial-park, and registered-enterprise counts",
        "usefulness": "Useful only as an anchor inventory; it is not a sub-control employment table and the street is already effectively inside for practical purposes.",
    },
    "徐家汇街道": {
        "provider": "Xuhui District Government",
        "title": "Xujiahui subdistrict overview",
        "url": "https://www.xuhui.gov.cn/xhda/xhda/xhbl/xhnj/2021/01/26/9f8086927641192c01773db4784133ea.html",
        "year": "2019 profile, published 2021",
        "resolution": "named commercial, institutional, education, and health anchors",
        "measure": "establishment/anchor inventory and commercial context",
        "usefulness": "Supports validation of major workplace nodes but is old, incomplete, and contains no employment weights.",
    },
    "五角场街道": {
        "provider": "Yangpu District Government",
        "title": "Wujiaochang Innovation and Entrepreneurship Center",
        "url": "https://www.shyp.gov.cn/shypq/kjbjwjccxcyzx/index.html",
        "year": "current page; underlying anchor descriptions are not a 2023 census",
        "resolution": "named innovation/enterprise anchors",
        "measure": "enterprise and innovation-node inventory",
        "usefulness": "Useful for validating cluster locations, not for employment counts or an exhaustive sub-control allocation.",
    },
}

OFFICIAL_PLANNING_CONTEXT = {
    "金桥经济技术开发区": {
        "provider": "Pudong New Area Government",
        "title": "Jinqiao development planning-scope publication",
        "url": "https://www.pudong.gov.cn/zwgk/006003002/2022/302/257742.html",
        "year": "2022 publication",
        "resolution": "reported 29.38 km2 planning scope; no reusable census-stratum vector",
        "measure": "planning scope and land-use interpretation",
        "usefulness": "Authoritative validation/sensitivity interpretation only. The reported planning scope is not assumed equal to the economic-census accounting stratum and differs materially from the selected 2020 statistical support.",
    },
    "张江高科技园区": {
        "provider": "Pudong New Area Government",
        "title": "Zhangjiang planning-scope publication",
        "url": "https://www.pudong.gov.cn/zwgk/14482.gkml_ywl_sthjgl/2025/171/341785.html",
        "year": "2025 publication",
        "resolution": "reported 28.26 km2 planning scope; no reusable census-stratum vector",
        "measure": "planning scope and land-use interpretation",
        "usefulness": "Authoritative validation/sensitivity interpretation only. The reported planning scope is not assumed equal to the economic-census accounting stratum and differs materially from the selected 2020 statistical support.",
    },
}


def _load_controls(repository_root: Path) -> pd.DataFrame:
    path = repository_root / "data/employment/outputs/structural-certainty-controls-50min.csv"
    controls = pd.read_csv(path, dtype={"accounting_stratum_id": "string"})
    if set(TARGET_CONTROLS) - set(controls["control_name"]):
        missing = sorted(set(TARGET_CONTROLS) - set(controls["control_name"]))
        raise ValueError(f"Target controls missing from structural audit: {missing}")
    return controls


def build_control_feasibility(repository_root: Path) -> pd.DataFrame:
    """Return one feasibility record for each named target control."""

    controls = _load_controls(repository_root)
    selected = controls.loc[controls["control_name"].isin(TARGET_CONTROLS)].copy()
    selected["uncertainty_priority_rank_within_14"] = selected[
        "model_max_minus_min_jobs"
    ].rank(method="first", ascending=False).astype(int)
    selected["feasibility_cost_rank_within_14"] = selected["control_name"].map(
        FEASIBILITY_RANK
    )
    selected["feasibility_cost"] = selected["control_name"].map(FEASIBILITY_COST)
    selected["status"] = selected["control_name"].map(STATUS)
    selected["preferred_next_evidence"] = selected["control_name"].map(
        PREFERRED_EVIDENCE
    )
    selected["expected_usefulness"] = selected["control_name"].map(
        CONTROL_SPECIFIC_UTILITY
    )
    selected["public_finer_census_breakdown_found"] = False
    selected["direct_inside_outside_employment_data_found"] = False
    keep = [
        "accounting_stratum_id",
        "district",
        "control_name",
        "control_type",
        "official_control_employment",
        "area_fraction_inside",
        "uniform_jobs_inside",
        "building_jobs_inside",
        "ppml_jobs_inside",
        "model_max_minus_min_jobs",
        "model_difference_shanghai_percentage_points",
        "partial_uncertainty_rank",
        "uncertainty_priority_rank_within_14",
        "feasibility_cost_rank_within_14",
        "feasibility_cost",
        "status",
        "public_finer_census_breakdown_found",
        "direct_inside_outside_employment_data_found",
        "preferred_next_evidence",
        "expected_usefulness",
    ]
    return selected[keep].sort_values("uncertainty_priority_rank_within_14")


def _candidate_row(
    control: pd.Series,
    *,
    source_tier: int,
    source_id: str,
    provider: str,
    title: str,
    url: str,
    year: str,
    resolution: str,
    measure: str,
    access: str,
    license_reuse: str,
    reproducible: str,
    exact_reach: str,
    usefulness: str,
    availability: str,
    independent: bool,
) -> dict[str, object]:
    return {
        "accounting_stratum_id": control["accounting_stratum_id"],
        "district": control["district"],
        "control_name": control["control_name"],
        "source_preference_tier": source_tier,
        "candidate_source_id": source_id,
        "source_provider": provider,
        "source_title": title,
        "source_url": url,
        "year_or_vintage": year,
        "spatial_resolution": resolution,
        "measure_or_proxy": measure,
        "access_method": access,
        "license_or_reuse_restriction": license_reuse,
        "reproducibly_acquirable": reproducible,
        "can_distinguish_exact_reach_inside_outside": exact_reach,
        "expected_usefulness_for_control": usefulness,
        "availability_finding": availability,
        "independent_of_existing_jrc_overture_surface": independent,
    }


def build_source_candidates(repository_root: Path) -> pd.DataFrame:
    """Build the source-by-control evidence ledger required by the audit."""

    controls = build_control_feasibility(repository_root)
    crosswalk = pd.read_csv(
        repository_root / "data/employment/manifests/control-crosswalk-2023.csv",
        dtype={"accounting_stratum_id": "string"},
    ).set_index("accounting_stratum_id")
    rows: list[dict[str, object]] = []
    for _, control in controls.iterrows():
        code = control["accounting_stratum_id"]
        census = crosswalk.loc[code]
        name = control["control_name"]
        rows.append(
            _candidate_row(
                control,
                source_tier=1,
                source_id="district-epc5-publication",
                provider=f"{control['district']} statistics authority",
                title="Fifth National Economic Census main data bulletin, first bulletin",
                url=census["publication_url"],
                year="2023-12-31",
                resolution="street/town or functional-zone aggregate already used as the accounting control",
                measure="legal-entity employment and legal-unit counts; separate district industry table",
                access="public district-government HTML/PDF attachment",
                license_reuse="official publication; cite source; no establishment microdata redistribution",
                reproducible="YES for published aggregates",
                exact_reach="NO",
                usefulness=(
                    "Locks the official control total and universe. Exhaustive table review found no "
                    "public industry-by-control, establishment-location, or sub-control employment table."
                ),
                availability="AVAILABLE, BUT NO FINER PUBLIC BREAKDOWN FOUND",
                independent=True,
            )
        )
        if name in OFFICIAL_CONTEXT:
            source = OFFICIAL_CONTEXT[name]
            rows.append(
                _candidate_row(
                    control,
                    source_tier=2,
                    source_id="official-control-context",
                    provider=source["provider"],
                    title=source["title"],
                    url=source["url"],
                    year=source["year"],
                    resolution=source["resolution"],
                    measure=source["measure"],
                    access="public government HTML/PDF",
                    license_reuse="official publication; citation permitted; no implied license for unpublished microdata",
                    reproducible="YES for published aggregates",
                    exact_reach="NO",
                    usefulness=source["usefulness"],
                    availability="AVAILABLE AS AGGREGATE VALIDATION ONLY",
                    independent=True,
                )
            )
        if name in OFFICIAL_PLANNING_CONTEXT:
            source = OFFICIAL_PLANNING_CONTEXT[name]
            rows.append(
                _candidate_row(
                    control,
                    source_tier=2,
                    source_id="official-planning-scope",
                    provider=source["provider"],
                    title=source["title"],
                    url=source["url"],
                    year=source["year"],
                    resolution=source["resolution"],
                    measure=source["measure"],
                    access="public government HTML/PDF",
                    license_reuse="official publication; citation permitted; no reusable vector license found",
                    reproducible="YES for published scope description; NO for an exact vector",
                    exact_reach="NO",
                    usefulness=source["usefulness"],
                    availability="AVAILABLE FOR VALIDATION, NOT AS CENSUS SUPPORT",
                    independent=True,
                )
            )
        rows.append(
            _candidate_row(
                control,
                source_tier=3,
                source_id="baidu-huiyan-work-population",
                provider="Baidu Maps Huiyan",
                title="Population geography big-data API: work-population grid/custom-area analysis",
                url="https://huiyan.baidu.com/products/popgeoapiservice",
                year="contract-defined; request a stable 2023 historical reference period",
                resolution="grid and arbitrary polygon/custom area; exact cell size disclosed only in contract",
                measure="work population, service population, visitation, and commuting proxy",
                access="commercial inquiry; API/DaaS or licensed offline extract",
                license_reuse="commercial contract; assume no raw redistribution unless expressly licensed",
                reproducible="CONDITIONAL: freeze request polygons, dates, parameters, returned cells, and provider metadata under contract",
                exact_reach="YES if grid cells or exact custom-polygon totals are licensed",
                usefulness=(
                    f"Strongest workplace-specific discriminator for {name}. {CONTROL_SPECIFIC_UTILITY[name]} "
                    "It is not the legal-entity census universe and must only inform within-control shares."
                ),
                availability="COMMERCIAL; PRICE, RETENTION, HISTORICAL COVERAGE, AND REDISTRIBUTION REQUIRE A QUOTE",
                independent=True,
            )
        )
        rows.append(
            _candidate_row(
                control,
                source_tier=4,
                source_id="shanghai-metro-entry-exit",
                provider="Shanghai Municipal Transportation Commission via Shanghai Public Data Open Platform",
                title="Citywide metro station entry and exit passenger volume",
                url="https://data.sh.gov.cn/",
                year="daily or real-time; request representative 2023 weekdays if retained",
                resolution="station point by day or real-time interval",
                measure="passenger entries/exits; not employment and not necessarily AM-peak alightings",
                access="public-data portal download/API; registration or conditional-use application may apply",
                license_reuse="Shanghai public-data terms; cite provider; conditional datasets require a data-use agreement",
                reproducible="CONDITIONAL on dataset access and historical retention",
                exact_reach="NO: station catchments cross control/reach boundaries and trips are multi-purpose",
                usefulness=(
                    f"Independent validation signal for workplace-center timing in {name}, never an employment count. "
                    "No public official AM-peak alighting table was located in this audit."
                ),
                availability="OFFICIAL STATION FLOW DATASET EXISTS; REQUIRED AM-PEAK/HISTORICAL DETAIL NOT CONFIRMED",
                independent=True,
            )
        )
        rows.append(
            _candidate_row(
                control,
                source_tier=5,
                source_id="official-registry-establishments",
                provider="Shanghai Administration for Market Regulation / GSXT",
                title="Shanghai enterprise registration machine-readable basic archives",
                url="https://fw.scjgj.sh.gov.cn/achieve_outer/apply/notice",
                year="registry address/status current at acquisition",
                resolution="establishment registered-address point after geocoding",
                measure="enterprise name, registered address, status, registration metadata, and business scope",
                access="official record-by-record identity-verified lookup through Shanghai's one-stop government portal",
                license_reuse="public inspection right; no bulk-download or raw-redistribution license identified",
                reproducible="NO at control scale without an official bulk extract; record-by-record lookup is auditable but impractical",
                exact_reach="YES geometrically after geocoding, but registered address may not be the workplace",
                usefulness=(
                    f"Potential establishment-location validation for {name}; no public bulk enumeration or employment weight, and registered-address bias remains."
                ),
                availability="OFFICIAL RECORD-BY-RECORD ONLY; NOT PRACTICAL AS A COMPLETE CONTROL DATASET",
                independent=True,
            )
        )
        rows.append(
            _candidate_row(
                control,
                source_tier=5,
                source_id="qichacha-insured-establishments",
                provider="Qichacha Open Platform",
                title="Enterprise risk-scan API with industry, address, branches, and insured count",
                url="https://openapi.qcc.com/dataApi/736",
                year="latest enterprise record and annual-report insured count available at acquisition",
                resolution="enterprise registered-address point after geocoding",
                measure="establishments, industry, branches, registered address, and reported insured count",
                access="commercial JSON API; enterprise-verified account and use-case approval",
                license_reuse="commercial contract; 6 RMB/query listed at audit date; assume no raw redistribution without written permission",
                reproducible="CONDITIONAL: freeze enterprise universe, API version, query date, raw responses, geocoder, and missingness/deduplication ledgers",
                exact_reach="YES geometrically after geocoding, but registered address and insured enrollment may differ from workplace",
                usefulness=(
                    f"Potential employment-weighted point proxy for {name}; incomplete insured counts, headquarters/branch duplication, "
                    "centralized social-insurance enrollment, and registered-address bias require normalization to the official control total."
                ),
                availability="COMMERCIAL; ENUMERATION AND PER-RECORD COST MAKE A TARGETED PILOT PREFERABLE TO CITYWIDE ACQUISITION",
                independent=True,
            )
        )
        rows.append(
            _candidate_row(
                control,
                source_tier=6,
                source_id="cmab-building-function-volume",
                provider="Tsinghua University researchers / Figshare",
                title="CMAB: Multi-Attribute Building Dataset of China, version 7",
                url="https://figshare.com/articles/dataset/CMAB-The_World_s_First_National-Scale_Multi-Attribute_Building_Dataset/27992417",
                year="dataset 2025; input imagery primarily 2022-2024",
                resolution="individual building polygon with height, volume, and predicted function",
                measure="office/industrial/commercial/public/residential building function and building volume",
                access="public Figshare download; subset Shanghai after freezing version/checksum",
                license_reuse="CC BY 4.0 with attribution",
                reproducible="YES; 15.81 GB national archive, versioned download",
                exact_reach="YES at building-polygon level",
                usefulness=(
                    f"{CONTROL_SPECIFIC_UTILITY[name]} Building function is predicted and partly derived from map AOI/POI; "
                    "it is an independent high-resolution morphology check, not a workplace count."
                ),
                availability="PUBLICLY AVAILABLE",
                independent=True,
            )
        )
        rows.append(
            _candidate_row(
                control,
                source_tier=6,
                source_id="global-building-atlas",
                provider="Technical University of Munich / GlobalBuildingAtlas",
                title="GlobalBuildingAtlas building polygons, heights, and LoD1 models",
                url="https://source.coop/tge-labs/globalbuildingatlas-lod1",
                year="2025 release; source imagery varies",
                resolution="individual building polygon and height",
                measure="building footprint, height, and volume; no workplace function",
                access="public cloud-hosted Parquet/GeoJSON distribution",
                license_reuse="polygon component published as ODbL; verify component-specific terms before redistribution",
                reproducible="YES with frozen partitions/version/checksum",
                exact_reach="YES at building-polygon level",
                usefulness=(
                    f"Independent geometry/height cross-check for {name}; weaker than CMAB because it lacks building function and employment."
                ),
                availability="PUBLICLY AVAILABLE",
                independent=True,
            )
        )
        rows.append(
            _candidate_row(
                control,
                source_tier=6,
                source_id="existing-jrc-overture-baseline",
                provider="European Commission JRC and Overture Maps Foundation",
                title="Existing JRC non-residential built volume and Overture Places inputs",
                url="https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2023A_GHS_BUILT_V",
                year="JRC 2020; Overture release 2026-07-22.0",
                resolution="100 m built-volume grid and place points",
                measure="non-residential built volume and categorized place confidence",
                access="already frozen in PR #16 source pipeline",
                license_reuse="existing source-manifest terms and attribution",
                reproducible="YES from the existing pipeline manifest",
                exact_reach="YES through existing 100 m partial-cell and point geometry",
                usefulness=(
                    f"Existing baseline for {name}; it cannot count as independent improvement because it already generates two of the compared allocation surfaces."
                ),
                availability="ALREADY USED; NOT NEW EVIDENCE",
                independent=False,
            )
        )
    result = pd.DataFrame(rows)
    return result.sort_values(
        ["control_name", "source_preference_tier", "candidate_source_id"]
    ).reset_index(drop=True)


def _shrink_selected(
    totals: np.ndarray,
    selected: pd.DataFrame,
    shrink_fraction: float,
) -> np.ndarray:
    adjusted = totals.copy()
    for _, row in selected.iterrows():
        values = row[MODEL_COLUMNS].to_numpy(dtype=float)
        center = float(values.mean())
        shrunk = center + (1.0 - shrink_fraction) * (values - center)
        adjusted += shrunk - values
    return adjusted


def build_portfolio_scenarios(repository_root: Path) -> pd.DataFrame:
    """Quantify current-range reduction without changing any allocation result.

    The 30% and 70% scenarios are explicit feasibility assumptions, not observed
    error rates or confidence intervals.  The 100% scenario is an oracle ceiling.
    """

    controls = _load_controls(repository_root)
    partial = controls.loc[
        controls["support_classification"] == "materially_partially_intersected"
    ].sort_values("partial_uncertainty_rank")
    totals = controls[MODEL_COLUMNS].sum().to_numpy(dtype=float)
    baseline_width_pp = float(np.ptp(totals) / CITY_EMPLOYMENT * 100.0)
    scenarios = [
        (
            "open_building_and_validation",
            0.30,
            "Selected-control model deviations shrink 30% toward their three-model mean; represents CMAB plus official/metro validation without workplace counts.",
        ),
        (
            "contracted_mobile_or_insured_establishments",
            0.70,
            "Selected-control model deviations shrink 70% toward their three-model mean; represents a well-documented workplace grid or insured-establishment census that still differs from the legal-entity universe.",
        ),
        (
            "oracle_perfect_inside_outside_share",
            1.00,
            "Selected controls have a perfectly known inside/outside share; this is a mathematical ceiling, not a forecast.",
        ),
    ]
    rows: list[dict[str, object]] = []
    for count in (5, 10, 20):
        selected = partial.head(count)
        additive_pp = float(
            selected["model_difference_shanghai_percentage_points"].sum()
        )
        names = " | ".join(selected["control_name"].tolist())
        for scenario, shrink, assumption in scenarios:
            adjusted = _shrink_selected(totals, selected, shrink)
            remaining = float(np.ptp(adjusted) / CITY_EMPLOYMENT * 100.0)
            rows.append(
                {
                    "portfolio_size": count,
                    "selected_by": "current control-level max-minus-min spread rank",
                    "controls": names,
                    "scenario": scenario,
                    "selected_control_additive_spread_percentage_points": additive_pp,
                    "shrink_fraction_assumption": shrink,
                    "baseline_aggregate_model_range_percentage_points": baseline_width_pp,
                    "remaining_aggregate_model_range_percentage_points": remaining,
                    "aggregate_range_reduction_percentage_points": baseline_width_pp
                    - remaining,
                    "assumption_note": assumption,
                }
            )
    return pd.DataFrame(rows)


def write_outputs(repository_root: Path) -> None:
    output_dir = repository_root / "data/employment/outputs"
    manifest_dir = repository_root / "data/employment/manifests"
    build_control_feasibility(repository_root).to_csv(
        output_dir / "workplace-data-feasibility-controls.csv", index=False
    )
    build_portfolio_scenarios(repository_root).to_csv(
        output_dir / "workplace-data-feasibility-portfolios.csv", index=False
    )
    build_source_candidates(repository_root).to_csv(
        manifest_dir / "workplace-source-candidates.csv", index=False
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    write_outputs(args.repository_root.resolve())


if __name__ == "__main__":
    main()
