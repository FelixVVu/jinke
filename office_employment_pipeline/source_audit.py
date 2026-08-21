"""Extract official 2023 district-by-industry employment controls.

This module is intentionally limited to source acquisition, classification, and
accounting validation.  It does not create a spatial surface, intersect a reach,
or modify the existing employment benchmark.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd


OFFICIAL_SOURCE_URL = (
    "https://tjj.sh.gov.cn/tjnj/jjpcnj2023/zk/html/A1-09.xls"
)
INDICATOR_DEFINITION_URL = (
    "https://tjj.sh.gov.cn/tjnj/jjpcnj2023/zk/html/zba01.pdf"
)
INDUSTRY_CLASSIFICATION_URL = (
    "https://www.stats.gov.cn/xxgk/tjbz/gjtjbz/201710/"
    "t20171017_1758922.html"
)
SOURCE_SHA256 = "b217fb6d1fdacf06cfd68e46b93c9f50536e566a3575581add57393a1c9b3d7a"
SOURCE_BYTES = 51_200
SOURCE_TABLE = "1-9  按行业(大类)、地区分组的法人单位从业人员数"
REFERENCE_DATE = "2023-12-31"
AUDIT_RETRIEVAL_DATE = "2026-08-21"
CITY_EMPLOYMENT = 13_099_795
EMPLOYMENT_UNIVERSE = (
    "people employed by Shanghai legal entities at 2023-12-31; "
    "individual-business employment excluded"
)

DISTRICTS = [
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
]

# These rows are mutually exclusive.  Section L is deliberately not selected as
# a whole because it would double count code 72 and would add code 71 rental.
INDUSTRY_SCOPE = [
    {
        "industry_code": "I",
        "industry_name": "信息传输、软件和信息技术服务业",
        "classification_level": "section",
        "core_office": True,
        "broad_office": True,
        "rationale": "Digital, software, telecommunications, and information-service employers are predominantly office/technical-workplace oriented.",
        "mixed_activity_warning": "Telecommunications field operations and infrastructure roles are included because the official district table cannot separate occupations.",
    },
    {
        "industry_code": "J",
        "industry_name": "金融业",
        "classification_level": "section",
        "core_office": True,
        "broad_office": True,
        "rationale": "Banking, securities, insurance, and other financial services are archetypal office-oriented activities.",
        "mixed_activity_warning": "Branch-counter, field-sales, and support roles are included; the measure is industry based, not occupation based.",
    },
    {
        "industry_code": "72",
        "industry_name": "商务服务业",
        "classification_level": "division",
        "core_office": False,
        "broad_office": True,
        "rationale": "Head-office management, consulting, legal, accounting, advertising, and related activities justify inclusion in Broad.",
        "mixed_activity_warning": "Labor dispatch, security, cleaning, conference, travel, and other non-office services cannot be separated at district grain, so code 72 is excluded from Core.",
    },
    {
        "industry_code": "M",
        "industry_name": "科学研究和技术服务业",
        "classification_level": "section",
        "core_office": True,
        "broad_office": True,
        "rationale": "Research, engineering, design, testing, and professional technical services are office/laboratory oriented.",
        "mixed_activity_warning": "Laboratory, survey, inspection, and field technical roles are included.",
    },
    {
        "industry_code": "K",
        "industry_name": "房地产业",
        "classification_level": "section",
        "core_office": False,
        "broad_office": True,
        "rationale": "Development, brokerage, leasing, and property administration add a broader commercial-office universe.",
        "mixed_activity_warning": "Property-management, maintenance, and on-site service workers make the section too mixed for Core.",
    },
    {
        "industry_code": "P",
        "industry_name": "教育",
        "classification_level": "section",
        "core_office": False,
        "broad_office": True,
        "rationale": "Education adds professional and administrative institutional workplaces to the Broad definition.",
        "mixed_activity_warning": "Schools and campuses are not conventional offices; teachers and support workers are included.",
    },
    {
        "industry_code": "Q",
        "industry_name": "卫生和社会工作",
        "classification_level": "section",
        "core_office": False,
        "broad_office": True,
        "rationale": "Health and social work add major professional/institutional workplaces to Broad.",
        "mixed_activity_warning": "Hospitals, clinics, care institutions, and clinical/support occupations are not conventional offices.",
    },
    {
        "industry_code": "R",
        "industry_name": "文化、体育和娱乐业",
        "classification_level": "section",
        "core_office": False,
        "broad_office": True,
        "rationale": "Media, publishing, cultural, and creative organizations form part of a broad professional-workplace universe.",
        "mixed_activity_warning": "Sports venues, performance, and entertainment operations are included and may not be office based.",
    },
    {
        "industry_code": "S",
        "industry_name": "公共管理、社会保障和社会组织",
        "classification_level": "section",
        "core_office": False,
        "broad_office": True,
        "rationale": "Government and social-organization administration are office/institutional workplaces included in Broad.",
        "mixed_activity_warning": "Public-safety, community, and other non-desk government/social-organization roles are included.",
    },
]


def download_official_workbook(url: str = OFFICIAL_SOURCE_URL) -> bytes:
    """Download the official workbook with headers accepted by the source host."""

    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://tjj.sh.gov.cn/",
        },
    )
    with urlopen(request, timeout=60) as response:
        return response.read()


def _validated_workbook(workbook: bytes) -> pd.DataFrame:
    digest = hashlib.sha256(workbook).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError(
            f"Official workbook hash changed: expected {SOURCE_SHA256}, found {digest}."
        )
    if len(workbook) != SOURCE_BYTES:
        raise ValueError(
            f"Official workbook size changed: expected {SOURCE_BYTES}, found {len(workbook)}."
        )
    sheet = pd.read_excel(BytesIO(workbook), header=None)
    if sheet.iloc[0, 0] != SOURCE_TABLE:
        raise ValueError(f"Unexpected Table 1-9 title: {sheet.iloc[0, 0]!r}")
    observed_districts = sheet.iloc[3, 3:19].tolist()
    if observed_districts != DISTRICTS:
        raise ValueError(f"Unexpected district columns: {observed_districts}")
    return sheet


def extract_official_controls(
    workbook: bytes,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Extract selected district-industry rows and Core/Broad summaries."""

    sheet = _validated_workbook(workbook)
    total_row = sheet.loc[sheet.iloc[:, 0] == "总  计"]
    if len(total_row) != 1:
        raise ValueError("Expected one all-industry total row.")
    total_row = total_row.iloc[0]
    if int(total_row.iloc[2]) != CITY_EMPLOYMENT:
        raise ValueError("Official city total does not match 13,099,795.")
    district_totals = {
        district: int(total_row.iloc[column])
        for column, district in enumerate(DISTRICTS, start=3)
    }
    if sum(district_totals.values()) != CITY_EMPLOYMENT:
        raise ValueError("The 16 district totals do not reconcile to the city total.")

    scope = pd.DataFrame(INDUSTRY_SCOPE)
    if scope["industry_code"].duplicated().any():
        raise ValueError("Office-industry scope contains a duplicate accounting row.")
    if (scope["core_office"] & ~scope["broad_office"]).any():
        raise ValueError("Core must be a strict subset of Broad.")

    records: list[dict[str, object]] = []
    city_totals: dict[str, int] = {}
    for definition in INDUSTRY_SCOPE:
        code = definition["industry_code"]
        selected = sheet.loc[sheet.iloc[:, 1].astype(str) == code]
        if len(selected) != 1:
            raise ValueError(f"Expected one official row for industry code {code}.")
        row = selected.iloc[0]
        observed_name = str(row.iloc[0]).strip()
        if observed_name != definition["industry_name"]:
            raise ValueError(
                f"Industry-name mismatch for {code}: {observed_name!r}."
            )
        city_total = int(row.iloc[2])
        city_totals[code] = city_total
        district_values = pd.to_numeric(row.iloc[3:19], errors="raise")
        if district_values.isna().any():
            raise ValueError(f"Selected industry {code} has a blank district cell.")
        if int(district_values.sum()) != city_total:
            raise ValueError(f"Districts do not reconcile for industry {code}.")
        for column, district in enumerate(DISTRICTS, start=3):
            employment = int(row.iloc[column])
            records.append(
                {
                    "district": district,
                    "industry_code": code,
                    "industry_name": definition["industry_name"],
                    "classification_level": definition["classification_level"],
                    "core_office": definition["core_office"],
                    "broad_office": definition["broad_office"],
                    "district_industry_employment": employment,
                    "official_city_industry_employment": city_total,
                    "district_share_of_city_industry_percentage": employment
                    / city_total
                    * 100.0,
                    "reference_date": REFERENCE_DATE,
                    "employment_universe": EMPLOYMENT_UNIVERSE,
                    "source_table": SOURCE_TABLE,
                    "source_url": OFFICIAL_SOURCE_URL,
                }
            )
    detail = pd.DataFrame(records)

    summary_rows: list[dict[str, object]] = []
    for district in DISTRICTS:
        district_rows = detail.loc[detail["district"] == district]
        core = int(
            district_rows.loc[
                district_rows["core_office"], "district_industry_employment"
            ].sum()
        )
        broad = int(
            district_rows.loc[
                district_rows["broad_office"], "district_industry_employment"
            ].sum()
        )
        total = district_totals[district]
        summary_rows.append(
            {
                "district": district,
                "official_all_industry_employment": total,
                "core_office_employment": core,
                "core_share_of_district_employment_percentage": core
                / total
                * 100.0,
                "core_share_of_shanghai_all_industry_percentage": core
                / CITY_EMPLOYMENT
                * 100.0,
                "broad_office_employment": broad,
                "broad_share_of_district_employment_percentage": broad
                / total
                * 100.0,
                "broad_share_of_shanghai_all_industry_percentage": broad
                / CITY_EMPLOYMENT
                * 100.0,
                "reference_date": REFERENCE_DATE,
                "employment_universe": EMPLOYMENT_UNIVERSE,
            }
        )
    district_summary = pd.DataFrame(summary_rows)
    core_total = int(district_summary["core_office_employment"].sum())
    broad_total = int(district_summary["broad_office_employment"].sum())
    if core_total != sum(
        city_totals[row["industry_code"]]
        for row in INDUSTRY_SCOPE
        if row["core_office"]
    ):
        raise ValueError("Core district controls do not reconcile to industry totals.")
    if broad_total != sum(city_totals.values()):
        raise ValueError("Broad district controls do not reconcile to industry totals.")
    if not (0 < core_total < broad_total < CITY_EMPLOYMENT):
        raise ValueError("Invalid Core/Broad nesting or totals.")
    city_summary = {
        "schema_version": 1,
        "reference_date": REFERENCE_DATE,
        "employment_universe": EMPLOYMENT_UNIVERSE,
        "official_all_industry_employment": CITY_EMPLOYMENT,
        "core_office_employment": core_total,
        "core_share_of_shanghai_all_industry_percentage": core_total
        / CITY_EMPLOYMENT
        * 100.0,
        "broad_office_employment": broad_total,
        "broad_share_of_shanghai_all_industry_percentage": broad_total
        / CITY_EMPLOYMENT
        * 100.0,
        "district_count": len(DISTRICTS),
        "selected_industry_row_count": len(INDUSTRY_SCOPE),
        "core_industry_rows": [
            row["industry_code"] for row in INDUSTRY_SCOPE if row["core_office"]
        ],
        "broad_industry_rows": [
            row["industry_code"] for row in INDUSTRY_SCOPE if row["broad_office"]
        ],
        "source_url": OFFICIAL_SOURCE_URL,
        "source_sha256": SOURCE_SHA256,
        "sufficiency_decision": "PROCEED",
        "sufficiency_scope": (
            "sufficient as official district calibration controls for an "
            "industry-based office-oriented benchmark; not occupation-level or "
            "fine-geographic observed employment"
        ),
    }
    return detail, district_summary, city_summary


