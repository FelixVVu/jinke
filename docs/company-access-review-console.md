# Review Console (PR #20 only)

The existing review Site exposes `company-review.html`; normal builds contain no
console page, candidate bundle, or approved pilot data. No provider calls, secrets,
new acquisition, deployment trigger, or production integration is added.

## Point click and local alias search

The existing visible `company-access-circles` layer resolves `properties.id` against
the currently visible approved inventory. MapLibre tile IDs are not assumed to
preserve string GeoJSON IDs. Selection updates the MapLibre ring and the drawer;
one delegated handler per layer survives style replacement. No extra hit layer or
DOM marker is used. Cluster leaves use the same canonical-ID lookup.

`web/src/company-access/aliases.js` contains exact office-ID/name-bound, reviewable
search metadata. The user explicitly supplied SAP / 思爱普 and NVIDIA / 英伟达.
No other English legal names or aliases are inferred. The metadata supports
reviewed English names, brands, acronyms and aliases without changing canonical
names. “Search identified offices” searches approved offices in the selected reach,
not general location search. Cluster search remains scoped to its cluster.

## Human workflow and persistence

The supplied Pilot 1 + 2 archive contains **166 prior decisions** (104 accept,
45 needs_review, 17 reject), all preserved and locked, including notes/reviewer/date.
There are **zero new pending candidates** in this archive. Default “New candidates
only” is correctly empty; use “All / locked history” to inspect prior decisions.
No synthetic candidates are added to the review Site.

For a new prepared batch: open its `review-bundle.json`, enter a reviewer name,
filter by suggestion/reason/status or search, select on map or list, and explicitly
Accept / Reject / Needs review. Bulk actions apply only to selected visible editable
rows; changing filters clears hidden selections. J/K navigate, Space selects,
A/R/N decide outside text fields. Notes can be saved independently. Every decision
and note edit has a before/after history with reviewer and time. Prior decisions
cannot be reopened silently. A separate explicitly authorized amendment workflow
would be required to change them.

Browser storage is **temporary draft recovery only**, not the authoritative ledger.
Export **decisions & history** for durable handoff and restore that JSON to continue
on another browser. CSVs are optional review interchange; the session JSON preserves
the full edit history. Nothing is uploaded automatically or published by the console.
The durable source of truth remains the protected offline snapshot, reviewed import
and prior decision ledger, not browser state. Do not clear browser data before export.
This is a file-backed review workflow, not a multi-user synchronized review database.

## Deterministic suggestions (v1)

Precedence: duplicate/conflict or changed prior source → needs_review; obvious
non-office place/provider category → suggested reject; stale/uncertain location,
vague address, manufacturing ambiguity or unclear company identity → needs_review;
company-category POI with a specific address and no flagged ambiguity → suggested
accept. Exact normalized name + address matches against prior approved inventory
are flagged for review, never merged or accepted automatically. These heuristics
are triage only, not a coverage or confidence probability. They do not establish
physical occupancy. Unknown industry remains unknown.

Accept means **reviewed mapped office**. There is no console confidence-upgrade
control. **Verified physical office** still requires strong evidence through the
existing Phase 2 validation methodology.

## Future batch commands (offline, no acquisition)

Use the immutable prior approved archive as `BASE`, and a key-free provider snapshot
as `SNAPSHOT`. Paths below are illustrative; outputs must be fresh directories.

```sh
node scripts/company-access/amap/console.mjs prepare SNAPSHOT BASE/audit/human-review.json offline-output/company-access/new-review
# Open new-review/review-bundle.json in the console. Export a session JSON.
node scripts/company-access/amap/console.mjs validate-export SNAPSHOT BASE/audit/human-review.json offline-output/company-access/validated-review SESSION.json
node scripts/company-access/amap/files.mjs import-review --snapshot SNAPSHOT --csv offline-output/company-access/validated-review/amap-office-review.csv --output offline-output/company-access/new-import --reviewer 'Reviewer name' --reviewed-at '2026-10-02T12:00:00Z'
node scripts/company-access/amap/merge-reviewed.mjs BASE offline-output/company-access/new-import offline-output/company-access/merged-import
```

`validate-export` reconstructs the bundle from trusted snapshot + prior ledger and
adjacent prior frontend offices, verifies bundle identity and every decision history,
and invokes unchanged canonical import validation before exporting. It also saves
the session with full history; retain it alongside the subsequent imported audit.
The final merge protects baseline offices/decisions and reports canonical conflicts.
Only explicit accepts enter the canonical pipeline, which can still reject/quarantine
them. Suggestions never become review decisions. Real bundles/exports stay ignored
under `offline-output/`, never in GitHub.

Review-only packaging requires the original Pilot 1/2 snapshots under `source-imports`
in the combined approved archive. All four frontend artifacts are copied unchanged;
office employment and general location search are untouched. Remove/disable the
review page/link/bundle packaging before any production enablement; normal build
already omits the page and data.
