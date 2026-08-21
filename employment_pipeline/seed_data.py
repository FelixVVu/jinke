"""Immutable official controls transcribed from the Gate 1 source audit.

This module is only used to build the checked-in CSV manifests. Runtime code reads
those manifests and never fuzzy-matches a statistical name to a geometry.
"""

from __future__ import annotations

from typing import Any

from .config import EMPLOYMENT_UNIVERSE, REFERENCE_DATE

CITY_TABLE_URL = "https://tjj.sh.gov.cn/tjnj/jjpcnj2023/zk/html/A1-02.xls"
CODE_REFERENCE_URL = (
    "https://www.stats.gov.cn/hd/lyzx/zxgk/202401/t20240104_1946235.html"
)

DISTRICTS: tuple[tuple[str, str, int, bool], ...] = (
    ("黄浦区", "Huangpu", 712_613, True),
    ("徐汇区", "Xuhui", 1_027_746, True),
    ("长宁区", "Changning", 602_150, True),
    ("静安区", "Jing'an", 973_987, True),
    ("普陀区", "Putuo", 524_969, True),
    ("虹口区", "Hongkou", 409_389, True),
    ("杨浦区", "Yangpu", 510_562, True),
    ("闵行区", "Minhang", 1_278_262, False),
    ("宝山区", "Baoshan", 766_004, False),
    ("嘉定区", "Jiading", 873_958, False),
    ("浦东新区", "Pudong", 2_879_157, True),
    ("金山区", "Jinshan", 393_752, False),
    ("松江区", "Songjiang", 852_240, False),
    ("青浦区", "Qingpu", 549_805, False),
    ("奉贤区", "Fengxian", 583_748, False),
    ("崇明区", "Chongming", 161_453, False),
)

SOURCE_INFO: dict[str, dict[str, str]] = {
    "黄浦区": {
        "url": "https://www.shhuangpu.gov.cn/uploadfile/fcba008c-ee33-44f4-bfe0-8cbb16faaf83/%E4%B8%8A%E6%B5%B7%E5%B8%82%E9%BB%84%E6%B5%A6%E5%8C%BA%E7%AC%AC%E4%BA%94%E6%AC%A1%E5%85%A8%E5%9B%BD%E7%BB%8F%E6%B5%8E%E6%99%AE%E6%9F%A5%E4%B8%BB%E8%A6%81%E6%95%B0%E6%8D%AE%E5%85%AC%E6%8A%A5%EF%BC%88%E6%9C%80%E7%BB%88%E5%8F%91%E5%B8%83%E7%A8%BF%EF%BC%891%E5%8F%B7.pdf",
        "unit": "persons",
        "rounding": "exact person rows",
        "exclusion": "enterprise legal-unit data returned by financial regulators",
        "table": "Table 1-5",
    },
    "徐汇区": {
        "url": "https://www.xuhui.gov.cn/xxgk/portal/article/detail?id=8a4c0c06982a9c100198f528792809df",
        "unit": "10,000 persons, two decimals",
        "rounding": "100-person display increment; each row interval is [nominal-50, nominal+50)",
        "exclusion": "construction and finance; construction processing-location adjustment applies",
        "table": "Table 1-5, printed/PDF pages 5-6",
    },
    "长宁区": {
        "url": "https://zwgk.shcn.gov.cn/xxgk/zdgzlsqk-zw/2025/211/78163.html",
        "unit": "persons",
        "rounding": "exact person rows",
        "exclusion": "directly managed financial units",
        "table": "Table 1-5",
    },
    "静安区": {
        "url": "https://www.jingan.gov.cn/main/7a2356e7-0acd-4df3-938e-dcd05244ea81/a9e09839-63a5-45f3-8eb3-9d56a10e42af/%E4%B8%8A%E6%B5%B7%E5%B8%82%E9%9D%99%E5%AE%89%E5%8C%BA%E7%AC%AC%E4%BA%94%E6%AC%A1%E7%BB%8F%E6%B5%8E%E6%99%AE%E6%9F%A5%E4%B8%BB%E8%A6%81%E6%95%B0%E6%8D%AE%E5%85%AC%E6%8A%A5%EF%BC%88%E7%AC%AC%E4%B8%80%E5%8F%B7%EF%BC%89.pdf",
        "unit": "10,000 persons, one decimal",
        "rounding": "1,000-person display increment; each row interval is [nominal-500, nominal+500)",
        "exclusion": "finance",
        "table": "geographic employment table",
    },
    "普陀区": {
        "url": "https://www.shpt.gov.cn/zhengwu/pcgg-pttj/2025/203/197385.html",
        "unit": "10,000 persons, one decimal",
        "rounding": "1,000-person display increment; each row interval is [nominal-500, nominal+500)",
        "exclusion": "finance",
        "table": "geographic employment table",
    },
    "虹口区": {
        "url": "https://www.shhk.gov.cn/shhk-zwgk/rest/frame/base/attach/attachAction/getContent?attachGuid=3a3b3cb4-8b7b-4a87-8472-ea58b4f2a6cc&isCommondto=true",
        "unit": "persons",
        "rounding": "exact person rows",
        "exclusion": "some legal-entity workers are not subdivided; construction processing-location adjustment applies",
        "table": "geographic employment table",
    },
    "杨浦区": {
        "url": "https://www.shyp.gov.cn/zhengwu/zwgk-yptj/2025/242/3eea1189dfca9d78d3190a204c75a74c.html",
        "unit": "persons",
        "rounding": "exact person rows",
        "exclusion": "finance and national-statistical-channel construction",
        "table": "geographic employment table",
    },
    "浦东新区": {
        "url": "https://www.pudong.gov.cn/zwgk/tjj_gkml_ywl_tjsj_gb/2025/295/347226.html",
        "unit": "10,000 persons, one decimal",
        "rounding": "1,000-person display increment; constrained by three category subtotals",
        "exclusion": "some legal-entity workers are not subdivided",
        "table": "geographic employment table; street, town, and development-zone subtotals",
    },
}