def write_outputs(repository_root: Path, workbook: bytes) -> None:
    """Write the separate source-audit workstream artifacts."""

    detail, district_summary, city_summary = extract_official_controls(workbook)
    manifest_dir = repository_root / "data/office_employment/manifests"
    intermediate_dir = repository_root / "data/office_employment/intermediate"
    output_dir = repository_root / "data/office_employment/outputs"
    for directory in (manifest_dir, intermediate_dir, output_dir):
        directory.mkdir(parents=True, exist_ok=True)

    scope = pd.DataFrame(INDUSTRY_SCOPE)
    city_industry = detail[
        [
            "industry_code",
            "official_city_industry_employment",
        ]
    ].drop_duplicates()
    scope = scope.merge(city_industry, on="industry_code", validate="one_to_one")
    scope["share_of_shanghai_all_industry_employment_percentage"] = (
        scope["official_city_industry_employment"] / CITY_EMPLOYMENT * 100.0
    )
    scope["source_table"] = SOURCE_TABLE
    scope["source_url"] = OFFICIAL_SOURCE_URL
    scope.to_csv(manifest_dir / "industry-scope-2023.csv", index=False)
    pd.DataFrame(
        [
            {
                "source_id": "shanghai-epc5-a1-09",
                "publisher": "Shanghai Municipal Statistics Bureau",
                "title": SOURCE_TABLE,
                "reference_date": REFERENCE_DATE,
                "retrieval_date": AUDIT_RETRIEVAL_DATE,
                "url": OFFICIAL_SOURCE_URL,
                "file_format": "XLS",
                "file_bytes": SOURCE_BYTES,
                "sha256": SOURCE_SHA256,
                "license_or_terms": "official statistical publication; extracted facts retained with citation; raw workbook not redistributed",
                "coverage": "16 Shanghai districts × 97 industry divisions, plus section and city totals",
                "used_for": "official district-by-industry office-employment calibration controls",
            },
            {
                "source_id": "shanghai-epc5-indicator-definitions",
                "publisher": "Shanghai Municipal Statistics Bureau",
                "title": "Shanghai Economic Census Yearbook 2023: main indicator definitions",
                "reference_date": REFERENCE_DATE,
                "retrieval_date": AUDIT_RETRIEVAL_DATE,
                "url": INDICATOR_DEFINITION_URL,
                "file_format": "PDF",
                "file_bytes": "",
                "sha256": "",
                "license_or_terms": "official statistical publication; cited, not redistributed",
                "coverage": "legal entity and year-end employment definitions",
                "used_for": "employment-universe interpretation",
            },
            {
                "source_id": "nbs-gbt-4754-2017",
                "publisher": "National Bureau of Statistics of China",
                "title": "Industrial Classification for National Economic Activities (GB/T 4754-2017, as amended)",
                "reference_date": "2017 standard; 2019 amendment",
                "retrieval_date": AUDIT_RETRIEVAL_DATE,
                "url": INDUSTRY_CLASSIFICATION_URL,
                "file_format": "HTML with official attachments",
                "file_bytes": "",
                "sha256": "",
                "license_or_terms": "official national statistical standard; cited, not redistributed",
                "coverage": "industry sections and two-digit divisions",
                "used_for": "Core and Broad industry-code definitions",
            },
        ]
    ).to_csv(manifest_dir / "source-manifest.csv", index=False)
    detail.to_csv(
        intermediate_dir / "district-industry-employment-2023.csv", index=False
    )
    district_summary.to_csv(
        output_dir / "district-office-employment-controls-2023.csv", index=False
    )
    (output_dir / "city-office-employment-summary-2023.json").write_text(
        json.dumps(city_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--input-xls", type=Path)
    args = parser.parse_args()
    workbook = (
        args.input_xls.read_bytes()
        if args.input_xls is not None
        else download_official_workbook()
    )
    write_outputs(args.repository_root.resolve(), workbook)


if __name__ == "__main__":
    main()
