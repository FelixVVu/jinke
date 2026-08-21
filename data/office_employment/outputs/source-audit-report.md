# Jinke office-oriented employment: 2023 source-audit report

**Audit date:** 2026-08-21

**Scope:** official district × industry controls only; no spatial allocation, reach calculation, or model fitting

**Protected outputs:** the existing 3.69 million / 28.2% employment result, GDP model/results, Site, and production reach polygons are unchanged

## Decision summary

The official source gate is complete. Shanghai Economic Census Yearbook 2023 Table 1-9 provides **legal-entity employment by industry division and all 16 districts** in one internally consistent workbook. The selected office-oriented rows contain no missing district cells, each industry’s 16 district values sums exactly to its official Shanghai total, and the table’s all-industry district totals sum exactly to **13,099,795**.

The data are sufficient to supply official **district calibration controls** for two separately labelled, industry-based office-employment benchmarks:

- **Core office-oriented industries:** 2,477,585 workers, **18.913%** of Shanghai legal-entity employment;
- **Broad office-oriented industries:** 6,374,547 workers, **48.661%**.

They are not occupation-level “white-collar worker” counts and are not fine-geographic observed employment. A future spatial model would still need workplace-location evidence within districts, but it does not need another official district-employment source.

## Official source

| Field | Finding |
|---|---|
| Publisher | Shanghai Municipal Statistics Bureau |
| Table | [Table 1-9: legal-entity employment by industry major group and district](https://tjj.sh.gov.cn/tjnj/jjpcnj2023/zk/html/A1-09.xls) |
| Reference date | 31 December 2023 |
| Grain | 16 districts × 97 two-digit industry divisions, with section and city totals |
| Unit | People; integer counts |
| Employment definition | Persons working in the legal entity on the final day of the year and receiving wages or other labor remuneration; see the [official indicator definitions](https://tjj.sh.gov.cn/tjnj/jjpcnj2023/zk/html/zba01.pdf) |
| Individual businesses | Excluded; the separate individual-business table is not used |
| Finance | Included in the integrated city table: 546,845 workers across the 16 districts |
| All-industry reconciliation | 13,099,795, exactly matching the existing Shanghai legal-entity denominator |
| Retrieved workbook | 51,200 bytes; SHA-256 `b217fb6d1fdacf06cfd68e46b93c9f50536e566a3575581add57393a1c9b3d7a` |
| Classification standard | [GB/T 4754-2017, as amended](https://www.stats.gov.cn/xxgk/tjbz/gjtjbz/201710/t20171017_1758922.html) |
| Redistribution | Extracted official facts and citations are retained; the raw XLS is not redistributed |

This citywide table is preferable to stitching district bulletins together. It uses one publication, one universe, one reference date, one industry classification, and includes financial-sector records that some district geographic bulletins exclude.

## Industry definitions

### Core

Core is deliberately strict and uses only industry rows that are predominantly knowledge, finance, or technical-service workplaces at the published district grain:

- **I — Information transmission, software and information technology services**;
- **J — Financial services**;
- **M — Scientific research and technical services**.

Two-digit **72 — Business services** is excluded from Core. Although it includes headquarters management, consulting, legal, accounting, advertising, and human-resources activity, it also includes labor dispatch, security, cleaning, travel, conferences, and other non-office services. Table 1-9 cannot separate those subgroups by district.

### Broad

Broad includes Core and adds industries with substantial commercial, professional, administrative, or institutional workplace activity:

- **72 — Business services**;
- **K — Real estate**;
- **P — Education**;
- **Q — Health and social work**;
- **R — Culture, sports and entertainment**;
- **S — Public administration, social security and social organizations**.

Broad is not a claim that every included employee works in an office. It intentionally includes schools, hospitals, cultural venues, property operations, government services, security/cleaning, and other mixed workplaces. It is the sensitivity definition for a wider professional/institutional employment universe.

### Official city totals

| Code | Official industry | Core | Broad | Employment | Share of 13,099,795 |
|---|---|:---:|:---:|---:|---:|
| I | Information transmission, software and IT services | Yes | Yes | 1,058,551 | 8.081% |
| J | Financial services | Yes | Yes | 546,845 | 4.174% |
| M | Scientific research and technical services | Yes | Yes | 872,189 | 6.658% |
| 72 | Business services | No | Yes | 1,904,322 | 14.537% |
| K | Real estate | No | Yes | 601,432 | 4.591% |
| P | Education | No | Yes | 478,200 | 3.650% |
| Q | Health and social work | No | Yes | 428,065 | 3.268% |
| R | Culture, sports and entertainment | No | Yes | 150,609 | 1.150% |
| S | Public administration, social security and social organizations | No | Yes | 334,334 | 2.552% |
| **Core total** | I + J + M | — | — | **2,477,585** | **18.913%** |
| **Broad total** | Core + 72 + K + P + Q + R + S | — | — | **6,374,547** | **48.661%** |

The selected rows are mutually exclusive. Section L is not selected as a whole, because using L together with division 72 would double-count business services and would also add division 71 rental services.

## Official district controls

| District | All legal-entity employment | Core | Core / district | Broad | Broad / district |
|---|---:|---:|---:|---:|---:|
| Huangpu | 712,613 | 158,769 | 22.3% | 478,374 | 67.1% |
| Xuhui | 1,027,746 | 258,823 | 25.2% | 571,893 | 55.6% |
| Changning | 602,150 | 105,111 | 17.5% | 299,213 | 49.7% |
| Jing’an | 973,987 | 194,334 | 20.0% | 604,189 | 62.0% |
| Putuo | 524,969 | 100,906 | 19.2% | 288,085 | 54.9% |
| Hongkou | 409,389 | 71,077 | 17.4% | 226,952 | 55.4% |
| Yangpu | 510,562 | 146,985 | 28.8% | 322,470 | 63.2% |
| Minhang | 1,278,262 | 229,092 | 17.9% | 605,180 | 47.3% |
| Baoshan | 766,004 | 73,770 | 9.6% | 353,767 | 46.2% |
| Jiading | 873,958 | 112,899 | 12.9% | 307,556 | 35.2% |
| Pudong | 2,879,157 | 816,970 | 28.4% | 1,534,797 | 53.3% |
| Jinshan | 393,752 | 20,472 | 5.2% | 103,875 | 26.4% |
| Songjiang | 852,240 | 64,930 | 7.6% | 248,404 | 29.1% |
| Qingpu | 549,805 | 72,568 | 13.2% | 198,056 | 36.0% |
| Fengxian | 583,748 | 40,638 | 7.0% | 163,266 | 28.0% |
| Chongming | 161,453 | 10,241 | 6.3% | 68,470 | 42.4% |
| **Shanghai** | **13,099,795** | **2,477,585** | **18.9%** | **6,374,547** | **48.7%** |

The machine-readable district table retains the Chinese official district names and exact unrounded counts.

## Sufficiency assessment

| Test | Result | Consequence |
|---|---|---|
| All 16 districts present | Pass | Complete Shanghai denominator and district controls |
| One consistent official source | Pass | No cross-bulletin universe reconciliation required |
| Reference date and employment definition consistent | Pass | Core and Broad can be compared across districts |
| Finance available by district | Pass | Core finance is not left as a residual |
| Selected industry rows contain no blank district cells | Pass | No imputation or suppression handling required |
| Each selected industry reconciles district sum to city total | Pass | No hidden geographic residual in selected rows |
| District all-industry totals reconcile to 13,099,795 | Pass | Compatible with the existing legal-entity accounting universe |
| Core rows mutually exclusive and nested in Broad | Pass | No double counting |
| Street/town × industry employment available | No | Future within-district allocation remains model dependent |
| Occupation or actual office-building employment available | No | Results must be labelled industry based, not “all white-collar workers” |

### What the data are sufficient for

- fixed Shanghai Core and Broad denominators;
- exact district totals for each selected industry row;
- district-level calibration of a future independent office-oriented workplace surface;
- separate Core and Broad reach percentages without altering the existing all-industry benchmark.

### What the data are not sufficient for

- directly observing office employment inside the production reach;
- distinguishing office and non-office occupations within an included industry;
- locating district industry totals below district grain without additional evidence;
- capturing corporate-office occupations inside manufacturing, wholesale/retail, transport, construction, or other excluded industries;
- claiming that Broad employment is literal office-building occupancy.

These limitations affect the interpretation and future spatial allocation, but they do not create an official-control data gap. A future model should retain Core as the primary result and Broad as a sensitivity result, normalize each selected industry to its official district control, and keep the output entirely separate from the existing 28.2% all-industry benchmark.

## Reproducible workstream

- `office_employment_pipeline/source_audit.py` downloads and verifies the official XLS, extracts only the declared non-overlapping rows, and performs accounting checks. It contains no spatial model.
- `data/office_employment/manifests/source-manifest.csv` freezes source provenance.
- `data/office_employment/manifests/industry-scope-2023.csv` freezes the Core/Broad definitions and mixed-activity warnings.
- `data/office_employment/intermediate/district-industry-employment-2023.csv` contains 144 official district-industry records.
- `data/office_employment/outputs/district-office-employment-controls-2023.csv` contains the 16 district controls.
- `data/office_employment/outputs/city-office-employment-summary-2023.json` contains the reconciled city totals and scoped decision.

No model, 100 m grid, reach intersection, web JSON, UI change, merge, or deployment is included.

**PROCEED**