def _row(
    district: str,
    code: str,
    official_name: str,
    employment: int,
    osm_relation_id: int | None,
    control_type: str,
    *,
    published_name: str | None = None,
    rounding_increment: int = 1,
    table_reference: str | None = None,
    subtotal_group: str = "ordinary",
    crosswalk_note: str = "exact official-name match",
) -> dict[str, Any]:
    half = rounding_increment // 2 if rounding_increment > 1 else 0
    source = SOURCE_INFO[district]
    return {
        "district": district,
        "official_control_code_2023": code,
        "official_control_name_2023": official_name,
        "published_control_label": published_name or official_name,
        "control_type": control_type,
        "accounting_stratum_id": code,
        "employment_nominal": employment,
        "employment_reconciled": employment,
        "employment_rounding_lower": employment - half,
        "employment_rounding_upper_exclusive": employment + half if half else employment,
        "rounding_increment_people": rounding_increment,
        "bulletin_unit": source["unit"],
        "bulletin_rounding_note": source["rounding"],
        "subtotal_group": subtotal_group,
        "table_page_reference": table_reference or source["table"],
        "employment_universe": EMPLOYMENT_UNIVERSE,
        "reference_date": REFERENCE_DATE,
        "individual_business_included": False,
        "geographic_table_exclusions": source["exclusion"],
        "publication_url": source["url"],
        "official_code_reference_url": CODE_REFERENCE_URL,
        "osm_relation_id": osm_relation_id,
        "geometry_source": "OpenStreetMap" if osm_relation_id else "Ruiduobao 2020 statistical polygon (restricted redistribution)",
        "geometry_is_approximate": True,
        "name_crosswalk_note": crosswalk_note,
    }


