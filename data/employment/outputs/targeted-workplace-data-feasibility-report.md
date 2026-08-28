# Jinke employment benchmark: targeted workplace-data feasibility audit

**Review date:** 2026-08-21

**Scope:** the 14 materially partial controls named after the 50-minute structural-certainty audit

**Decision use:** whether independent fine-scale evidence can materially narrow the existing uniform/building/PPML allocation range

**Protected result:** the existing 50-minute result remains **3.69 million / 28.2%**; this report does not reallocate employment or fit a model

## Technical summary

No public source located in this audit provides direct employment below the existing 2023 street/town or Pudong functional-zone accounting rows. The official Fifth Economic Census bulletins contain separate industry and geographic tables, but no public industry-by-street cross-tab, establishment-location table, development-zone subarea employment table, or inside/outside-reach split. Establishment-level census records are not a practical substitute: identifiable statistical records are protected by Article 28 of the [Statistics Law](https://www.stats.gov.cn/xxgk/zcfggz/tjfl2020/202410/t20241010_1956870.html), and the [national microdata catalog](https://microdata.stats.gov.cn/) currently lists the Third, not Fifth, Economic Census.

Two source classes can improve the evidence:

- **Immediately reproducible open evidence:** [CMAB version 7](https://figshare.com/articles/dataset/CMAB-The_World_s_First_National-Scale_Multi-Attribute_Building_Dataset/27992417), a CC BY 4.0 building-level dataset with footprints, height, volume, and predicted function. It is finer and independent of the current JRC grid, but it remains a building-use proxy rather than a workplace count. Its function labels are modelled, partly from map AOI/POI, and should not be treated as observed employment. [The methods paper](https://www.nature.com/articles/s41597-025-04730-5) reports national validation, not control-specific Shanghai workplace accuracy.
- **Workplace-specific evidence requiring a contract:** [Baidu Huiyan](https://huiyan.baidu.com/products/popgeoapiservice) explicitly offers work-population grids and arbitrary-area analysis with historical capability. A licensed 2023 snapshot could distinguish the exact reached and unreached portions of each control. It is still a mobile-device workplace proxy, not the legal-entity census universe, so it must only inform within-control shares and must be normalized to the official control totals.

The 14 controls sum to **1.320 Shanghai percentage points of additive, non-directional control-level max-minus-min spread**. The actual aggregate range is only **0.925 points** (27.741%–28.666%) because model deviations offset across controls. Consequently, control-level spreads cannot simply be added to claim a narrower aggregate interval.

Under an explicit portfolio sensitivity—not a new estimate—the realistic benefit is:

- open building/context/metro evidence: about **0.10 pp** for the top 5, **0.14 pp** for the top 10, and **0.22 pp** for the top 20;
- a documented workplace-population or insured-establishment acquisition that resolves 70% of selected-control disagreement: about **0.23 pp**, **0.32 pp**, and **0.51 pp**, respectively;
- even perfect inside/outside shares for the top 5 would leave an aggregate model range of about **0.60 pp**.

The data implication is narrow: open morphology can test the most conspicuous allocation failures, but a material reduction in the 27.7%–28.7% model range requires contracted workplace-specific evidence. It does not require or justify another generic global PPML model.

## Scope, definitions, and invariants

- Statistical universe and denominator are unchanged: **13,099,795 people employed by Shanghai legal entities engaged in secondary- and tertiary-sector activity at 31 December 2023**.
- The existing production 50-minute polygon, 116 accounting controls, selected supports, residual treatment, and 3.69 million / 28.2% result are unchanged.
- “Direct employment” in this audit means an observed employment count or workplace-person count at a grain capable of separating the exact reached and unreached parts of the accounting control. A control-total publication is not direct fine-scale data.
- “Strong independent proxy” means a new source independent of the current JRC/Overture allocation surface, available at building/grid/point grain, and materially capable of discriminating the reached portion for that control. It is not equivalent to observed census employment.
- “No practical improvement” means that even perfect fine-scale information has negligible leverage on the reported Shanghai share.
- Job-vacancy postings were not searched or used as employment counts.

Machine-readable audit artifacts:

- `data/employment/manifests/workplace-source-candidates.csv`: 121 control-source records with provider, year, grain, measure, access, license, reproducibility, exact-reach discrimination, and control-specific usefulness;
- `data/employment/outputs/workplace-data-feasibility-controls.csv`: the 14-control decision table;
- `data/employment/outputs/workplace-data-feasibility-portfolios.csv`: reproducible range-reduction scenarios.

## Finer official-census search

### Result

**No finer public Fifth Economic Census employment table was found for any of the 14 controls.**

The district bulletins lock the accounting universe and control totals. For example, Huangpu publishes industry totals separately from Table 1-5’s street employment rows in its [official bulletin](https://www.shhuangpu.gov.cn/uploadfile/fcba008c-ee33-44f4-bfe0-8cbb16faaf83/%E4%B8%8A%E6%B5%B7%E5%B8%82%E9%BB%84%E6%B5%A6%E5%8C%BA%E7%AC%AC%E4%BA%94%E6%AC%A1%E5%85%A8%E5%9B%BD%E7%BB%8F%E6%B5%8E%E6%99%AE%E6%9F%A5%E4%B8%BB%E8%A6%81%E6%95%B0%E6%8D%AE%E5%85%AC%E6%8A%A5%EF%BC%88%E6%9C%80%E7%BB%88%E5%8F%91%E5%B8%83%E7%A8%BF%EF%BC%891%E5%8F%B7.pdf); the [Pudong bulletin](https://www.pudong.gov.cn/zwgk/tjj_gkml_ywl_tjsj_gb/2025/295/347226.html) publishes street, town, and development-zone rows but no sub-zone workplace locations. The same pattern holds for Xuhui, Changning, Jing’an, Hongkou, and Yangpu.

The National Bureau of Statistics provides a controlled [microdata application process](https://www.stats.gov.cn/zt_18555/zthd/lhfw/2022/rdwt/202302/t20230214_1903571.html) for eligible universities and research institutions, with secure-lab use and output review. This is not reproducibly available to this PR, and the current catalog does not expose Fifth Economic Census microdata. It is therefore not classified as an available source.

### Negative findings preserved

- No public industry × street/town employment cross-tab.
- No public establishment-address table linked to Fifth Economic Census employment.
- No public subarea employment split within Jinqiao ETDZ or Zhangjiang High-Tech Park.
- No public street-level legal-entity employment grid.
- No official public AM-peak metro alighting table was located; the Shanghai open-data platform advertises station entry/exit flows, which are validation data only.

## Candidate-source assessment

The full source-by-control ledger is in `workplace-source-candidates.csv`. This table summarizes the shared source classes.

| Source | Year / grain | Measures | Access and reuse | Reproducibility | Exact reach split? | Audit finding |
|---|---|---|---|---|---|---|
| District Fifth Economic Census bulletins | 2023; control aggregate | Legal-entity employment and legal-unit counts | Public official HTML/PDF; cite source | Yes for aggregates | No | Essential accounting control; no finer public table found |
| Pudong Statistical Yearbook, Tables 20-1 to 20-3 | 2023–2024; whole reported zone | Jinqiao/Zhangjiang employees; Lujiazui office stock and occupancy; enterprise/economic indicators | Public [official PDF](https://www.pudong.gov.cn/assets/xls/tjj/2025/%E7%AC%AC%E4%BA%8C%E5%8D%81%E7%AF%87%20%E9%87%8D%E7%82%B9%E5%BC%80%E5%8F%91%E5%8C%BA%E5%92%8C%E8%A1%97%E9%95%87.pdf) | Yes for published aggregates | No | Strong aggregate validation, but scopes are not proven identical to census strata and have no subarea split |
| Other official control/cluster pages | Mostly 2019–2025; named buildings, parks, malls, or parcels | Enterprises, office buildings, parks, retail/innovation anchors | Public district-government pages | Yes for published facts | Usually no | Useful anchor validation; incomplete and not employment-weighted |
| Baidu Huiyan | Contract-defined; request stable 2023 grid/custom polygons | Work population, service population, commuting/activity | Commercial API/DaaS/offline extract; raw redistribution assumed prohibited absent written license | Conditional on contract, frozen parameters, and retained extract | Yes | Strongest workplace-specific candidate; device/population bias and universe mismatch remain |
| Shanghai metro entry/exit flows | Daily or real time; station point | Passenger entries/exits | [Shanghai Public Data Open Platform](https://data.sh.gov.cn/); access may be unconditional or application-based under Shanghai public-data terms | Conditional on historical retention/access | No | Independent timing/activity validation only; not employment or AM-peak alightings as currently documented |
| Shanghai official registry | Current record; registered-address point | Enterprise name, address, status, scope | [Identity-verified record lookup](https://fw.scjgj.sh.gov.cn/achieve_outer/apply/notice); no bulk license found | Not practical at full-control scale | Geometrically yes, substantively imperfect | Registered address is not necessarily workplace; no public bulk employment weights |
| Qichacha API | Current/latest annual report; enterprise point | Industry, branches, address, insured count | [Commercial JSON API](https://openapi.qcc.com/dataApi/736), use-case approval, listed 6 RMB/query, contract-restricted | Conditional on a frozen enterprise universe and raw-response/missingness ledger | Geometrically yes, substantively imperfect | Stronger than POI counts, but missing insured counts, branch/head-office duplication, and centralized enrollment require correction |
| CMAB v7 | 2025 dataset; imagery mainly 2022–2024; building polygon | Footprint, height, volume, predicted function | Public 15.81 GB Figshare archive, CC BY 4.0 | Yes with version and checksum | Yes | Best new open proxy; no observed workplace count and function accuracy must be validated locally |
| GlobalBuildingAtlas | 2025; building polygon/height | Footprint, height, volume | Public [cloud distribution](https://source.coop/tge-labs/globalbuildingatlas-lod1); component-specific ODbL/usage terms must be checked | Yes with version/partition/hash | Yes | Independent building-volume cross-check; weaker than CMAB because it lacks function |
| Existing JRC / Overture inputs | JRC 2020 at 100 m; Overture 2026 place points | Non-residential volume and POI categories | Already frozen in PR #16 | Yes | Yes through existing geometry | Baseline only; not independent improvement |

Shanghai’s public-data rules distinguish direct/API access for unconditional data from application and data-use agreements for conditional data; the [Interim Measures](https://www.shanghai.gov.cn/nw48156/20200825/0001-48156_62825.html) also require source attribution. Historical 2023 metro retention and exact access conditions must be confirmed before treating the dataset as reproducible.

## Control status and uncertainty priority

“Spread” is the current maximum-minus-minimum of uniform, JRC-building, and PPML jobs inside the 50-minute reach, divided by 13,099,795. It is a sensitivity diagnostic, not a probability interval.

| Impact rank | Control | District | Support area inside | Spread (Shanghai pp) | Status | Feasibility rank |
|---:|---|---|---:|---:|---|---:|
| 1 | 金桥经济技术开发区 | 浦东新区 | 47.42% | 0.241 | **STRONG INDEPENDENT PROXY AVAILABLE** | 11 |
| 2 | 广中路街道 | 虹口区 | 13.02% | 0.183 | **STRONG INDEPENDENT PROXY AVAILABLE** | 4 |
| 3 | 三林镇 | 浦东新区 | 17.29% | 0.146 | **ONLY EXISTING JRC/POI-TYPE PROXIES AVAILABLE** | 13 |
| 4 | 张江高科技园区 | 浦东新区 | 95.85% | 0.139 | **STRONG INDEPENDENT PROXY AVAILABLE** | 12 |
| 5 | 徐家汇街道 | 徐汇区 | 35.44% | 0.119 | **STRONG INDEPENDENT PROXY AVAILABLE** | 1 |
| 6 | 天目西路街道 | 静安区 | 77.25% | 0.101 | **STRONG INDEPENDENT PROXY AVAILABLE** | 2 |
| 7 | 周浦镇 | 浦东新区 | 19.88% | 0.093 | **ONLY EXISTING JRC/POI-TYPE PROXIES AVAILABLE** | 14 |
| 8 | 五角场街道 | 杨浦区 | 26.46% | 0.089 | **STRONG INDEPENDENT PROXY AVAILABLE** | 3 |
| 9 | 仙霞新村街道 | 长宁区 | 26.10% | 0.082 | **ONLY EXISTING JRC/POI-TYPE PROXIES AVAILABLE** | 7 |
| 10 | 宝山路街道 | 静安区 | 86.91% | 0.057 | **ONLY EXISTING JRC/POI-TYPE PROXIES AVAILABLE** | 6 |
| 11 | 陆家嘴街道 | 浦东新区 | 97.28% | 0.042 | **STRONG INDEPENDENT PROXY AVAILABLE** | 5 |
| 12 | 新泾镇 | 长宁区 | 3.34% | 0.019 | **ONLY EXISTING JRC/POI-TYPE PROXIES AVAILABLE** | 8 |
| 13 | 外滩街道 | 黄浦区 | 99.30% | 0.006 | **NO PRACTICAL IMPROVEMENT AVAILABLE** | 9 |
| 14 | 北外滩街道 | 虹口区 | 99.74% | 0.003 | **NO PRACTICAL IMPROVEMENT AVAILABLE** | 10 |

No control qualifies as **DIRECT EMPLOYMENT DATA AVAILABLE**.

### Control-specific findings

1. **金桥经济技术开发区:** The Pudong yearbook reports 208,500 end-term employees in 2023, close to but not identical with the rounded 203,000 census row. It is an independent aggregate check, not a sub-control split. CMAB is well suited to industrial/office morphology, but the central obstacle is accounting support: the official [29.38 km² planning scope](https://www.pudong.gov.cn/zwgk/006003002/2022/302/257742.html) is not proven equal to the census stratum. A workplace grid needs an authoritative zone-member roster or census-zone support to be decisive.
2. **广中路街道:** This is the highest-return open pilot. Building allocation puts 28,387 jobs inside versus 4,398 uniform and 9,886 PPML. Building-level CMAB can test whether the reached 13.0% genuinely contains a concentrated office/industrial cluster. Hongkou’s official high-tech-zone description identifies office/park anchors, but not a complete employment-weighted list.
3. **三林镇:** Mixed residential, logistics, institutional, and commercial land use defeats simple building-volume interpretation. No finer official employment or enterprise table was found. A repeated 2023-compatible work-population grid is the practical discriminator.
4. **张江高科技园区:** The Pudong yearbook’s Zhangjiang-area employment is direct aggregate context but its reported area is broader/different from the 469,000-worker census stratum. The control is already 95.85% inside by selected support; the 0.139-point model spread and separate boundary uncertainty should not be conflated. CMAB helps identify R&D/industrial clusters, but a zone roster/support remains necessary.
5. **徐家汇街道:** CMAB, geocoded insured establishments, and mobile work population are all technically capable of separating the reached 35.4%. Officially named commercial, education, health, and institutional anchors plus station flows provide independent validation, not weights.
6. **天目西路街道:** Dense rail-station, office, hotel, and wholesale clusters make building-level function useful. Station exits can validate the spatial pattern, but mobile work population is needed to distinguish workplace intensity from passenger interchange.
7. **周浦镇:** As in Sanlin, open building products remain too indirect for a mixed town. No practical public sub-control workforce table was found. Mobile work population or a complete insured-establishment census is needed.
8. **五角场街道:** Building-level function can distinguish university, office, innovation, and retail clusters from residential blocks. Official innovation anchors and station flows are useful validation; neither measures employment.
9. **仙霞新村街道:** Office corridors and residential compounds coexist. CMAB improves spatial detail but not workplace intensity. Mobile work population or insured-establishment points would be materially better.
10. **宝山路街道:** The control is small and 86.9% inside. Fine building data can test the remaining disagreement, but a workplace grid is required for a strong independent split.
11. **陆家嘴街道:** The official yearbook reports 228 office buildings, 16.0 million m² of office floor area, and 81.9% average occupancy for the broader Lujiazui Finance and Trade Zone in 2023. That strongly validates an employment center, but 97.28% of the street support is already inside, capping marginal benefit.
12. **新泾镇:** A mobile grid could verify whether the 3.34% reached edge contains a workplace cluster, but the entire three-model leverage is only 0.019 points. Acquire only as part of a broader contract.
13. **外滩街道:** 99.30% of support is inside and the spread is 0.006 points. The official control total already determines the result to practical precision.
14. **北外滩街道:** 99.74% of support is inside and the spread is 0.003 points. Additional allocation data has no practical headline value.

## Feasibility and cost ranking

This ordering ranks acquisition practicality, not uncertainty impact. The best pilot combines high impact with a low/medium acquisition burden: 广中路, 徐家汇, 天目西路, and 五角场. The Pudong zones rank lower on feasibility because better proxy cells alone do not solve their accounting-support ambiguity.

| Feasibility rank | Control | Cost / constraint |
|---:|---|---|
| 1 | 徐家汇街道 | Low-medium: compact ordinary control; open building data and multiple metro anchors |
| 2 | 天目西路街道 | Low-medium: compact ordinary control; open building data and rail/metro anchors |
| 3 | 五角场街道 | Low-medium: official commercial/innovation anchors plus metro |
| 4 | 广中路街道 | Low-medium: compact ordinary control and a very large current disagreement |
| 5 | 陆家嘴街道 | Low-medium acquisition, but low leverage because almost fully inside |
| 6 | 宝山路街道 | Medium: mixed land use; building and station proxies remain indirect |
| 7 | 仙霞新村街道 | Medium: office/residential mixture; mobile work population preferable |
| 8 | 新泾镇 | Medium: mixed town and only a small reached edge |
| 9 | 外滩街道 | Easy but not worth doing; negligible possible reduction |
| 10 | 北外滩街道 | Easy but not worth doing; negligible possible reduction |
| 11 | 金桥经济技术开发区 | High: negotiated workplace data plus zone-membership/support resolution |
| 12 | 张江高科技园区 | High: negotiated workplace data plus zone-membership/support resolution |
| 13 | 三林镇 | High: mobile grid or insured-establishment census required |
| 14 | 周浦镇 | High: mobile grid or insured-establishment census required |

If a commercial establishment route is evaluated, the Qichacha API page lists **6 RMB per query** and returns industry, address, branches, and insured count. A 20,000-record pilot would therefore be about **120,000 RMB at the listed per-query rate**, before enumeration, geocoding, licensing, and engineering; an actual bulk quote could differ. A mobile-workplace quote is preferable because it directly supplies a spatial work-population surface and avoids treating registered office addresses as workplaces.

## Aggregate uncertainty-reduction scenarios

### Method

The exact current fine-control model totals are:

- uniform: 3,501,236;
- JRC building volume: 3,622,356;
- calibrated PPML: 3,558,484.

Adding the same central residual amount to all three models does not change their range. The exact aggregate range is therefore 121,120 workers, or **0.924591 Shanghai percentage points**.

For a selected control (i), let its current three-model vector be (v_i), and let (\bar v_i) be its three-model mean. The scenario replaces it with:

\[
v_i' = \bar v_i + (1-s)(v_i-\bar v_i)
\]

where (s=0.30) is an open building/context scenario, (s=0.70) is a contracted workplace-data scenario, and (s=1.00) is an oracle with a perfectly known inside/outside share. These are declared feasibility assumptions, not observed error rates, probabilities, or confidence intervals. No replacement is applied to the published employment outputs.

### Results

| Portfolio | Selected-control additive spread | Open evidence: reduction / remaining range | Contracted workplace evidence: reduction / remaining range | Perfect-data ceiling: reduction / remaining range |
|---|---:|---:|---:|---:|
| Top 5 | 0.828 pp | 0.098 / 0.827 pp | 0.228 / 0.697 pp | 0.325 / 0.599 pp |
| Top 10 | 1.250 pp | 0.137 / 0.788 pp | 0.319 / 0.606 pp | 0.455 / 0.470 pp |
| Top 20 | 1.747 pp | 0.220 / 0.704 pp | 0.514 / 0.411 pp | 0.734 / 0.191 pp |

The top 5 are 金桥经济技术开发区, 广中路街道, 三林镇, 张江高科技园区, and 徐家汇街道. The top 10 add 天目西路街道, 周浦镇, 五角场街道, 仙霞新村街道, and 宝山路街道. The top 20 add 共和新路街道, 四平路街道, 宜川路街道, 上钢新村街道, 斜土路街道, 北蔡镇, 天山路街道, 大桥街道, 张江镇, and 五里桥街道. Those additional ten were not source-audited individually in this focused report; their scenario uses the same generic source-effectiveness assumption.

The “additive spread” exceeds the aggregate range because it ignores direction and model covariance. The scenario recomputes the three aggregate totals after shrinking selected-control deviations and is therefore the relevant estimate of headline-range reduction.

### Practical interpretation

- **Top 5:** worth a proof-of-concept, but even ideal information cannot collapse the range below about 0.60 pp because other controls still disagree. A contracted workplace grid would realistically remove about 0.23 pp.
- **Top 10:** the minimum sensible acquisition package if the goal is a visibly narrower headline range. A strong contracted dataset could reduce the range by about 0.32 pp, leaving about 0.61 pp.
- **Top 20:** the first portfolio capable of roughly halving the exact current range under the 70% scenario, leaving about 0.41 pp. This would require a wider contract and a second source-audit pass for the ten additional controls.
- **Open-only route:** CMAB is scientifically useful for diagnosing whether JRC flattens or over-concentrates particular clusters, especially 广中路, 徐家汇, 天目西路, 五角场, 金桥, and 张江. It is not strong enough by itself to claim a large reduction in employment-allocation uncertainty.

## Acquisition specification if refinement is approved later

No acquisition or allocation is performed in this report. A defensible later procurement should require:

1. a stable 2023 reference period, preferably multiple ordinary weekdays outside holidays and disruption periods;
2. work-population—not generic daytime footfall—at 100 m or finer grid grain, or exact arbitrary-polygon sums for both the reached and unreached portions of every selected control;
3. provider documentation of device coverage, home/work inference, extrapolation, deduplication, minimum-cell suppression, and historical revisions;
4. permission to retain a frozen extract, request parameters, source version/date, checksums, and derived control shares for reproducibility;
5. explicit prohibition on replacing official census totals: the acquired data may only determine within-control fractions;
6. a separate Jinqiao/Zhangjiang request to the relevant zone/statistics authority for a 2023 establishment-membership roster or the actual census accounting support. A same-name planning polygon is not sufficient;
7. metro station flows used only as independent temporal validation; and
8. pre-registered diagnostics comparing mobile, insured-establishment, CMAB, JRC, and uniform shares within the selected controls before any result is reconsidered.

## Limitations

- Public-source absence is an evidence finding as of the review date, not proof that unpublished administrative data do not exist.
- CMAB and mobile/work-population products have different temporal and statistical universes from the 2023 legal-entity census; normalization preserves totals but does not remove proxy bias.
- Registered addresses and social-insurance enrollment can be displaced from actual workplaces, especially for headquarters, branches, construction, and centrally administered employers.
- Pudong functional-zone boundary uncertainty is separate from within-support workplace allocation. Better workplace cells cannot identify the correct census-zone support without zone membership or an authoritative accounting boundary.
- The portfolio percentages quantify how the existing three-model range would contract under stated assumptions. They do not revise the 3.69 million numerator and are not confidence intervals.

## Recommendation

**COMMERCIAL/MOBILE WORKPLACE DATA REQUIRED**
