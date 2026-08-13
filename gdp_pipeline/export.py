"""Write detailed Drive audit artifacts and the lightweight website ZIP."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def export_audit_outputs(
    *,
    audit_dir: Path,
    grid: gpd.GeoDataFrame,
    calibration: pd.DataFrame,
    reach: pd.DataFrame,
    methodology: dict[str, Any],
    validation_report: dict[str, Any],
) -> dict[str, Path]:
    audit_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "grid": audit_dir / "shanghai-gdp-grid.parquet",
        "calibration": audit_dir / "district-calibration.csv",
        "reach_analysis": audit_dir / "reach-gdp-analysis.csv",
        "methodology": audit_dir / "gdp-methodology.json",
        "validation": audit_dir / "validation-report.json",
        "reach_web": audit_dir / "reach-economy.json",
        "web_zip": audit_dir / "gdp-web-data.zip",
    }
    grid.to_parquet(paths["grid"], index=False)
    calibration.to_csv(paths["calibration"], index=False)
    reach.to_csv(paths["reach_analysis"], index=False)
    _write_json(paths["methodology"], methodology)
    _write_json(paths["validation"], validation_report)

    web_records = [
        {
            "limit_minutes": int(row.limit_minutes),
            "estimated_gdp_100m_cny": float(row.estimated_gdp_100m_cny),
            "percentage_of_shanghai_gdp": float(row.percentage_of_shanghai_gdp),
            "incremental_gdp_100m_cny": float(row.incremental_gdp_100m_cny),
            "building_heavy_gdp_100m_cny": float(row.building_heavy_gdp_100m_cny),
            "activity_heavy_gdp_100m_cny": float(row.activity_heavy_gdp_100m_cny),
        }
        for row in reach.itertuples(index=False)
    ]
    _write_json(paths["reach_web"], web_records)
    with zipfile.ZipFile(paths["web_zip"], "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(paths["reach_web"], arcname="reach-economy.json")
        archive.write(paths["methodology"], arcname="gdp-methodology.json")
    with zipfile.ZipFile(paths["web_zip"]) as archive:
        if sorted(archive.namelist()) != ["gdp-methodology.json", "reach-economy.json"]:
            raise RuntimeError("Website ZIP contains an unexpected file.")
    return paths
