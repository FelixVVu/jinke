# Jinke office-employment fine-control spatial framework

## Review status

The revised framework is complete for review. It allocates the eight audited priority districts to the existing 100 m EPSG:32651 lattice. **No reach polygon was intersected and no reach percentage was calculated.** GDP, general-employment outputs, reach polygons, and the Site remain outside this workstream.

Core remains the official district×industry hard control. Core+ Base remains central; Low and High retain the reviewed selected-72 district composition sensitivity. City controls remain **2,477,585 Core** and **3,220,710 Core+**.

## Accounting identity

The grid contains **172,233 unique physical cells**. Employment is reconciled at accounting-stratum grain, allocated within each stratum support, and aggregated once to physical cells.

Priority-district Core allocation: **1,852,975**.

| Core+ composition | Priority-district employment | Difference from Base |
|---|---|---|
| Low office intensity | 2,323,401 | -12,983 |
| Base | 2,336,384 | +0 |
| High office intensity | 2,349,367 | +12,983 |

## Control × industry matrix

The synthetic matrix contains **116 official fine accounting rows plus eight explicit residual rows**. Columns are I, J, M, selected 721/723/724/725, and an `OTHER` remainder. The independence prior is the maximum-entropy solution when only the two official margins are observed; RAS/IPF and deterministic controlled integer rounding retain both margins.

Across three Core+ composition cases the matrix has **2,976 cells**. All **348 scenario×fine-control row checks** equal their official totals exactly, every district×industry margin reconciles exactly, and each eight-district ledger totals 7,640,573.

The residual rows are required because published fine tables omit 526,062 district workers. Bulletin-identified finance residuals in Huangpu, Xuhui, Changning, Jing'an, Putuo, and Yangpu absorb official J before IPF; Hongkou and Pudong remain maximum-entropy residual compositions because their publications do not identify a sector split. This prevents excluded finance from being silently forced into street/town rows.

All **3,596 control×industry allocation checks** have zero difference. None of the positive allocations (3,335 records) needed the uniform no-evidence fallback.

Pudong's FTZ Bonded Area, Jinqiao ETDZ, and Zhangjiang High-Tech Park remain three immutable census rows. Overlap with ordinary streets is intentional: the employment rows are disjoint even when supports overlap. Each row enters the matrix and grid once. Restricted source geometry is not committed; only combined, non-zone-identifying physical-cell totals are published.

## Within-control weights

| Weight case | JRC volume | Building function | OSM establishments | Overture POIs |
|---|---|---|---|---|
| Base | 60% | 25% | 10% | 5% |
| Building-volume dominant | 75% | 15% | 7.5% | 2.5% |
| Workplace-evidence emphasis | 45% | 30% | 15% | 10% |

Every component remains raw and uncapped, is normalized within its own accounting stratum, and is combined linearly. There is no log transform, winsorization, district min–max normalization, smoothing, generic PPML, or uniform main allocation. All three weight cases preserve **2,336,384 priority-district Core+ Base workers exactly**.

Against Base, the building-volume-dominant case relocates **250,684 jobs between cells**, while workplace-evidence emphasis relocates **265,053**. These are half-L1 relocation measures; no employment is added or removed.

OSM `building:levels` is known for only **7.3%** of classified workplace buildings, so levels remain audited but unused. JRC volume provides the consistent magnitude signal; OSM footprint supplies building function.

## Change from district-direct allocation

Fine-control Base shifts **448,992 Core+ jobs** between 113 ordinary controls—**19.2%** of priority Core+ Base employment. Core alone shifts **346,246 jobs**. This is a relocation measure (half the summed absolute control changes), not new employment.

| District | Ordinary control | District-direct | Revised | Shift |
|---|---|---|---|---|
| 浦东新区 | 张江镇 | 101,371 | 164,769 | +63,398 |
| 浦东新区 | 高桥镇 | 67,006 | 28,105 | -38,902 |
| 浦东新区 | 潍坊新村街道 | 17,967 | 52,472 | +34,505 |
| 徐汇区 | 徐家汇街道 | 38,713 | 69,239 | +30,526 |
| 浦东新区 | 陆家嘴街道 | 48,716 | 71,811 | +23,095 |
| 浦东新区 | 高东镇 | 62,488 | 39,964 | -22,524 |
| 浦东新区 | 康桥镇 | 45,045 | 23,284 | -21,761 |
| 静安区 | 彭浦镇 | 61,105 | 40,303 | -20,802 |
| 黄浦区 | 小东门街道 | 13,167 | 33,464 | +20,297 |
| 徐汇区 | 虹梅路街道 | 65,961 | 85,989 | +20,028 |

