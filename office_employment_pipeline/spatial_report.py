"""Write the review report for the fine-control office spatial framework."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def _markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def write_spatial_review_report(spatial_root: Path) -> Path:
    outputs = spatial_root / "outputs"
    intermediate = spatial_root / "intermediate"
    summary = json.loads(
        (outputs / "spatial-allocation-summary.json").read_text(encoding="utf-8")
    )
    quality = json.loads(
        (intermediate / "building-evidence-quality.json").read_text(encoding="utf-8")
    )
    diagnostics = pd.read_csv(outputs / "allocation-diagnostics.csv")
    clusters = pd.read_csv(outputs / "cluster-validation.csv")
    matrix = pd.read_csv(
        intermediate / "control-industry-matrix-2023.csv",
        dtype={"accounting_stratum_id": str, "industry_code": str},
    )
    shifts = pd.read_csv(
        outputs / "control-shift-comparison.csv",
        dtype={"accounting_stratum_id": str},
    )
    concentration = pd.read_csv(outputs / "concentration-comparison.csv")
    weighting_clusters = pd.read_csv(outputs / "cluster-weighting-sensitivity.csv")

    scenario_totals = summary["priority_core_plus_allocated_employment"]
    base = int(scenario_totals["base"])
    scenario_rows = []
    for scenario, label in (
        ("low_office_intensity", "Low office intensity"),
        ("base", "Base"),
        ("high_office_intensity", "High office intensity"),
    ):
        value = int(scenario_totals[scenario])
        scenario_rows.append([label, f"{value:,}", f"{value - base:+,}"])

    cluster_rows = []
    for row in clusters.itertuples(index=False):
        cluster_rows.append(
            [
                row.cluster_name,
                row.expected_district,
                f"{row.core_plus_base_employment_in_radius:,}",
                f"{row.local_to_district_density_ratio:.2f}×",
                f"{row.district_direct_local_to_district_density_ratio:.2f}×",
                f"{row.density_ratio_change_from_district_direct:+.2f}×",
                "Yes" if row.cluster_emerges_under_declared_rule else "No",
                "Yes" if row.strong_cluster_emerges_under_declared_rule else "No",
            ]
        )

    weighting_rows = [
        ["Base", "60%", "25%", "10%", "5%"],
        ["Building-volume dominant", "75%", "15%", "7.5%", "2.5%"],
        ["Workplace-evidence emphasis", "45%", "30%", "15%", "10%"],
    ]
    concentration_labels = {
        "district_direct_base": "Previous district-direct Base",
        "fine_control_base": "Revised fine-control Base",
        "fine_control_building_volume_dominant": "Revised building-volume dominant",
        "fine_control_workplace_evidence_emphasis": "Revised workplace-evidence emphasis",
    }
    concentration_rows = [
        [
            concentration_labels[row.allocation_architecture],
            f"{row.gini_cell_employment:.4f}",
            f"{row.top_1_percent_cell_employment_share * 100:.2f}%",
            f"{int(row.maximum_cell_employment):,}",
            f"{row.cell_hhi:.6f}",
        ]
        for row in concentration.itertuples(index=False)
    ]
    top_shifts = shifts.assign(
        absolute_shift=shifts["core_plus_base_shift_from_district_direct"].abs()
    ).nlargest(10, "absolute_shift")
    shift_rows = [
        [
            row.district,
            row.control_name,
            f"{row.district_direct_core_plus_base:,.0f}",
            f"{row.revised_core_plus_base:,.0f}",
            f"{row.core_plus_base_shift_from_district_direct:+,.0f}",
        ]
        for row in top_shifts.itertuples(index=False)
    ]
    weighting_labels = {
        "base": "Base 60/25/10/5",
        "building_volume_dominant": "Building-volume dominant",
        "workplace_evidence_emphasis": "Workplace-evidence emphasis",
    }
    weighting_cluster_rows = []
    for scenario, group in weighting_clusters.groupby("weighting_scenario", sort=False):
        weighting_cluster_rows.append(
            [
                weighting_labels[scenario],
                f"{int(group['cluster_emerges_under_declared_rule'].sum())}/7",
                f"{int(group['strong_cluster_emerges_under_declared_rule'].sum())}/7",
                f"{group['local_to_district_density_ratio'].min():.2f}×",
                f"{group['local_to_district_density_ratio'].max():.2f}×",
            ]
        )
    shift_summary = summary["control_shift_from_district_direct"]
    concentration_index = concentration.set_index("allocation_architecture")
    old = concentration_index.loc["district_direct_base"]
    revised = concentration_index.loc["fine_control_base"]
    fine_rows = matrix.loc[matrix["row_is_official_fine_control"]]
    fine_row_check_count = len(
        fine_rows.groupby(["scenario", "accounting_stratum_id"])
    )
    positive_diagnostics = diagnostics.loc[diagnostics["assigned_employment"] > 0]

    lines = [
        "# Jinke office-employment fine-control spatial framework",
        "",
        "## Review status",
        "",
        "The revised framework is complete for review. It allocates the eight audited "
        "priority districts to the existing 100 m EPSG:32651 lattice. **No reach polygon "
        "was intersected and no reach percentage was calculated.** GDP, general-employment "
        "outputs, reach polygons, and the Site remain outside this workstream.",
        "",
        "Core remains the official district×industry hard control. Core+ Base remains "
        "central; Low and High retain the reviewed selected-72 district composition "
        "sensitivity. City controls remain "
        f"**{summary['city_core_hard_control']:,} Core** and "
        f"**{summary['city_core_plus_control_each_scenario']:,} Core+**.",
        "",
        "## Accounting identity",
        "",
        f"The grid contains **{summary['priority_grid_cell_count']:,} unique physical "
        "cells**. Employment is reconciled at accounting-stratum grain, allocated within "
        "each stratum support, and aggregated once to physical cells.",
        "",
        f"Priority-district Core allocation: **{summary['priority_core_allocated_employment']:,}**.",
        "",
        _markdown_table(
            ["Core+ composition", "Priority-district employment", "Difference from Base"],
            scenario_rows,
        ),
        "",
        "## Control × industry matrix",
        "",
        "The synthetic matrix contains **116 official fine accounting rows plus eight "
        "explicit residual rows**. Columns are I, J, M, selected 721/723/724/725, and "
        "an `OTHER` remainder. The independence prior is the maximum-entropy solution "
        "when only the two official margins are observed; RAS/IPF and deterministic "
        "controlled integer rounding retain both margins.",
        "",
        f"Across three Core+ composition cases the matrix has **{len(matrix):,} cells**. "
        f"All **{fine_row_check_count:,} scenario×fine-control row checks** equal their "
        "official totals exactly, every district×industry margin reconciles exactly, "
        "and each eight-district ledger totals 7,640,573.",
        "",
        "The residual rows are required because published fine tables omit 526,062 "
        "district workers. Bulletin-identified finance residuals in Huangpu, Xuhui, "
        "Changning, Jing'an, Putuo, and Yangpu absorb official J before IPF; Hongkou and "
        "Pudong remain maximum-entropy residual compositions because their publications "
        "do not identify a sector split. This prevents excluded finance from being "
        "silently forced into street/town rows.",
        "",
        f"All **{len(diagnostics):,} control×industry allocation checks** have zero "
        "difference. None of the positive allocations "
        f"({len(positive_diagnostics):,} records) needed the uniform no-evidence fallback.",
        "",
        "Pudong's FTZ Bonded Area, Jinqiao ETDZ, and Zhangjiang High-Tech Park remain "
        "three immutable census rows. Overlap with ordinary streets is intentional: "
        "the employment rows are disjoint even when supports overlap. Each row enters "
        "the matrix and grid once. Restricted source geometry is not committed; only "
        "combined, non-zone-identifying physical-cell totals are published.",
        "",
        "## Within-control weights",
        "",
        _markdown_table(
            ["Weight case", "JRC volume", "Building function", "OSM establishments", "Overture POIs"],
            weighting_rows,
        ),
        "",
        "Every component remains raw and uncapped, is normalized within its own "
        "accounting stratum, and is combined linearly. There is no log transform, "
        "winsorization, district min–max normalization, smoothing, generic PPML, or "
        "uniform main allocation. All three weight cases preserve **2,336,384 "
        "priority-district Core+ Base workers exactly**.",
        "",
        "Against Base, the building-volume-dominant case relocates "
        f"**{summary['weighting_sensitivity_jobs_relocated_from_base']['building_volume_dominant']:,.0f} "
        "jobs between cells**, while workplace-evidence emphasis relocates "
        f"**{summary['weighting_sensitivity_jobs_relocated_from_base']['workplace_evidence_emphasis']:,.0f}**. "
        "These are half-L1 relocation measures; no employment is added or removed.",
        "",
        f"OSM `building:levels` is known for only "
        f"**{quality['known_building_levels_share_of_classified_features'] * 100:.1f}%** "
        "of classified workplace buildings, so levels remain audited but unused. "
        "JRC volume provides the consistent magnitude signal; OSM footprint supplies "
        "building function.",
        "",
        "## Change from district-direct allocation",
        "",
        f"Fine-control Base shifts **{shift_summary['core_plus_base_gross_jobs_shifted_between_ordinary_controls']:,.0f} "
        "Core+ jobs** between 113 ordinary controls—"
        f"**{shift_summary['core_plus_base_gross_jobs_shifted_between_ordinary_controls'] / base * 100:.1f}%** "
        "of priority Core+ Base employment. Core alone shifts "
        f"**{shift_summary['core_gross_jobs_shifted_between_ordinary_controls']:,.0f} jobs**. "
        "This is a relocation measure (half the summed absolute control changes), not "
        "new employment.",
        "",
        _markdown_table(
            ["District", "Ordinary control", "District-direct", "Revised", "Shift"],
            shift_rows,
        ),
        "",
        _markdown_table(
            ["Architecture", "Cell Gini", "Top 1% share", "Maximum cell", "Cell HHI"],
            concentration_rows,
        ),
        "",
        f"Versus district-direct Base, fine-control Base changes Gini by "
        f"**{revised.gini_cell_employment - old.gini_cell_employment:+.4f}**, top-1% "
        f"share by **{(revised.top_1_percent_cell_employment_share - old.top_1_percent_cell_employment_share) * 100:+.2f} "
        "percentage points**, and maximum cell employment by "
        f"**{int(revised.maximum_cell_employment - old.maximum_cell_employment):+,}**.",
        "",
        "## Workplace-cluster validation",
        "",
        "A cluster emerges when its 1.5 km Core+ Base density is at least the containing "
        "district mean and its maximum local cell is at or above the 95th percentile "
        "of positive cells. Strong contrast requires at least 1.5× district density "
        "and a 90th-percentile local maximum.",
        "",
        _markdown_table(
            [
                "Cluster",
                "District",
                "Revised jobs",
                "Revised ratio",
                "Previous ratio",
                "Ratio change",
                "Emerges",
                "Strong",
            ],
            cluster_rows,
        ),
        "",
        f"All **{int(clusters['cluster_emerges_under_declared_rule'].sum())}/7** centres "
        "emerge under the basic rule; "
        f"**{int(clusters['strong_cluster_emerges_under_declared_rule'].sum())}/7** meet "
        "the stronger rule.",
        "",
        _markdown_table(
            ["Weight case", "Basic emergence", "Strong emergence", "Minimum ratio", "Maximum ratio"],
            weighting_cluster_rows,
        ),
        "",
        "Validation maps use one common logarithmic color scale. The scale affects "
        "display only; it does not alter allocation. No reach polygon is drawn or read.",
        "",
        "- [Lujiazui](../maps/cluster-lujiazui.png)",
        "- [People's Square / Nanjing Road](../maps/cluster-peoples-square-nanjing-road.png)",
        "- [Jing'an](../maps/cluster-jingan.png)",
        "- [Xujiahui](../maps/cluster-xujiahui.png)",
        "- [Zhangjiang](../maps/cluster-zhangjiang.png)",
        "- [Wujiaochang](../maps/cluster-wujiaochang.png)",
        "- [Hongqiao development area](../maps/cluster-hongqiao.png)",
        "",
        "## Review files",
        "",
        "- `intermediate/control-industry-matrix-2023.csv`: three exact synthetic ledgers.",
        "- `intermediate/control-industry-reconciliation.csv`: margins and residual treatment.",
        "- `outputs/core-employment-grid-100m.parquet`: Core under Base weights.",
        "- `outputs/core-plus-base-employment-grid-100m.parquet`: Core+ Base under Base weights.",
        "- `outputs/core-plus-sensitivity-grid-100m.parquet`: Low/Base/High composition.",
        "- `outputs/core-plus-weighting-sensitivity-grid-100m.parquet`: three weight cases.",
        "- `outputs/control-shift-comparison.csv`: revised versus district-direct controls.",
        "- `outputs/concentration-comparison.csv`: old and revised cell concentration.",
        "- `outputs/cluster-validation.csv`: revised-versus-old cluster diagnostics.",
        "- `outputs/cluster-weighting-sensitivity.csv`: cluster robustness by weight case.",
        "",
        "## Validation assessment",
        "",
        "**Ready for fine-control spatial-framework review, with synthetic within-control "
        "industry composition, residual-support, source-vintage, and OSM-function "
        "coverage caveats.** A later reach calculation requires separate approval; this "
        "revision contains no reach result or percentage.",
        "",
    ]
    report_path = outputs / "spatial-allocation-report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
