# Jinke office-oriented employment: refined 2023 source audit

**Audit date:** 2026-08-21

**Scope:** industry definitions and official control sufficiency only; no spatial allocation, reach calculation, or model fitting

**Protected outputs:** the existing 3.69 million / 28.2% employment result, GDP model/results, Site, and production reach polygons are unchanged

## Revised decision summary

Three differently labelled universes should be retained:

| Definition | Composition | Shanghai employment | Share of 13,099,795 | Status |
|---|---|---:|---:|---|
| **Core office-oriented** | I + J + M | **2,477,585** | **18.913%** | Primary conservative official benchmark |
| **Core+ office-oriented** | Core + 721 + 723 + 724 + 725 | **3,220,710** | **24.586%** | Preferred expanded office-oriented benchmark |
| **Broad professional/institutional** | Core + full 72 + K + P + Q + R + S | **6,374,547** | **48.661%** | Optional sensitivity only; not a white-collar metric |

Core remains unchanged. Core+ adds **743,125** workers from four official three-digit groups within business services, equal to **39.023%** of division 72. Education, health and social work, culture/sports/entertainment, public administration/social organizations, and real estate are not in Core+.

The Core+ Shanghai denominator is directly observed from official census totals. Its district split must be partly modelled because the official publication does not provide district × three-digit-industry employment.

## Official sources and granularity

| Table | Published grain | Use | Limitation |
|---|---|---|---|
| [1-9: legal-entity employment by industry division and district](https://tjj.sh.gov.cn/tjnj/jjpcnj2023/zk/html/A1-09.xls) | 16 districts × industry sections/divisions | Exact district I, J, M, full 72, K, P, Q, R, and S controls | No three-digit group within district |
| [1-3: legal-entity units and employment by industry middle group](https://tjj.sh.gov.cn/tjnj/jjpcnj2023/zk/html/A1-03.xls) | Shanghai city × three-digit group | Exact 721–729 city totals and Core+ denominator | No district cross-tab |
| [GB/T 4754-2017](https://www.stats.gov.cn/xxgk/tjbz/gjtjbz/201710/t20171017_1758922.html) | Official industry hierarchy and activity definitions | Inclusion/exclusion rules | Classification, not employment data |
| [Main indicator definitions](https://tjj.sh.gov.cn/tjnj/jjpcnj2023/zk/html/zba01.pdf) | Legal-entity and year-end employment definitions | Common statistical universe | Not an occupational classification |

Table 1-3 is pinned at 112,128 bytes and SHA-256 `301aedcbc88cd488dac47697b31af42d10ae19334f16f96e47c5a0cb1b2b68d2`. Its nine groups reconcile exactly to the Table 1-9 division-72 total of 1,904,322.

The enterprise-only companion tables do not solve the missing cross-tab. Table 2-4 reports city × middle group, while Table 2-6 reports district × division. Table 4-13 reports the combined rental-and-business-services section by district and rounds employment to 0.1 ten-thousand persons. None publishes district × 721–729 legal-entity employment.

## Core: unchanged

Core is the conservative, fully official district-controlled benchmark:

- **I — Information transmission, software and information technology services:** 1,058,551;
- **J — Financial services:** 546,845;
- **M — Scientific research and technical services:** 872,189.

Total: **2,477,585**, or **18.913%** of Shanghai legal-entity employment.

Core is industry based, not occupation based. It includes non-desk jobs inside these industries and excludes corporate-office occupations employed by industries outside I/J/M.

## Core+: selected business-service groups

| Code | Official group | Employment | Share of division 72 | Core+ | Reason |
|---|---|---:|---:|:---:|---|
| 721 | Organization management services | 228,288 | 11.988% | Yes | Headquarters, investment/asset management, rights exchange, and related management are predominantly office oriented |
| 722 | Integrated management services | 54,595 | 2.867% | No | Park, commercial-complex, market, and supply-chain management mix office and operational work |
| 723 | Legal services | 50,311 | 2.642% | Yes | Predominantly professional office services |
| 724 | Consulting and investigation | 363,868 | 19.107% | Yes | Accounting, audit, tax, research, and professional consulting are predominantly office oriented |
| 725 | Advertising | 100,658 | 5.286% | Yes | Predominantly office/creative-workplace activity |
| 726 | Human-resources services | 791,271 | 41.551% | No | Labor dispatch and outsourcing-related activity cannot be separated from recruitment and consulting |
| 727 | Security-protection services | 179,327 | 9.417% | No | Predominantly operational employment |
| 728 | Conference, exhibition and related services | 37,521 | 1.970% | No | Planning cannot be separated from venue, logistics, and event operations |
| 729 | Other business services | 98,483 | 5.172% | No | Travel, packaging, office, translation, agency, ticketing, credit, and other services are too heterogeneous |
| **Division 72** | **Business services** | **1,904,322** | **100.000%** | — | — |

Cleaning is not in division 72 under GB/T 4754-2017; it is group 821 and is not included in Core, Core+, or the existing Broad definition.

### Important 721 caveat

Group 721 also contains unit-logistics management and rural collective management. Four-digit 721 employment is not published, so full inclusion is not occupation-pure. It is retained because the group is predominantly organization-management activity and Core+ is explicitly industry based.

A stricter diagnostic excluding all of 721 would be **2,992,422 workers (22.843%)**. This is not the recommended Core+ denominator; it records the maximum definitional effect of the unresolved 721 composition.

## Proposed Core+ district-control method

The following official margins are available:

- exact district totals for division 72 from Table 1-9;
- exact city totals for groups 721–729 from Table 1-3;
- exact selected city subtotal 721 + 723 + 724 + 725 = 743,125.

The official tables do not identify how that selected subtotal is distributed across districts. The least-assumptive constrained estimate is the maximum-entropy independence solution:

`estimated selected-72 employment in district d = official district-72 employment × 743,125 / 1,904,322`

Integer controls should use largest-remainder rounding so the 16 district estimates sum exactly to 743,125. This would preserve every observed district-72 margin and the observed city Core+ subtotal without introducing unobserved district industry patterns.

This would be a district composition estimate, not spatial allocation within districts. Every resulting Core+ district control must carry `core_plus_72_is_modelled = true`. The construction is deliberately left to the next implementation commit.

## Broad: relabelled sensitivity only

Broad retains the previous arithmetic definition and denominator:

`Core + full 72 + K + P + Q + R + S = 6,374,547 (48.661%)`

Its label is now **Broad professional/institutional employment sensitivity**. It is not the main white-collar or office-employment metric because it includes property operations, labor dispatch, security, schools, hospitals, cultural/sports venues, public administration, and other mixed workplaces.

## Sufficiency and next gate

The evidence is sufficient to freeze:

- an exact official Core denominator and exact Core district controls;
- an exact official Core+ Shanghai denominator;
- a transparent specification for a constrained, explicitly modelled Core+ district bridge;
- an unchanged Broad professional/institutional sensitivity denominator.

It is not sufficient to call Core+ district composition directly observed, to infer occupation, or to estimate employment inside any reach polygon. No spatial allocation should begin until the user approves the revised definitions and the partly modelled district-72 bridge.

No employment result, GDP result, web asset, reach polygon, UI, merge, or deployment was changed.

**STOP FOR REVIEW**