CONTROLS: tuple[dict[str, Any], ...] = tuple(
    [
        _row("黄浦区", "310101002000", "南京东路街道", 101_851, 12236005, "street"),
        _row("黄浦区", "310101013000", "外滩街道", 113_352, 12235857, "street"),
        _row("黄浦区", "310101015000", "半淞园路街道", 30_334, 12235902, "street"),
        _row("黄浦区", "310101017000", "小东门街道", 126_442, 12235905, "street"),
        _row("黄浦区", "310101018000", "豫园街道", 19_681, 12235904, "street"),
        _row("黄浦区", "310101019000", "老西门街道", 16_323, 12235903, "street"),
        _row("黄浦区", "310101020000", "五里桥街道", 45_959, 12235959, "street"),
        _row("黄浦区", "310101021000", "打浦桥街道", 49_936, 12235958, "street"),
        _row("黄浦区", "310101022000", "淮海中路街道", 81_561, 12236003, "street"),
        _row("黄浦区", "310101023000", "瑞金二路街道", 52_840, 12236004, "street"),
    ]
    + [
        _row("徐汇区", code, name, value, osm, kind, rounding_increment=100, table_reference=page)
        for code, name, value, osm, kind, page in (
            ("310104003000", "天平路街道", 57_800, 13469980, "street", "Table 1-5, printed/PDF page 5"),
            ("310104004000", "湖南路街道", 48_700, 13469979, "street", "Table 1-5, printed/PDF page 5"),
            ("310104007000", "斜土路街道", 29_800, 13470053, "street", "Table 1-5, printed/PDF page 5"),
            ("310104008000", "枫林路街道", 56_800, 13470052, "street", "Table 1-5, printed/PDF page 5"),
            ("310104010000", "长桥街道", 20_700, 13470589, "street", "Table 1-5, printed/PDF page 5"),
            ("310104011000", "田林街道", 75_600, 13470318, "street", "Table 1-5, printed/PDF page 5"),
            ("310104012000", "虹梅路街道", 262_100, 13470463, "street", "Table 1-5, printed/PDF page 5"),
            ("310104013000", "康健新村街道", 15_900, 13470479, "street", "Table 1-5, printed/PDF page 6"),
            ("310104014000", "徐家汇街道", 216_300, 13469990, "street", "Table 1-5, printed/PDF page 6"),
            ("310104015000", "凌云路街道", 12_200, 13470540, "street", "Table 1-5, printed/PDF page 6"),
            ("310104016000", "龙华街道", 59_600, 13470146, "street", "Table 1-5, printed/PDF page 6"),
            ("310104017000", "漕河泾街道", 88_600, 13470278, "street", "Table 1-5, printed/PDF page 6"),
            ("310104103000", "华泾镇", 10_300, 13470658, "town", "Table 1-5, printed/PDF page 6"),
        )
    ]
    + [
        _row("长宁区", code, name, value, osm, kind)
        for code, name, value, osm, kind in (
            ("310105001000", "华阳路街道", 48_926, 13469230, "street"),
            ("310105002000", "江苏路街道", 37_808, 13469138, "street"),
            ("310105004000", "新华路街道", 52_426, 13469094, "street"),
            ("310105005000", "周家桥街道", 25_426, 13469231, "street"),
            ("310105006000", "天山路街道", 70_756, 13469232, "street"),
            ("310105008000", "仙霞新村街道", 20_827, 13469351, "street"),
            ("310105009000", "虹桥街道", 84_297, 13469352, "street"),
            ("310105010000", "程家桥街道", 101_760, 14184034, "street"),
            ("310105011000", "北新泾街道", 6_332, 14184083, "street"),
            ("310105102000", "新泾镇", 148_418, 14184082, "town"),
        )
    ]
    + [
        _row("静安区", code, name, value, osm, kind, rounding_increment=1000)
        for code, name, value, osm, kind in (
            ("310106006000", "江宁路街道", 35_000, 14186018, "street"),
            ("310106011000", "石门二路街道", 47_000, 14186017, "street"),
            ("310106012000", "南京西路街道", 152_000, 14186016, "street"),
            ("310106013000", "静安寺街道", 80_000, 14186014, "street"),
            ("310106014000", "曹家渡街道", 48_000, 14186015, "street"),
            ("310106015000", "天目西路街道", 161_000, 14186013, "street"),
            ("310106016000", "北站街道", 65_000, 14186012, "street"),
            ("310106017000", "宝山路街道", 21_000, 14186011, "street"),
            ("310106018000", "共和新路街道", 31_000, 14186010, "street"),
            ("310106019000", "大宁路街道", 115_000, 14186009, "street"),
            ("310106020000", "彭浦新村街道", 17_000, 14186008, "street"),
            ("310106021000", "临汾路街道", 5_000, 14186007, "street"),
            ("310106022000", "芷江西路街道", 28_000, 14186006, "street"),
            ("310106100000", "彭浦镇", 112_000, 14186005, "town"),
        )
    ]
    + [
        _row(
            "普陀区", code, name, value, osm, kind, rounding_increment=1000,
            published_name=published,
            crosswalk_note=note,
        )
        for code, name, published, value, osm, kind, note in (
            ("310107005000", "曹杨新村街道", "曹杨新村街道", 22_000, 14187873, "street", "exact official-name match"),
            ("310107014000", "长风新村街道", "长风新村街道", 90_000, 14187872, "street", "exact official-name match"),
            ("310107015000", "长寿路街道", "长寿路街道", 96_000, 14187871, "street", "exact official-name match"),
            ("310107016000", "甘泉路街道", "甘泉路街道", 21_000, 14187870, "street", "exact official-name match"),
            ("310107017000", "石泉路街道", "石泉路街道", 20_000, 14187869, "street", "exact official-name match"),
            ("310107020000", "宜川路街道", "宜川路街道", 17_000, 14187868, "street", "exact official-name match"),
            ("310107021000", "真如镇街道", "真如镇", 26_000, 14187866, "street", "explicit bulletin-label crosswalk: 真如镇 -> official 2023 真如镇街道"),
            ("310107022000", "万里街道", "万里街道", 43_000, 14187867, "street", "exact official-name match"),
            ("310107102000", "长征镇", "长征镇", 112_000, 14187865, "town", "exact official-name match"),
            ("310107103000", "桃浦镇", "桃浦镇", 65_000, 14187864, "town", "exact official-name match"),
        )
    ]
    + [
        _row(
            "虹口区", code, name, value, osm, "street",
            published_name=published, crosswalk_note=note,
        )
        for code, name, published, value, osm, note in (
            ("310109009000", "欧阳路街道", "欧阳路街道", 21_300, 13465959, "exact official-name match"),
            ("310109010000", "曲阳路街道", "曲阳路街道", 46_159, 13466001, "exact official-name match"),
            ("310109011000", "广中路街道", "广中路街道", 33_773, 13466055, "exact official-name match"),
            ("310109014000", "嘉兴路街道", "嘉兴路街道", 40_429, 13462879, "exact official-name match"),
            ("310109016000", "凉城新村街道", "凉城新材街道", 23_538, 13466134, "explicit bulletin typo crosswalk: 凉城新材街道 -> official 2023 凉城新村街道"),
            ("310109017000", "四川北路街道", "四川北路街道", 51_996, 13462869, "exact official-name match"),
            ("310109018000", "北外滩街道", "北外滩街道", 133_468, 13462842, "exact official-name match"),
            ("310109019000", "江湾镇街道", "江湾镇街道", 29_170, 13466137, "exact official-name match"),
        )
    ]
    + [
        _row("杨浦区", code, name, value, osm, "street")
        for code, name, value, osm in (
            ("310110001000", "定海路街道", 30_849, 13466400),
            ("310110006000", "平凉路街道", 49_638, 13464332),
            ("310110008000", "江浦路街道", 44_382, 13464392),
            ("310110009000", "四平路街道", 45_502, 13466002),
            ("310110012000", "控江路街道", 15_491, 13466004),
            ("310110013000", "长白新村街道", 11_271, 13466407),
            ("310110015000", "延吉新村街道", 13_326, 13466383),
            ("310110016000", "殷行街道", 16_658, 13466582),
            ("310110018000", "大桥街道", 72_321, 13466384),
            ("310110019000", "五角场街道", 105_944, 13466003),
            ("310110020000", "新江湾城街道", 55_638, 13466494),
            ("310110021000", "长海路街道", 40_003, 13466408),
        )
    ]
    + [
        _row("浦东新区", code, name, value, osm, kind, rounding_increment=1000, subtotal_group=subtotal)
        for code, name, value, osm, kind, subtotal in (
            ("310115004000", "潍坊新村街道", 154_000, 12867311, "street", "Pudong streets"),
            ("310115005000", "陆家嘴街道", 201_000, 12867312, "street", "Pudong streets"),
            ("310115007000", "周家渡街道", 25_000, 14178772, "street", "Pudong streets"),
            ("310115008000", "塘桥街道", 55_000, 12867313, "street", "Pudong streets"),
            ("310115009000", "上钢新村街道", 26_000, 14178805, "street", "Pudong streets"),
            ("310115010000", "南码头路街道", 42_000, 14178760, "street", "Pudong streets"),
            ("310115011000", "沪东新村街道", 14_000, 14178858, "street", "Pudong streets"),
            ("310115012000", "金杨新村街道", 24_000, 14178830, "street", "Pudong streets"),
            ("310115013000", "洋泾街道", 52_000, 5325929, "street", "Pudong streets"),
            ("310115014000", "浦兴路街道", 17_000, 14178857, "street", "Pudong streets"),
            ("310115015000", "东明路街道", 6_000, 14178911, "street", "Pudong streets"),
            ("310115016000", "花木街道", 82_000, 12867438, "street", "Pudong streets"),
            ("310115103000", "川沙新镇", 89_000, 14179063, "town", "Pudong towns"),
            ("310115104000", "高桥镇", 38_000, 14179071, "town", "Pudong towns"),
            ("310115105000", "北蔡镇", 60_000, 14179101, "town", "Pudong towns"),
            ("310115110000", "合庆镇", 38_000, 14179128, "town", "Pudong towns"),
            ("310115114000", "唐镇", 43_000, 14179148, "town", "Pudong towns"),
            ("310115117000", "曹路镇", 44_000, 14179174, "town", "Pudong towns"),
            ("310115120000", "金桥镇", 20_000, 14179186, "town", "Pudong towns"),
            ("310115121000", "高行镇", 35_000, 14179185, "town", "Pudong towns"),
            ("310115123000", "高东镇", 28_000, 14179184, "town", "Pudong towns"),
            ("310115125000", "张江镇", 21_000, 14179188, "town", "Pudong towns"),
            ("310115130000", "三林镇", 96_000, 14179226, "town", "Pudong towns"),
            ("310115131000", "惠南镇", 68_000, 14179286, "town", "Pudong towns"),
            ("310115132000", "周浦镇", 48_000, 14179320, "town", "Pudong towns"),
            ("310115133000", "新场镇", 26_000, 14179332, "town", "Pudong towns"),
            ("310115134000", "大团镇", 10_000, 14179370, "town", "Pudong towns"),
            ("310115136000", "康桥镇", 57_000, 14179369, "town", "Pudong towns"),
            ("310115137000", "航头镇", 39_000, 14179368, "town", "Pudong towns"),
            ("310115139000", "祝桥镇", 82_000, 14179522, "town", "Pudong towns"),
            ("310115140000", "泥城镇", 38_000, 14180408, "town", "Pudong towns"),
            ("310115141000", "宣桥镇", 36_000, 14180407, "town", "Pudong towns"),
            ("310115142000", "书院镇", 14_000, 14180406, "town", "Pudong towns"),
            ("310115143000", "万祥镇", 17_000, 14180410, "town", "Pudong towns"),
            ("310115144000", "老港镇", 14_000, 14180412, "town", "Pudong towns"),
            ("310115145000", "南汇新城镇", 138_000, 14180411, "town", "Pudong towns"),
        )
    ]
    + [
        _row(
            "浦东新区", code, name, value, None, "functional_zone",
            rounding_increment=1000, subtotal_group="Pudong functional zones",
            crosswalk_note="exact 2020/2023 statistical code and census-row name; accounting support is not an official 2023 polygon",
        )
        for code, name, value in (
            ("310115501000", "中国（上海）自由贸易试验区（保税片区）", 149_000),
            ("310115502000", "金桥经济技术开发区", 203_000),
            ("310115503000", "张江高科技园区", 469_000),
        )
    ]
)

