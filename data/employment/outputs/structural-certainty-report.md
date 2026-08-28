# Jinke employment benchmark — 50-minute structural-certainty report

## Scope and unchanged result

This audit decomposes the existing benchmark at the level of all 116 selected
fine accounting supports. It uses the exact pinned production 50-minute polygon
and does **not** fit, refit, or judge another global PPML specification.

The existing result remains unchanged:

**Estimated workplace employment within 50-minute reach: 3.69 million**

**28.2% of Shanghai's 2023 secondary- and tertiary-sector legal-entity employment**

The denominator remains 13,099,795. Individual-business employment is excluded.

## Classification tolerance

The relative support-area tolerance is **1e-06**,
or **0.0001%** of a
control's selected support. A control is effectively outside at or below that
fraction, effectively inside at or above
99.9999%,
and materially partial otherwise. This is a strict numerical/geometric tolerance,
not an employment-density assumption.

| Support class | Controls | Official employment | Shanghai denominator | PPML jobs inside | Current numerator |
|---|---|---|---|---|---|
| Effectively fully inside | 13 | 959,621 | 7.325% | 959,621 | 25.997% |
| Effectively fully outside | 34 | 1,786,761 | 13.640% | 0 | 0.000% |
| Materially partial | 69 | 4,368,129 | 33.345% | 2,598,863 | 70.406% |

The three rows account for all 7,114,511 fine-controlled workers. Their PPML jobs
inside sum to 3,558,484;
the remaining 132,774
in the current numerator is the separate central residual allocation.

## Allocation-free geometric bound

- Lower structural bound: **959,621 (7.325% of Shanghai)**.
- Upper structural bound: **5,327,750 (40.670% of Shanghai)**.
- Width: **4,368,129 workers / 33.345 percentage points**.

This is a bound on fine-controlled employment only. It includes every fully-inside
control total in the lower bound and allows zero-to-all employment from every
partial control. It deliberately excludes the 526,062 residual workers and the
Pudong functional-zone boundary perturbation.

Kept separate:

- Adding the all-residual upper ledger to the selected-support upper gives
  **5,853,812
  (44.686%)**.
- Moving the separately uncertain FTZ Bonded Area support to its conservative
  upper adds 149,000, for
  an explicit extreme ceiling of **6,002,812
  (45.824%)**.

These ledgers are shown together only to answer the ceiling question; they are not
collapsed into the structural bound or a confidence interval.

## Answers A–C

**A. 26.0% of the current 50-minute numerator is fixed directly by official fine-control totals without a within-control allocation model.**

That is 959,621
workers in fully-inside controls. It is
27.0%
of the fine-controlled numerator alone.

**B. 70.4% of the current numerator genuinely depends on allocation within partial controls.**

That is 2,598,863
PPML-allocated workers, or
73.0%
of the fine-controlled numerator. A further
3.6% of the current
numerator is the separately treated central residual and is neither A nor B.

**C. More than 40% is mathematically permitted by the accounting/geometric bound, but it is not a plausible central result; more than 50% is ruled out by the explicit extrema.**

The selected-support fine-control ceiling is only
40.670%. Reaching 40% with
residuals held separate would require
98.0%
of all employment in the 69 partial controls to sit inside their reach-facing
pieces—essentially the adversarial upper edge. The retained uniform/building/PPML
results are far lower. Even putting all 526,062 residual workers inside and applying
the separate conservative Pudong-zone boundary upper reaches only
45.824%,
not 50%.

## District decomposition

Counts are shown as inside/outside/partial. Bounds remain fine-control-only;
district residuals stay in the final column.

