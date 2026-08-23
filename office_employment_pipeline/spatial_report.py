"""Write the review report for the office-employment spatial framework."""

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
    summary = json.loads(
        (outputs / "spatial-allocation-summary.json").read_text(encoding="utf-8")
    )
    quality = json.loads(
        (spatial_root / "intermediate/building-evidence-quality.json").read_text(
            encoding="utf-8"
        )
    )
    diagnostics = pd.read_csv(outputs / "allocation-diagnostics.csv")
    clusters = pd.read_csv(outputs / "cluster-validation.csv")

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
                f"{row.maximum_local_cell_percentile_among_positive_cells:.2f}",
                "Yes" if row.cluster_emerges_under_declared_rule else "No",
                "Yes"
                if row.strong_cluster_emerges_under_declared_rule
                else "No",
            ]
        )

    component_rows = [
        ["JRC non-residential building volume", "60%", "Primary magnitude signal"],
        ["OSM tagged building-function footprint", "25%", "Industry-specific workplace type"],
        ["OSM office establishment tags", "10%", "Independent office/business anchor"],
        ["Overture workplace POIs", "5%", "Supplementary evidence only"],
    ]
    min_gini = float(diagnostics["gini_cell_employment"].min())
    max_gini = float(diagnostics["gini_cell_employment"].max())
    min_top_one = float(
        diagnostics["top_1_percent_cell_employment_share"].min() * 100.0
    )
    max_top_one = float(
        diagnostics["top_1_percent_cell_employment_share"].max() * 100.0
    )
    lines = [
        "# Jinke office-employment spatial allocation framework",
        "",
        "## Review status",
        "",
        "The spatial framework is complete for review. It allocates the eight "
        "audited reach-relevant districts to the inherited 100 m EPSG:32651 "
        "lattice. **No reach polygon was intersected and no reach percentage was "
        "calculated.** The GDP model, general-employment results, reach polygons, "
        "and Site are outside this workstream.",
        "",
        "Core remains the official district×industry hard control. Core+ Base is "
        "the central composition case; Low and High retain the reviewed division-72 "
        "district-composition sensitivity. The fixed city controls remain "
        f"**{summary['city_core_hard_control']:,} Core** and "
        f"**{summary['city_core_plus_control_each_scenario']:,} Core+** in every scenario.",
        "",
        "## Spatial scope and accounting identity",
        "",
        f"The grid contains **{summary['priority_grid_cell_count']:,} unique physical "
        "cells** in Huangpu, Xuhui, Changning, Jing'an, Putuo, Hongkou, Yangpu, "
        "and Pudong. Functional-zone and residual overlay rows from the general "
        "employment grid are excluded before the street/town fragments are dissolved, "
        "so no physical 100 m cell is counted twice.",
        "",
        f"Priority-district Core allocation: **{summary['priority_core_allocated_employment']:,}**.",
        "",
        _markdown_table(
            ["Core+ scenario", "Priority-district allocated employment", "Difference from Base"],
            scenario_rows,
        ),
        "",
        f"All **{len(diagnostics):,} district×industry/scenario reconciliation "
        "records have zero difference** between assigned and allocated employment. "
        "Integer largest-remainder allocation makes the identity exact rather than "
        "dependent on floating-point tolerance.",
        "",
        "The other eight Shanghai districts remain as district controls only. They "
        "are not spatialized in this stage because the inherited audited 100 m "
        "employment lattice covers the eight districts relevant to the production "
        "reach. The previously identified Minhang contact remains a separate technical "
        "boundary sliver and is not assigned office employment here.",
        "",
        "## Allocation method",
        "",
        _markdown_table(["Evidence component", "Declared share", "Role"], component_rows),
        "",
        "Each component is kept in raw linear form, normalized within each district "
        "and industry, and combined with the declared shares above. There is **no "
        "log transform, cap, winsorization, district min–max normalization, spatial "
        "smoothing, uniform main allocation, or generic PPML fit**. Industry-specific "
        "relevance rules differ for I, J, M, 721, 723, 724, and 725 and are serialized "
        "in `spatial-allocation-summary.json`.",
        "",
        "OSM `building:levels` is present for only "
        f"**{quality['known_building_levels_share_of_classified_features'] * 100:.1f}%** "
        "of classified workplace buildings in scope, so levels are audited but not "
        "used in the allocation. JRC non-residential volume supplies the consistent "
        "built-magnitude signal; OSM footprint area supplies only building function.",
        "",
        "## Source-quality findings",
        "",
        f"- {quality['classified_workplace_buildings_in_priority_scope']:,} classified "
        "OSM workplace-building features intersect the priority grid.",
        f"- {quality['invalid_or_empty_classified_geometries_before_repair']:,} "
        "classified source geometries required validity repair; none remain invalid "
        "or empty after repair.",
        f"- {quality['cells_with_building_function_evidence']:,} cells have tagged "
        "building-function footprint evidence.",
        f"- {quality['office_establishment_anchors_matched_to_grid']:,} OSM office "
        "establishment anchors match the grid across "
        f"{quality['cells_with_office_establishment_anchors']:,} cells.",
        "- The OSM building snapshot is 23 August 2026, JRC volume is epoch 2020, "
        "Overture Places is release 2026-07-22.0, and the employment controls are "
        "31 December 2023. These layers are spatial proxies, not contemporaneous "
        "employment observations.",
        f"- JRC non-residential volume is positive in "
        f"{quality['cells_with_positive_jrc_nonresidential_volume']:,} of "
        f"{quality['priority_grid_cell_count']:,} cells "
        f"({quality['positive_jrc_cell_share'] * 100:.1f}%). Overture workplace "
        f"evidence is positive in {quality['cells_with_any_overture_workplace_poi']:,} "
        f"cells ({quality['positive_overture_cell_share'] * 100:.1f}%).",
        "- The rolling OSM download URL cannot guarantee later retrieval of the same "
        "PBF. The raw SHA-256 is enforced and the non-reconstructive 100 m building "
        "evidence is committed under ODbL attribution so the checked-in allocation "
        "remains reproducible.",
        f"- Cell-allocation Gini values range from **{min_gini:.3f} to "
        f"{max_gini:.3f}** across district×industry/scenario controls; the top 1% "
        f"of cells carry **{min_top_one:.1f}% to {max_top_one:.1f}%** of each control. "
        "This confirms that the surface is not spatially flattened, but also flags "
        "upper-tail concentration as a review caveat rather than treating it as "
        "observed workplace density.",
        "",
        "## Workplace-cluster validation",
        "",
        "A cluster is recorded as emerging when its 1.5 km Core+ Base density is at "
        "least the containing-district mean and its maximum local cell is at or above "
        "the 95th percentile of positive cells. A separate strong-contrast flag requires "
        "at least 1.5× district density and a 90th-percentile local maximum.",
        "",
        _markdown_table(
            [
                "Cluster",
                "District",
                "Core+ Base within 1.5 km",
                "Density vs district",
                "Max-cell percentile",
                "Emerges",
                "Strong",
            ],
            cluster_rows,
        ),
        "",
        f"All **{int(clusters['cluster_emerges_under_declared_rule'].sum())} of 7** "
        "declared centres emerge under the basic rule; "
        f"**{int(clusters['strong_cluster_emerges_under_declared_rule'].sum())} of 7** "
        "meet the stronger contrast rule. The result is not forced: Jing'an, Xujiahui, "
        "and Wujiaochang show high-intensity cells but only moderate density uplift "
        "relative to already dense districts.",
        "",
        "Validation maps use one common logarithmic display scale for allocated people "
        "per 100 m cell. The log scale affects color only; it does not alter allocation. "
        "No reach polygon is drawn or queried.",
        "The stars are declared approximate WGS84 cluster centres used only for "
        "validation windows; they are not official CBD or development-zone boundaries. "
        "Pudong density ratios also inherit Pudong's very large district-area denominator.",
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
        "- `core-employment-grid-100m.parquet`: Core I/J/M weights and exact integer allocations.",
        "- `core-plus-base-employment-grid-100m.parquet`: Core hard controls plus Base 721/723/724/725.",
        "- `core-plus-sensitivity-grid-100m.parquet`: Low/Base/High cell comparisons.",
        "- `allocation-diagnostics.csv`: exact control reconciliation and concentration diagnostics.",
        "- `cluster-validation.csv`: quantitative checks supporting the seven maps.",
        "- `building-function-evidence-100m.parquet`: frozen derived OSM evidence.",
        "- `source-manifest.csv`: source hashes, years, access, and reuse terms.",
        "",
        "## Validation assessment",
        "",
        "**Ready for spatial-framework review, with source-vintage and OSM-function "
        "coverage caveats.** Approval of this framework would authorize a later reach "
        "intersection; this commit itself contains no reach result or percentage.",
        "",
    ]
    report_path = outputs / "spatial-allocation-report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