# Pudong's 12 displayed street rows sum to 69.8 万 while the published street
# subtotal is 69.5 万. Each row was rounded to 0.1 万. The unique least-squares
# reconciliation under the row intervals subtracts 250 people from every street;
# it preserves every displayed value after rounding and hits the subtotal exactly.
CONTROLS = tuple(
    {
        **control,
        "employment_reconciled": (
            control["employment_nominal"] - 250
            if control["subtotal_group"] == "Pudong streets"
            else control["employment_nominal"]
        ),
        "reconciliation_note": (
            "Pudong street subtotal: least-squares adjustment -250 from each of 12 rounded rows"
            if control["subtotal_group"] == "Pudong streets"
            else "nominal midpoint retained"
        ),
    }
    for control in CONTROLS
)

RESIDUALS: tuple[dict[str, Any], ...] = (
    {
        "district": "黄浦区", "residual_id": "310101-finance-residual",
        "residual_class": "finance_regulator_return", "employment_nominal": 74_334,
        "rounding_lower": 74_334, "rounding_upper": 74_334,
        "reason": "geographic table excludes enterprise legal units returned by financial regulators",
        "central_rule": "finance/business POI and non-residential-building surface; normalized within district",
        "central_is_spatially_allocated": True,
    },
    {
        "district": "徐汇区", "residual_id": "310104-construction-finance-residual",
        "residual_class": "construction_plus_finance_unsplit", "employment_nominal": 73_346,
        "rounding_lower": 72_696, "rounding_upper": 73_996,
        "reason": "street/town rows exclude construction and finance; exact split unavailable",
        "central_rule": "unresolved: no defensible split between sectors",
        "central_is_spatially_allocated": False,
    },
    {
        "district": "长宁区", "residual_id": "310105-finance-residual",
        "residual_class": "directly_managed_finance", "employment_nominal": 5_174,
        "rounding_lower": 5_174, "rounding_upper": 5_174,
        "reason": "geographic table excludes directly managed financial units",
        "central_rule": "finance/business POI and non-residential-building surface; normalized within district",
        "central_is_spatially_allocated": True,
    },
    {
        "district": "静安区", "residual_id": "310106-finance-residual",
        "residual_class": "finance", "employment_nominal": 56_987,
        "rounding_lower": 49_987, "rounding_upper": 63_987,
        "reason": "geographic rows exclude finance",
        "central_rule": "finance/business POI and non-residential-building surface; normalized within district",
        "central_is_spatially_allocated": True,
    },
    {
        "district": "普陀区", "residual_id": "310107-finance-residual",
        "residual_class": "finance", "employment_nominal": 12_969,
        "rounding_lower": 7_969, "rounding_upper": 17_969,
        "reason": "geographic rows exclude finance",
        "central_rule": "finance/business POI and non-residential-building surface; normalized within district",
        "central_is_spatially_allocated": True,
    },
    {
        "district": "虹口区", "residual_id": "310109-special-channel-residual",
        "residual_class": "unsubdivided_special_channel", "employment_nominal": 29_556,
        "rounding_lower": 29_556, "rounding_upper": 29_556,
        "reason": "some workers not subdivided; construction processing location qualified but not split",
        "central_rule": "unresolved: no published sector split or establishment weights",
        "central_is_spatially_allocated": False,
    },
    {
        "district": "杨浦区", "residual_id": "310110-finance-construction-residual",
        "residual_class": "finance_plus_national_channel_construction", "employment_nominal": 9_539,
        "rounding_lower": 9_539, "rounding_upper": 9_539,
        "reason": "geographic rows exclude finance and national-channel construction; exact split unavailable",
        "central_rule": "unresolved: no defensible sector split",
        "central_is_spatially_allocated": False,
    },
    {
        "district": "浦东新区", "residual_id": "310115-unsubdivided-residual",
        "residual_class": "unsubdivided_special_channel", "employment_nominal": 264_157,
        "rounding_lower": 262_657, "rounding_upper": 265_657,
        "reason": "district total exceeds the three published geographic-category subtotals",
        "central_rule": "unresolved: no sector/entity evidence supports a location",
        "central_is_spatially_allocated": False,
    },
)


XUHUI_INDIVIDUAL_BUSINESS_EMPLOYMENT: tuple[tuple[str, int], ...] = (
    ("Manufacturing", 129),
    ("Construction", 32),
    ("Wholesale and retail", 8_477),
    ("Transport, storage and post", 134),
    ("Accommodation and catering", 5_253),
    ("Real estate", 173),
    ("Leasing and business services", 148),
    ("Resident services, repair and other services", 2_623),
    ("Education", 14),
    ("Culture, sports and entertainment", 115),
)