| District | I/O/P controls | Inside-control emp. | Outside-control emp. | Partial-control emp. | PPML fine jobs inside | Structural Shanghai-share bound | Residual separate |
|---|---|---|---|---|---|---|---|
| Huangpu | 7/0/3 | 448,634 | 0 | 189,645 | 626,946 | 3.425%–4.872% | 74,334 |
| Xuhui | 0/7/6 | 0 | 485,400 | 469,000 | 270,813 | 0.000%–3.580% | 73,346 |
| Changning | 1/1/8 | 37,808 | 101,760 | 457,408 | 184,105 | 0.289%–3.780% | 5,174 |
| Jing'an | 3/4/7 | 279,000 | 249,000 | 389,000 | 600,142 | 2.130%–5.099% | 56,987 |
| Putuo | 0/6/4 | 0 | 287,000 | 225,000 | 29,385 | 0.000%–1.718% | 12,969 |
| Hongkou | 1/2/5 | 40,429 | 52,708 | 286,696 | 250,765 | 0.309%–2.497% | 29,556 |
| Yangpu | 0/4/8 | 0 | 96,893 | 404,130 | 200,664 | 0.000%–3.085% | 9,539 |
| Pudong | 1/10/28 | 153,750 | 514,000 | 1,947,250 | 1,395,664 | 1.174%–16.038% | 264,157 |

## Partial-control model spread

For each partial control the detailed CSV reports official employment, exact support
area fraction, uniform/building/PPML jobs inside, the maximum-minus-minimum difference,
and its Shanghai percentage-point contribution. The aggregate partial totals span
121,120
jobs (0.925
percentage points). Summing control-level absolute spreads gives
332,029
jobs because model differences offset across controls.

Top 10 controls by local model spread:

| Rank | District | Control | Official emp. | Area inside | Uniform | Building | PPML | Max−min |
|---|---|---|---|---|---|---|---|---|
| 1 | 浦东新区 | 金桥经济技术开发区 | 203,000 | 47.423% | 96,269 | 64,690 | 79,080 | 31,579 |
| 2 | 虹口区 | 广中路街道 | 33,773 | 13.021% | 4,398 | 28,387 | 9,886 | 23,989 |
| 3 | 浦东新区 | 三林镇 | 96,000 | 17.293% | 16,601 | 35,716 | 23,351 | 19,115 |
| 4 | 浦东新区 | 张江高科技园区 | 469,000 | 95.855% | 449,559 | 467,790 | 461,776 | 18,231 |
| 5 | 徐汇区 | 徐家汇街道 | 216,300 | 35.436% | 76,648 | 89,512 | 92,206 | 15,558 |
| 6 | 静安区 | 天目西路街道 | 161,000 | 77.245% | 124,365 | 137,627 | 133,800 | 13,262 |
| 7 | 浦东新区 | 周浦镇 | 48,000 | 19.881% | 9,543 | 21,713 | 11,860 | 12,170 |
| 8 | 杨浦区 | 五角场街道 | 105,944 | 26.464% | 28,037 | 16,372 | 22,112 | 11,665 |
| 9 | 长宁区 | 仙霞新村街道 | 20,827 | 26.102% | 5,436 | 16,139 | 8,445 | 10,703 |
| 10 | 静安区 | 宝山路街道 | 21,000 | 86.912% | 18,252 | 10,777 | 16,427 | 7,475 |

The smallest ranked set reaching at least 80% contains
**28 controls** and
accounts for **80.35%**
of summed local model spread:

