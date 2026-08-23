# Jinke office-employment spatial allocation framework

## Review status

The spatial framework is complete for review. It allocates the eight audited reach-relevant districts to the inherited 100 m EPSG:32651 lattice. **No reach polygon was intersected and no reach percentage was calculated.** The GDP model, general-employment results, reach polygons, and Site are outside this workstream.

Core remains the official district×industry hard control. Core+ Base is the central composition case; Low and High retain the reviewed division-72 district-composition sensitivity. The fixed city controls remain **2,477,585 Core** and **3,220,710 Core+** in every scenario.

## Spatial scope and accounting identity

The grid contains **172,233 unique physical cells** in Huangpu, Xuhui, Changning, Jing'an, Putuo, Hongkou, Yangpu, and Pudong. Functional-zone and residual overlay rows from the general employment grid are excluded before the street/town fragments are dissolved, so no physical 100 m cell is counted twice.

Priority-district Core allocation: **1,852,975**.

| Core+ scenario | Priority-district allocated employment | Difference from Base |
|---|---|---|
| Low office intensity | 2,323,401 | -12,983 |
| Base | 2,336,384 | +0 |
| High office intensity | 2,349,367 | +12,983 |

All **120 district×industry/scenario reconciliation records have zero difference** between assigned and allocated employment. Integer largest-remainder allocation makes the identity exact rather than dependent on floating-point tolerance.

The other eight Shanghai districts remain as district controls only. They are not spatialized in this stage because the inherited audited 100 m employment lattice covers the eight districts relevant to the production reach. The previously identified Minhang contact remains a separate technical boundary sliver and is not assigned office employment here.

## Allocation method

| Evidence component | Declared share | Role |
|---|---|---|
| JRC non-residential building volume | 60% | Primary magnitude signal |
| OSM tagged building-function footprint | 25% | Industry-specific workplace type |
| OSM office establishment tags | 10% | Independent office/business anchor |
| Overture workplace POIs | 5% | Supplementary evidence only |

Each component is kept in raw linear form, normalized within each district and industry, and combined with the declared shares above. There is **no log transform, cap, winsorization, district min–max normalization, spatial smoothing, uniform main allocation, or generic PPML fit**. Industry-specific relevance rules differ for I, J, M, 721, 723, 724, and 725 and are serialized in `spatial-allocation-summary.json`.

OSM `building:levels` is present for only **7.3%** of classified workplace buildings in scope, so levels are audited but not used in the allocation. JRC non-residential volume supplies the consistent built-magnitude signal; OSM footprint area supplies only building function.

## Source-quality findings

- 9,730 classified OSM workplace-building features intersect the priority grid.
- 72 classified source geometries required validity repair; none remain invalid or empty after repair.
- 13,522 cells have tagged building-function footprint evidence.
- 397 OSM office establishment anchors match the grid across 344 cells.
- The OSM building snapshot is 23 August 2026, JRC volume is epoch 2020, Overture Places is release 2026-07-22.0, and the employment controls are 31 December 2023. These layers are spatial proxies, not contemporaneous employment observations.
- JRC non-residential volume is positive in 40,161 of 172,233 cells (23.3%). Overture workplace evidence is positive in 6,848 cells (4.0%).
- The rolling OSM download URL cannot guarantee later retrieval of the same PBF. The raw SHA-256 is enforced and the non-reconstructive 100 m building evidence is committed under ODbL attribution so the checked-in allocation remains reproducible.
- Cell-allocation Gini values range from **0.837 to 0.962** across district×industry/scenario controls; the top 1% of cells carry **15.9% to 41.4%** of each control. This confirms that the surface is not spatially flattened, but also flags upper-tail concentration as a review caveat rather than treating it as observed workplace density.

## Workplace-cluster validation

A cluster is recorded as emerging when its 1.5 km Core+ Base density is at least the containing-district mean and its maximum local cell is at or above the 95th percentile of positive cells. A separate strong-contrast flag requires at least 1.5× district density and a 90th-percentile local maximum.

| Cluster | District | Core+ Base within 1.5 km | Density vs district | Max-cell percentile | Emerges | Strong |
|---|---|---|---|---|---|---|
| Lujiazui | 浦东新区 | 52,103 | 10.78× | 99.84 | Yes | Yes |
| People's Square / Nanjing Road | 黄浦区 | 146,669 | 1.83× | 99.99 | Yes | Yes |
| Jing'an | 静安区 | 78,658 | 1.44× | 99.98 | Yes | No |
| Xujiahui | 徐汇区 | 48,466 | 1.19× | 99.78 | Yes | No |
| Zhangjiang | 浦东新区 | 55,187 | 11.43× | 99.91 | Yes | Yes |
| Wujiaochang | 杨浦区 | 24,846 | 1.26× | 99.57 | Yes | No |
| Hongqiao development area | 长宁区 | 46,280 | 1.71× | 99.71 | Yes | Yes |

All **7 of 7** declared centres emerge under the basic rule; **4 of 7** meet the stronger contrast rule. The result is not forced: Jing'an, Xujiahui, and Wujiaochang show high-intensity cells but only moderate density uplift relative to already dense districts.

Validation maps use one common logarithmic display scale for allocated people per 100 m cell. The log scale affects color only; it does not alter allocation. No reach polygon is drawn or queried.
The stars are declared approximate WGS84 cluster centres used only for validation windows; they are not official CBD or development-zone boundaries. Pudong density ratios also inherit Pudong's very large district-area denominator.

- [Lujiazui](../maps/cluster-lujiazui.png)
- [People's Square / Nanjing Road](../maps/cluster-peoples-square-nanjing-road.png)
- [Jing'an](../maps/cluster-jingan.png)
- [Xujiahui](../maps/cluster-xujiahui.png)
- [Zhangjiang](../maps/cluster-zhangjiang.png)
- [Wujiaochang](../maps/cluster-wujiaochang.png)
- [Hongqiao development area](../maps/cluster-hongqiao.png)

## Review files

- `core-employment-grid-100m.parquet`: Core I/J/M weights and exact integer allocations.
- `core-plus-base-employment-grid-100m.parquet`: Core hard controls plus Base 721/723/724/725.
- `core-plus-sensitivity-grid-100m.parquet`: Low/Base/High cell comparisons.
- `allocation-diagnostics.csv`: exact control reconciliation and concentration diagnostics.
- `cluster-validation.csv`: quantitative checks supporting the seven maps.
- `building-function-evidence-100m.parquet`: frozen derived OSM evidence.
- `source-manifest.csv`: source hashes, years, access, and reuse terms.

## Validation assessment

**Ready for spatial-framework review, with source-vintage and OSM-function coverage caveats.** Approval of this framework would authorize a later reach intersection; this commit itself contains no reach result or percentage.
