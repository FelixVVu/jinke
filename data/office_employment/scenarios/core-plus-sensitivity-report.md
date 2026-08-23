# Jinke district Core+ composition sensitivity

**Scope:** district controls only; no 100 m grid, spatial allocation, reach intersection, or reach percentage.

## Validated construction

- Core remains an immutable official hard control.
- Every scenario preserves 743,125 selected division-72 workers and total city Core+ employment of 3,220,710.
- Base exactly reproduces the current maximum-entropy district Core+ table.
- Low and High are targeted composition stresses, not estimates or confidence bounds.
- The transfer is 12,983 workers, equal to 20% of Baoshan's Base selected-72 allocation, preserved subgroup by subgroup.
- The other 11 districts remain exactly at Base.
- Selected-72 shares stay within official division-72 margins: 36.909%-46.828% in Low, 39.021%-39.024% in Base after integer reconciliation, and 31.218%-41.137% in High.

## Scenario definitions

- **Low office intensity:** lower selected-72 concentration in Huangpu, Jing'an, Changning and Putuo; the conserved amount moves to Baoshan.
- **Base:** current 39.023% maximum-entropy selected-72 share.
- **High office intensity:** higher selected-72 concentration in those four central districts; the same conserved amount moves out of Baoshan.

## District scenario table

| district | core office employment hard control | low office intensity core plus employment | base core plus employment | high office intensity core plus employment | low office intensity difference from base employment | high office intensity difference from base employment |
|---|---|---|---|---|---|---|
| 黄浦区 | 158769 | 229335 | 233376 | 237417 | -4041 | 4041 |
| 徐汇区 | 258823 | 318079 | 318079 | 318079 | 0 | 0 |
| 长宁区 | 105111 | 144309 | 146553 | 148797 | -2244 | 2244 |
| 静安区 | 194334 | 278803 | 283639 | 288475 | -4836 | 4836 |
| 普陀区 | 100906 | 133421 | 135283 | 137145 | -1862 | 1862 |
| 虹口区 | 71077 | 92225 | 92225 | 92225 | 0 | 0 |
| 杨浦区 | 146985 | 168462 | 168462 | 168462 | 0 | 0 |
| 闵行区 | 229092 | 301661 | 301661 | 301661 | 0 | 0 |
| 宝山区 | 73770 | 151667 | 138684 | 125701 | 12983 | -12983 |
| 嘉定区 | 112899 | 150079 | 150079 | 150079 | 0 | 0 |
| 浦东新区 | 816970 | 958767 | 958767 | 958767 | 0 | 0 |
| 金山区 | 20472 | 32854 | 32854 | 32854 | 0 | 0 |
| 松江区 | 64930 | 91522 | 91522 | 91522 | 0 | 0 |
| 青浦区 | 72568 | 89760 | 89760 | 89760 | 0 | 0 |
| 奉贤区 | 40638 | 62083 | 62083 | 62083 | 0 | 0 |
| 崇明区 | 10241 | 17683 | 17683 | 17683 | 0 | 0 |

## Ranking changes

Positive rank change means a district moves down relative to Base; negative means it moves up.

| scenario label | district | employment rank | employment rank change from base | intensity rank | intensity rank change from base |
|---|---|---|---|---|---|
| Low office intensity | 长宁区 | 9 | 1 | 7 | 0 |
| Low office intensity | 宝山区 | 7 | -2 | 10 | 0 |
| Low office intensity | 嘉定区 | 8 | 1 | 11 | 0 |
| High office intensity | 黄浦区 | 5 | 0 | 1 | -2 |
| High office intensity | 普陀区 | 9 | -1 | 6 | 0 |
| High office intensity | 杨浦区 | 6 | 0 | 3 | 1 |
| High office intensity | 宝山区 | 10 | 1 | 11 | 1 |
| High office intensity | 嘉定区 | 7 | 0 | 10 | -1 |
| High office intensity | 浦东新区 | 1 | 0 | 2 | 1 |

## Validation assessment

**READY FOR FRAMEWORK REVIEW WITH CAVEATS.** The accounting constraints and targeted sensitivity behave as designed. The 20% transfer is a transparent stress amplitude, not an empirically estimated district composition interval. Core is ready as a hard control. Core+ must continue to carry scenario labels when later spatial allocation is implemented.

**STOP BEFORE 100 M GRID OR REACH CALCULATION**
