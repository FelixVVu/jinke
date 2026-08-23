"""Static validation maps and cluster diagnostics for office allocation."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, LogNorm
from matplotlib.patches import Circle
from pyproj import Transformer


CLUSTERS = (
    {
        "cluster_id": "lujiazui",
        "cluster_name": "Lujiazui",
        "longitude": 121.5025,
        "latitude": 31.2397,
        "expected_district": "浦东新区",
    },
    {
        "cluster_id": "peoples-square-nanjing-road",
        "cluster_name": "People's Square / Nanjing Road",
        "longitude": 121.4737,
        "latitude": 31.2335,
        "expected_district": "黄浦区",
    },
    {
        "cluster_id": "jingan",
        "cluster_name": "Jing'an",
        "longitude": 121.4450,
        "latitude": 31.2290,
        "expected_district": "静安区",
    },
    {
        "cluster_id": "xujiahui",
        "cluster_name": "Xujiahui",
        "longitude": 121.4375,
        "latitude": 31.1954,
        "expected_district": "徐汇区",
    },
    {
        "cluster_id": "zhangjiang",
        "cluster_name": "Zhangjiang",
        "longitude": 121.5930,
        "latitude": 31.2050,
        "expected_district": "浦东新区",
    },
    {
        "cluster_id": "wujiaochang",
        "cluster_name": "Wujiaochang",
        "longitude": 121.5140,
        "latitude": 31.3020,
        "expected_district": "杨浦区",
    },
    {
        "cluster_id": "hongqiao",
        "cluster_name": "Hongqiao development area",
        "longitude": 121.4050,
        "latitude": 31.2050,
        "expected_district": "长宁区",
    },
)
RADIUS_METRES = 1_500.0
MAP_HALF_WIDTH_METRES = 3_500.0
EMERGENCE_DENSITY_RATIO = 1.0
EMERGENCE_MAX_CELL_PERCENTILE = 95.0
STRONG_DENSITY_RATIO = 1.5
STRONG_MAX_CELL_PERCENTILE = 90.0


def evaluate_clusters(grid: gpd.GeoDataFrame) -> pd.DataFrame:
    """Evaluate declared centres without using any reach polygon."""

    if grid.crs is None or grid.crs.to_epsg() != 32651:
        raise ValueError("Cluster validation grid must use EPSG:32651.")
    value_column = "cell_employment_core_plus_base"
    if value_column not in grid.columns:
        raise ValueError(f"Missing {value_column}.")
    transformer = Transformer.from_crs("EPSG:4326", grid.crs, always_xy=True)
    district_area = grid.groupby("district")["cell_area_m2"].sum() / 1_000_000.0
    district_jobs = grid.groupby("district")[value_column].sum()
    district_density = district_jobs / district_area
    positive = grid.loc[grid[value_column] > 0, value_column]
    records: list[dict[str, Any]] = []
    for cluster in CLUSTERS:
        x, y = transformer.transform(cluster["longitude"], cluster["latitude"])
        distance = np.hypot(
            grid["center_x"].to_numpy(dtype=float) - x,
            grid["center_y"].to_numpy(dtype=float) - y,
        )
        local = grid.loc[distance <= RADIUS_METRES]
        local_area_km2 = float(local["cell_area_m2"].sum() / 1_000_000.0)
        local_jobs = int(local[value_column].sum())
        local_density = local_jobs / local_area_km2 if local_area_km2 else 0.0
        max_cell = int(local[value_column].max()) if len(local) else 0
        max_percentile = (
            float((positive <= max_cell).mean() * 100.0) if len(positive) else 0.0
        )
        expected_district = cluster["expected_district"]
        density_ratio = local_density / float(district_density.loc[expected_district])
        emerges = (
            density_ratio >= EMERGENCE_DENSITY_RATIO
            and max_percentile >= EMERGENCE_MAX_CELL_PERCENTILE
        )
        strong_emergence = (
            density_ratio >= STRONG_DENSITY_RATIO
            and max_percentile >= STRONG_MAX_CELL_PERCENTILE
        )
        records.append(
            {
                **cluster,
                "analysis_x": float(x),
                "analysis_y": float(y),
                "validation_radius_m": RADIUS_METRES,
                "local_cell_count": int(len(local)),
                "local_area_km2": local_area_km2,
                "core_plus_base_employment_in_radius": local_jobs,
                "local_employment_density_per_km2": local_density,
                "expected_district_employment_density_per_km2": float(
                    district_density.loc[expected_district]
                ),
                "local_to_district_density_ratio": density_ratio,
                "maximum_local_cell_employment": max_cell,
                "maximum_local_cell_percentile_among_positive_cells": max_percentile,
                "emergence_density_ratio_threshold": EMERGENCE_DENSITY_RATIO,
                "emergence_max_cell_percentile_threshold": EMERGENCE_MAX_CELL_PERCENTILE,
                "cluster_emerges_under_declared_rule": bool(emerges),
                "strong_density_ratio_threshold": STRONG_DENSITY_RATIO,
                "strong_max_cell_percentile_threshold": STRONG_MAX_CELL_PERCENTILE,
                "strong_cluster_emerges_under_declared_rule": bool(
                    strong_emergence
                ),
                "reach_polygon_used": False,
            }
        )
    return pd.DataFrame(records)


def _map_one_cluster(
    grid: gpd.GeoDataFrame,
    row: pd.Series,
    output_path: Path,
    norm: LogNorm,
    cmap: LinearSegmentedColormap,
) -> None:
    x = float(row["analysis_x"])
    y = float(row["analysis_y"])
    mask = (
        grid["center_x"].between(x - MAP_HALF_WIDTH_METRES, x + MAP_HALF_WIDTH_METRES)
        & grid["center_y"].between(y - MAP_HALF_WIDTH_METRES, y + MAP_HALF_WIDTH_METRES)
    )
    local = grid.loc[mask].copy()
    district_outline = local[["district", "geometry"]].dissolve(by="district")
    values = local["cell_employment_core_plus_base"].to_numpy(dtype=float)
    plot_values = np.where(values > 0, values, np.nan)

    fig, ax = plt.subplots(figsize=(8.4, 7.2), dpi=180)
    ax.set_facecolor("#F5F7FA")
    scatter = ax.scatter(
        local["center_x"],
        local["center_y"],
        c=plot_values,
        cmap=cmap,
        norm=norm,
        marker="s",
        s=8,
        linewidths=0,
        rasterized=True,
    )
    district_outline.boundary.plot(ax=ax, color="#344054", linewidth=0.9)
    ax.add_patch(
        Circle(
            (x, y),
            RADIUS_METRES,
            fill=False,
            edgecolor="#B7791F",
            linewidth=1.4,
            linestyle="--",
        )
    )
    ax.scatter(
        [x],
        [y],
        marker="*",
        s=180,
        c="#D69E2E",
        edgecolors="#1F2937",
        linewidths=0.8,
        zorder=5,
    )
    ax.set_xlim(x - MAP_HALF_WIDTH_METRES, x + MAP_HALF_WIDTH_METRES)
    ax.set_ylim(y - MAP_HALF_WIDTH_METRES, y + MAP_HALF_WIDTH_METRES)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color("#D0D5DD")
    status = "emerges" if row["cluster_emerges_under_declared_rule"] else "does not emerge"
    strong_status = (
        "strong contrast"
        if row["strong_cluster_emerges_under_declared_rule"]
        else "moderate contrast"
    )
    ax.set_title(
        f"Core+ Base 100 m allocation — {row['cluster_name']}",
        loc="left",
        fontsize=13,
        fontweight="bold",
        color="#101828",
        pad=16,
    )
    ax.text(
        0,
        1.015,
        (
            f"1.5 km density is {row['local_to_district_density_ratio']:.2f}× the "
            f"district mean; cluster {status} with {strong_status}."
        ),
        transform=ax.transAxes,
        fontsize=9,
        color="#475467",
        va="bottom",
    )
    colorbar = fig.colorbar(scatter, ax=ax, fraction=0.040, pad=0.02)
    colorbar.set_label("Allocated people per 100 m cell (log scale)", fontsize=8)
    colorbar.ax.tick_params(labelsize=8)
    ax.text(
        0,
        -0.035,
        "Gold star: declared centre · dashed ring: 1.5 km · no reach polygon shown",
        transform=ax.transAxes,
        fontsize=8,
        color="#667085",
        va="top",
    )
    fig.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def render_cluster_validation_maps(
    core_plus_grid_path: Path,
    maps_directory: Path,
    diagnostics_path: Path,
) -> pd.DataFrame:
    grid = gpd.read_parquet(core_plus_grid_path)
    diagnostics = evaluate_clusters(grid)
    maps_directory.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(diagnostics_path, index=False)
    positive = grid.loc[
        grid["cell_employment_core_plus_base"] > 0,
        "cell_employment_core_plus_base",
    ]
    if positive.empty:
        raise RuntimeError("Core+ Base grid has no positive cells.")
    norm = LogNorm(vmin=1.0, vmax=max(float(positive.max()), 1.0))
    cmap = LinearSegmentedColormap.from_list(
        "jinke_office_blue", ["#EAF2FB", "#7FB3E1", "#1E5AA8", "#12355B"]
    )
    for _, row in diagnostics.iterrows():
        _map_one_cluster(
            grid,
            row,
            maps_directory / f"cluster-{row['cluster_id']}.png",
            norm,
            cmap,
        )
    return diagnostics


def update_summary_with_clusters(summary_path: Path, clusters: pd.DataFrame) -> None:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["cluster_validation"] = {
        "cluster_count": int(len(clusters)),
        "clusters_passing_declared_rule": int(
            clusters["cluster_emerges_under_declared_rule"].sum()
        ),
        "clusters_passing_strong_rule": int(
            clusters["strong_cluster_emerges_under_declared_rule"].sum()
        ),
        "all_declared_clusters_pass": bool(
            clusters["cluster_emerges_under_declared_rule"].all()
        ),
        "validation_radius_m": RADIUS_METRES,
        "reach_polygon_used": False,
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