| Rank | District | Control | Max−min jobs | Shanghai pp | Cumulative |
|---|---|---|---|---|---|
| 1 | 浦东新区 | 金桥经济技术开发区 | 31,579 | 0.241 | 9.5% |
| 2 | 虹口区 | 广中路街道 | 23,989 | 0.183 | 16.7% |
| 3 | 浦东新区 | 三林镇 | 19,115 | 0.146 | 22.5% |
| 4 | 浦东新区 | 张江高科技园区 | 18,231 | 0.139 | 28.0% |
| 5 | 徐汇区 | 徐家汇街道 | 15,558 | 0.119 | 32.7% |
| 6 | 静安区 | 天目西路街道 | 13,262 | 0.101 | 36.7% |
| 7 | 浦东新区 | 周浦镇 | 12,170 | 0.093 | 40.3% |
| 8 | 杨浦区 | 五角场街道 | 11,665 | 0.089 | 43.8% |
| 9 | 长宁区 | 仙霞新村街道 | 10,703 | 0.082 | 47.1% |
| 10 | 静安区 | 宝山路街道 | 7,475 | 0.057 | 49.3% |
| 11 | 静安区 | 共和新路街道 | 7,473 | 0.057 | 51.6% |
| 12 | 杨浦区 | 四平路街道 | 7,264 | 0.055 | 53.8% |
| 13 | 普陀区 | 宜川路街道 | 7,052 | 0.054 | 55.9% |
| 14 | 浦东新区 | 上钢新村街道 | 6,891 | 0.053 | 58.0% |
| 15 | 徐汇区 | 斜土路街道 | 6,696 | 0.051 | 60.0% |
| 16 | 浦东新区 | 北蔡镇 | 6,566 | 0.050 | 61.9% |
| 17 | 长宁区 | 天山路街道 | 6,244 | 0.048 | 63.8% |
| 18 | 杨浦区 | 大桥街道 | 5,834 | 0.045 | 65.6% |
| 19 | 浦东新区 | 张江镇 | 5,529 | 0.042 | 67.3% |
| 20 | 黄浦区 | 五里桥街道 | 5,515 | 0.042 | 68.9% |
| 21 | 浦东新区 | 陆家嘴街道 | 5,454 | 0.042 | 70.6% |
| 22 | 长宁区 | 新华路街道 | 5,187 | 0.040 | 72.1% |
| 23 | 浦东新区 | 康桥镇 | 5,004 | 0.038 | 73.6% |
| 24 | 浦东新区 | 川沙新镇 | 4,683 | 0.036 | 75.0% |
| 25 | 浦东新区 | 金桥镇 | 4,647 | 0.035 | 76.4% |
| 26 | 浦东新区 | 南码头路街道 | 4,463 | 0.034 | 77.8% |
| 27 | 徐汇区 | 湖南路街道 | 4,272 | 0.033 | 79.1% |
| 28 | 浦东新区 | 唐镇 | 4,253 | 0.032 | 80.3% |

## Top 10 fine-scale data priorities

The structural bound is still very wide. For allocation-free uncertainty, the
maximum reduction from resolving one partial stratum is its full official control
employment. These are therefore the ten highest-value controls for improved
workplace information (model spread is shown as a secondary diagnostic):

| Priority | District | Control | Official emp. | Area inside | Model max−min |
|---|---|---|---|---|---|
| 1 | 浦东新区 | 张江高科技园区 | 469,000 | 95.855% | 18,231 |
| 2 | 徐汇区 | 徐家汇街道 | 216,300 | 35.436% | 15,558 |
| 3 | 浦东新区 | 金桥经济技术开发区 | 203,000 | 47.423% | 31,579 |
| 4 | 浦东新区 | 陆家嘴街道 | 200,750 | 97.283% | 5,454 |
| 5 | 静安区 | 天目西路街道 | 161,000 | 77.245% | 13,262 |
| 6 | 长宁区 | 新泾镇 | 148,418 | 3.344% | 2,532 |
| 7 | 虹口区 | 北外滩街道 | 133,468 | 99.742% | 344 |
| 8 | 黄浦区 | 外滩街道 | 113,352 | 99.299% | 794 |
| 9 | 杨浦区 | 五角场街道 | 105,944 | 26.464% | 11,665 |
| 10 | 浦东新区 | 三林镇 | 96,000 | 17.293% | 19,115 |

## Review status

This report adds a structural audit only. The current 3.69 million / 28.2% result,
its failed calibrated-model gate, the GDP model and files, production reach polygons,
and Site/UI remain unchanged. Nothing is merged or deployed.
