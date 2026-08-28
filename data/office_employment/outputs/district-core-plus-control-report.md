# Jinke district Core+ employment controls

**Construction date:** 2026-08-23

**Scope:** district controls only; no 100 m grid, within-district spatial allocation, reach intersection, or reach percentage

## Accounting result

| Definition | Shanghai employment | Share of 13,099,795 | Status |
|---|---:|---:|---|
| Core: I + J + M | 2,477,585 | 18.913% | Exact official district controls |
| Core+ excluding 721: Core + 723 + 724 + 725 | 2,992,422 | 22.843% | City subgroup total official; district subgroup composition modelled |
| Core+ including 721: Core + 721 + 723 + 724 + 725 | 3,220,710 | 24.586% | City subgroup total official; district subgroup composition modelled |
| Broad professional/institutional sensitivity | 6,374,547 | 48.661% | Exact official district controls |

Including group 721 adds **228,288 workers**, or **1.743 Shanghai percentage points**, relative to the 721-excluded Core+ sensitivity.

## Construction method

Official Table 1-9 fixes each district's division-72 employment. Official Table 1-3 fixes the Shanghai totals for groups 721, 723, 724, and 725. Because the census does not publish district × three-digit-group employment, each subgroup uses the maximum-entropy independence allocation:

`district subgroup = official district 72 × official Shanghai subgroup / official Shanghai 72`

Each subgroup is then integerized with largest-remainder reconciliation so its 16 district estimates sum exactly to its official Shanghai total. Core and full division 72 are never altered. This is a district composition bridge only and uses no geometry.

## District Core/Core+/Broad controls

| District | Exact Core | Exact full 72 | Core+ including 721 | Core+ excluding 721 | Exact Broad |
|---|---:|---:|---:|---:|---:|
| Huangpu | 158,769 | 191,187 | 233,376 | 210,457 | 478,374 |
| Xuhui | 258,823 | 151,850 | 318,079 | 299,875 | 571,893 |
| Changning | 105,111 | 106,199 | 146,553 | 133,822 | 299,213 |
| Jing'an | 194,334 | 228,852 | 283,639 | 256,205 | 604,189 |
| Putuo | 100,906 | 88,096 | 135,283 | 124,722 | 288,085 |
| Hongkou | 71,077 | 54,193 | 92,225 | 85,728 | 226,952 |
| Yangpu | 146,985 | 55,036 | 168,462 | 161,864 | 322,470 |
| Minhang | 229,092 | 185,963 | 301,661 | 279,368 | 605,180 |
| Baoshan | 73,770 | 166,347 | 138,684 | 118,743 | 353,767 |
| Jiading | 112,899 | 95,276 | 150,079 | 138,657 | 307,556 |
| Pudong | 816,970 | 363,367 | 958,767 | 915,207 | 1,534,797 |
| Jinshan | 20,472 | 31,730 | 32,854 | 29,050 | 103,875 |
| Songjiang | 64,930 | 68,145 | 91,522 | 83,353 | 248,404 |
| Qingpu | 72,568 | 44,055 | 89,760 | 84,479 | 198,056 |
| Fengxian | 40,638 | 54,954 | 62,083 | 55,495 | 163,266 |
| Chongming | 10,241 | 19,072 | 17,683 | 15,397 | 68,470 |
| **Shanghai** | **2,477,585** | **1,904,322** | **3,220,710** | **2,992,422** | **6,374,547** |

## Audit flags

- `core_and_full_72_are_official = true`
- `core_plus_72_is_modelled = true`
- `no_spatial_allocation_performed = true`
- `grid_created = false`
- `reach_percentage_calculated = false`

The long-form subgroup allocation is retained separately so every estimated district 721/723/724/725 value can be audited. The Core+ table does not alter the existing all-industry employment benchmark or any web output.

**STOP FOR REVIEW**
