# Jinke employment benchmark v1 decision report

## Primary result

**Estimated workplace employment within 50-minute reach: 3.69 million**

**28.2% of Shanghai's 2023 secondary- and tertiary-sector legal-entity employment**

The exact denominator is 13,099,795. Individual-business employment is excluded.
All boundary supports are approximate.

## Uncertainty decomposition

- **Residual-location range:** 27.2–31.2%
- **Spatial-allocation/model range:** 27.7–28.7%
- **Boundary sensitivity:** ±4.1 percentage points (conservative asymmetric envelope -4.1/+2.1; reach-edge ±100 m alone -1.8/+1.6)
- Publication rounding at 50 minutes is -0.057/+0.054 percentage points and is immaterial.

These are separate sensitivity dimensions, not a confidence interval, and they are
not added together.

## Model comparison

| Model | Employment inside 50 min | Shanghai share |
|---|---:|---:|
| Uniform within control | 3,634,010 | 27.741% |
| Raw JRC non-residential building volume | 3,755,130 | 28.666% |
| Calibrated workplace PPML (model-contingent central) | 3,691,258 | 28.178% |

The raw-building surface is highest because the reach captures a disproportionate
share of dense non-residential built volume. Uniform allocation spreads employment
into peripheral portions of partially intersected controls. The calibrated surface
uses uncapped building volume plus interpretable workplace POI categories and lands
between them. Every final surface is normalized within each census accounting
control, so published control totals are preserved exactly. That reconciliation does
not validate the within-control surface.

Six contiguous citywide spatial-block holdouts give MAE 27,522,
WAPE 44.9%, MAPE
56.1%, and Spearman rank correlation
0.706. For top-quartile controls, MAE is
63,123, WAPE 45.0%,
and rank correlation 0.199. The audit records
9 obvious top-control
underpredictions rather than concealing them.

The nonlinear Poisson boosting alternative gives top-control WAPE
46.1%
with rank correlation
-0.172
and 12
severe misses. It does not improve the aggregate high-control diagnostics and fails
the same scientific acceptance gate, so it is retained as a diagnostic and is not
silently substituted as the 100 m allocation surface.

## 50-minute district contributions

| District | Exact district employment | Fine controlled | Residual | Inside reach | District captured | Reach contribution | Boundary |
|---|---:|---:|---:|---:|---:|---:|---|
| Huangpu | 712,613 | 638,279 | 74,334 | 701,280 | 98.4% | 19.0% | OSM; approximate |
| Xuhui | 1,027,746 | 954,400 | 73,346 | 270,813 | 26.4% | 7.3% | OSM; approximate |
| Changning | 602,150 | 596,976 | 5,174 | 186,121 | 30.9% | 5.0% | OSM; approximate |
| Jing'an | 973,987 | 917,000 | 56,987 | 654,875 | 67.2% | 17.7% | OSM; approximate |
| Putuo | 524,969 | 512,000 | 12,969 | 31,076 | 5.9% | 0.8% | OSM; approximate |
| Hongkou | 409,389 | 379,833 | 29,556 | 250,765 | 61.3% | 6.8% | OSM; approximate |
| Yangpu | 510,562 | 501,023 | 9,539 | 200,664 | 39.3% | 5.4% | OSM; approximate |
| Pudong | 2,879,157 | 2,615,000 | 264,157 | 1,395,664 | 48.5% | 37.8% | OSM; approximate |

## Pudong accounting strata

| Stratum | Employment | Inside reach | Captured | Approximate support |
|---|---:|---:|---:|---|
| FTZ Bonded Area | 149,000 | 0 | 0.0% | yes |
| Jinqiao ETDZ | 203,000 | 79,080 | 39.0% | yes |
| Zhangjiang High-Tech Park | 469,000 | 461,776 | 98.5% | yes |
| ordinary streets/towns | 1,794,000 | 854,809 | 47.6% | yes |
| Pudong residual | 264,157 | 0 | 0.0% | yes |

Functional-zone counts remain immutable, separate rows and are never merged into
host streets/towns. Their source polygons are not redistributed. The reported-area
morphology comparison changes the 50-minute city share by
+0.002 percentage points,
but the conservative 0%/100% support envelope drives the broader boundary range.

## GDP diagnostic

The existing 50-minute GDP share is 21.622%.
GDP share / employment share is
**0.767**, implying GDP per worker inside
the reach is **76.7% of the Shanghai
average** under the two independent benchmark surfaces. This is a diagnostic, not a
causal productivity estimate. The GDP pipeline and result were not changed or rerun.

## Classification

**NOT YET RELIABLE**

The accounting benchmark is complete, but the calibrated spatial surface is not.
High-employment controls remain poorly ranked and materially underpredicted under
both PPML and a nonlinear Poisson alternative. The open boundary vintage, Pudong
functional-zone scope, and unresolved residual locations add further uncertainty.
