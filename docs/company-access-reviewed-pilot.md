# Phase 3C — approved Pilot 1 review

Imported the user's exact `amap-office-review_proposed(1).csv` against the exact
snapshot inside `company-access-amap-pilot-1-35691688121(1).zip`, using the existing
import-review command. Review notes and decisions are unchanged. The importer
records the import timestamp, not a claim about when the user reviewed each row.

| Result | Count |
| --- | ---: |
| Human accepts | 28 |
| Needs review, excluded | 9 |
| Reject, excluded | 8 |
| Canonical offices | 28 |
| Collapsed duplicates | 0 |
| Canonical conflicts / validation exclusions | 0 |
| 10 / 20 / 30 / 40 / 50 minutes | 0 / 7 / 28 / 28 / 28 |
| Known hubs | 0 |
| Pudong / Huangpu | 22 / 6 |
| Reviewed mapped office confidence (`building`) | 28 |
| Licensed POI source | 28 |

Unknown buildings/hubs/industries remain unknown. Mapped office confidence is
not verified physical-office confidence, an employment estimate, or a claim of
inventory completeness. Source-dependent coverage remains disclosed.

## Packaging and UI

Run `npm run company-access:review-build -- <approved-import-directory>`.
This validates all seven canonical/audit artifacts and checks that canonical
source IDs have human accept decisions before creating `dist-review`. Only the
four compact frontend files are copied into the review website. Generated real
records, CSVs, caches and review builds remain gitignored. The normal build has
no review marker or company data and never requests this pilot inventory.

The explicit review build adds a Pilot 1 HTML marker. The browser reconciles
canonical offices, hubs and exact reach summaries before enabling the toggle.
Company statistics and the office/cluster detail cards use text nodes, never
provider HTML. They stay inside Jinke's existing desktop panel/mobile sheet.

MapLibre GeoJSON clustering uses a 48-pixel radius and max cluster zoom 14.
The source is rebuilt from exact selected-reach membership BEFORE clustering;
`All` uses 50 minutes. Rose circles with white numbers show cluster counts;
zooming in separates individual points. Cluster clicks list the selected
source's offices. Office clicks show name, address, district, mapped-location
confidence and building/hub only when known. There are no DOM markers.
Named hub labels are supported at medium zoom, but Pilot 1 has no genuine hub
assignments, so none are invented or shown.

Incremental counts are the set difference from the previous cumulative reach,
not a distance approximation. The panel separately shows district mix,
confidence counts and known hubs. Style restoration re-creates sources/layers,
retains reach/toggle state, binds handlers once, and invalidates in-flight
cluster queries when their data/style becomes stale. A glyph URL is provided
for numbered labels on raster basemaps without changing protected map helpers.

## Review hosting and production boundary

Reuse the existing **Jinke PR 19 Review** Site for the PR #20 review, retaining
its existing audience and URL. Its identity is separate from the production
Jinke Site. No new permanent Site, main merge, production Jinke source update,
or production Jinke deployment is part of this task. The old review URL keeps
its historical `pr19` slug; the Site title identifies the current PR #20 review.

The 156-file model/data hash baseline is untouched. Approved Core+ remains
1,212,066.713237 employment and 37.6335253% Shanghai share.

Validation: 85 JavaScript tests, 111 Python tests, and review build passed.
Behavioral tests cover exact pre-cluster filtering, stale queries, All reach,
repeated style replacement, analytics, review-only loading and data tampering.
Browser visual verification was blocked by `ERR_BLOCKED_BY_CLIENT` / URL policy;
no screenshot or browser-verified visual result is claimed.