| Architecture | Cell Gini | Top 1% share | Maximum cell | Cell HHI |
|---|---|---|---|---|
| Previous district-direct Base | 0.9322 | 40.00% | 4,909 | 0.000166 |
| Revised fine-control Base | 0.9441 | 45.16% | 6,040 | 0.000209 |
| Revised building-volume dominant | 0.9445 | 45.15% | 4,524 | 0.000196 |
| Revised workplace-evidence emphasis | 0.9469 | 47.16% | 9,029 | 0.000266 |

Versus district-direct Base, fine-control Base changes Gini by **+0.0119**, top-1% share by **+5.16 percentage points**, and maximum cell employment by **+1,131**.

## Workplace-cluster validation

A cluster emerges when its 1.5 km Core+ Base density is at least the containing district mean and its maximum local cell is at or above the 95th percentile of positive cells. Strong contrast requires at least 1.5× district density and a 90th-percentile local maximum.

| Cluster | District | Revised jobs | Revised ratio | Previous ratio | Ratio change | Emerges | Strong |
|---|---|---|---|---|---|---|---|
| Lujiazui | 浦东新区 | 72,387 | 14.97× | 10.78× | +4.20× | Yes | Yes |
| People's Square / Nanjing Road | 黄浦区 | 136,386 | 1.70× | 1.83× | -0.13× | Yes | Yes |
| Jing'an | 静安区 | 101,746 | 1.86× | 1.44× | +0.42× | Yes | Yes |
| Xujiahui | 徐汇区 | 79,570 | 1.96× | 1.19× | +0.76× | Yes | Yes |
| Zhangjiang | 浦东新区 | 96,979 | 20.09× | 11.43× | +8.66× | Yes | Yes |
| Wujiaochang | 杨浦区 | 27,838 | 1.41× | 1.26× | +0.15× | Yes | No |
| Hongqiao development area | 长宁区 | 42,298 | 1.56× | 1.71× | -0.15× | Yes | Yes |

All **7/7** centres emerge under the basic rule; **6/7** meet the stronger rule.

| Weight case | Basic emergence | Strong emergence | Minimum ratio | Maximum ratio |
|---|---|---|---|---|
| Base 60/25/10/5 | 7/7 | 6/7 | 1.41× | 20.09× |
| Building-volume dominant | 7/7 | 6/7 | 1.40× | 20.08× |
| Workplace-evidence emphasis | 7/7 | 6/7 | 1.47× | 20.17× |

Validation maps use one common logarithmic color scale. The scale affects display only; it does not alter allocation. No reach polygon is drawn or read.

- [Lujiazui](../maps/cluster-lujiazui.png)
- [People's Square / Nanjing Road](../maps/cluster-peoples-square-nanjing-road.png)
- [Jing'an](../maps/cluster-jingan.png)
- [Xujiahui](../maps/cluster-xujiahui.png)
- [Zhangjiang](../maps/cluster-zhangjiang.png)
- [Wujiaochang](../maps/cluster-wujiaochang.png)
- [Hongqiao development area](../maps/cluster-hongqiao.png)

## Review files

- `intermediate/control-industry-matrix-2023.csv`: three exact synthetic ledgers.
- `intermediate/control-industry-reconciliation.csv`: margins and residual treatment.
- `outputs/core-employment-grid-100m.parquet`: Core under Base weights.
- `outputs/core-plus-base-employment-grid-100m.parquet`: Core+ Base under Base weights.
- `outputs/core-plus-sensitivity-grid-100m.parquet`: Low/Base/High composition.
- `outputs/core-plus-weighting-sensitivity-grid-100m.parquet`: three weight cases.
- `outputs/control-shift-comparison.csv`: revised versus district-direct controls.
- `outputs/concentration-comparison.csv`: old and revised cell concentration.
- `outputs/cluster-validation.csv`: revised-versus-old cluster diagnostics.
- `outputs/cluster-weighting-sensitivity.csv`: cluster robustness by weight case.

## Validation assessment

**Ready for fine-control spatial-framework review, with synthetic within-control industry composition, residual-support, source-vintage, and OSM-function coverage caveats.** A later reach calculation requires separate approval; this revision contains no reach result or percentage.
