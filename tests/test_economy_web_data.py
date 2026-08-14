import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "web" / "public" / "data"
REACH_ECONOMY = DATA_DIR / "reach-economy.json"
METHODOLOGY = DATA_DIR / "gdp-methodology.json"
LIMITS = [10, 20, 30, 40, 50]


def load_payloads():
    return (
        json.loads(REACH_ECONOMY.read_text(encoding="utf-8")),
        json.loads(METHODOLOGY.read_text(encoding="utf-8")),
    )


def test_reach_economy_has_all_limits_and_reconciled_calculations():
    records, methodology = load_payloads()
    assert [record["limit_minutes"] for record in records] == LIMITS
    assert len({record["limit_minutes"] for record in records}) == len(LIMITS)

    official_city_gdp = methodology["official_gdp"][
        "official_city_gdp_100m_cny"
    ]
    assert official_city_gdp == 56708.71
    assert methodology["official_gdp"]["unit"] == (
        "100 million current CNY (亿元)"
    )

    previous = 0.0
    for record in records:
        central = record["estimated_gdp_100m_cny"]
        assert central >= previous >= 0
        assert math.isclose(
            record["percentage_of_shanghai_gdp"],
            central / official_city_gdp * 100,
            rel_tol=0,
            abs_tol=1e-10,
        )
        assert math.isclose(
            record["incremental_gdp_100m_cny"],
            central - previous,
            rel_tol=0,
            abs_tol=1e-10,
        )
        previous = central


def test_central_and_sensitivity_estimates_are_nonnegative_and_monotonic():
    records, _ = load_payloads()
    for field in (
        "estimated_gdp_100m_cny",
        "building_heavy_gdp_100m_cny",
        "activity_heavy_gdp_100m_cny",
    ):
        values = [record[field] for record in records]
        assert all(math.isfinite(value) and value >= 0 for value in values)
        assert values == sorted(values)


def test_methodology_versions_and_production_reach_hash_are_pinned():
    _, methodology = load_payloads()
    assert methodology["official_gdp"]["year"] == 2025
    assert methodology["sources"]["jrc"]["dataset"] == (
        "GHS-BUILT-V_NRES_GLOBE_R2023A"
    )
    assert methodology["sources"]["jrc"]["epoch"] == 2020
    assert methodology["sources"]["viirs"]["dataset"] == "VNP46A4"
    assert methodology["sources"]["viirs"]["year"] == 2025
    assert methodology["sources"]["viirs"]["version"] == "2"
    assert methodology["sources"]["overture"]["release"] == "2026-07-22.0"
    assert "not confidence intervals" in methodology["sensitivity_disclosure"]

    reach_path = DATA_DIR / "reach-areas.geojson"
    actual_hash = hashlib.sha256(reach_path.read_bytes()).hexdigest()
    assert actual_hash == methodology["reach_polygons"]["sha256"]


def test_economic_frontend_payload_is_lightweight_and_excludes_grid():
    assert REACH_ECONOMY.stat().st_size + METHODOLOGY.stat().st_size < 50_000
    assert not list(DATA_DIR.glob("*.parquet"))
    assert not list(DATA_DIR.glob("*gdp-grid*"))
