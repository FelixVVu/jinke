# Pilot 3: evidence-assisted second pass

This is a review-only suggestion workflow. It does not accept candidates, modify
canonical company names, infer industries, merge identities, move coordinates or
upgrade mapped-office confidence to verified physical-office confidence.

## Actual inputs and result — 2026-10-15

Used the exact attachments `company-access-amap-pilot-3-38561610093(1).zip` and
`pilot3-second-pass-triage(2).json`. The latter is preliminary triage, not a human
decision file. Its bundle ID, all 276 provider IDs, names and addresses match the
snapshot-derived review bundle. All 276 decisions remain pending.

Snapshot SHA: `2aa095a4d4238959840afe54f7da9c4b233fb55d789583bb7e24e5cf6eef9bf7`.
Incoming bundle ID: `9fae0e2a67367f5d88c3906ee1a8422f9d4e29672ba26048974b6364a78bcf9a`.

| Second-pass group | Records | Review workload |
| --- | ---: | --- |
| 可信候选 | 34 | Spot-check up to 8, then explicitly confirm remaining pending group |
| 建议排除 | 36 | Spot-check obvious site/store/property exclusions, then confirm |
| 重点核实 | 206 | Prioritize 9 identity/address/duplicate exceptions; other ambiguous records can remain held in bulk |
| 历史锁定 | 166 | Unchanged decisions, including the existing 104 approved offices |

Of 34 credible candidates, 7 have public office-address corroboration and 27 have
consistent mapped company/address/floor fields only. Targeted primary-source
checks cover 15 candidates in total, including conflicting and identity-only
evidence. This does not claim 276 external checks or a verified inventory.

The old suggestion rule accepted 242 rows merely from company POI type and an
address containing a number. Version 2 separates intersections/directions from
specific addresses, construction sites, retail/service locations, property desks,
industrial activity, vague identities, and ground/basement locations. A numbered
road alone is not enough. Parenthesized metro directions do not invalidate an
otherwise precise office address. A reliable public campus address does not need
an invented floor number. Matching names at different provider IDs are held, never
automatically merged; sharing a building alone is not a duplicate.

## Evidence and immutable data

`web/src/company-access/review-triage.js` is shared between offline preparation
and the browser. Rules use deterministic reason codes; there are no confidence
probabilities, fuzzy identities or company-name industry assignments.

The evidence sidecar binds each annotation to its exact provider ID, company name
and address. It records assessment, scope (company identity / site / building /
floor), summary, limitations, HTTPS source URL, title and check date. Registration
or company existence alone does not become public office-address corroboration.
Address/identity conflicts take precedence over positive evidence. Public sources
are displayed as evidence for a suggestion, not as human review decisions.

The attached preliminary flags remain visible for audit. They are not accepted
as authoritative classifications. The original v1 suggestion remains in the
immutable bundle for audit and hash/import compatibility; the Console exclusively
uses v2 for displayed groups, filters and bulk guidance. Existing session IDs and
the trusted offline importer are unchanged.

All real source/evidence/triage files stay under ignored `offline-output/`.
Neither real company data nor review decisions are committed to GitHub. The
explicit review package includes sanitized pending rows, compact evidence and
coverage metadata; it does not include raw provider snapshots or acquisition keys.

## Reproduce and package

```sh
node scripts/company-access/amap/second-pass.mjs \
  APPROVED_BASE SNAPSHOT_JSON ATTACHED_TRIAGE_JSON PUBLIC_EVIDENCE_JSON \
  offline-output/company-access/FRESH_TRIAGE_OUTPUT

node scripts/company-access/build-review.mjs \
  APPROVED_BASE offline-output/company-access/FRESH_TRIAGE_OUTPUT
```

The first command refuses mismatched attachments, incomplete coverage, duplicate
or unknown annotation IDs, changed names/addresses, and non-pending seed decisions.
It writes `pending-review-bundle.json`, `second-pass.json`, and
`pilot3-coverage.geojson` into a fresh directory. The second command checks the
pack against the trusted historical bundle before including it in `dist-review`.
Normal builds do not contain these artifacts or the Console page.

The actual review deployment retains the historical pr19 hostname and existing
access policy. Only the approved 104 offices are loaded in the Jinke map. Pending
rows appear only in the Review Console.

## User workflow

1. Open `/company-review.html`. This Pilot 3 batch and its evidence load directly;
   no acquisition ZIP or CSV needs to be imported by the user. Fill in 审核人.
2. Click 可信候选 → 抽查本组（最多 8 条）. Inspect the source scope and map for the
   samples. Correct any exceptions individually. If satisfied, click
   批量确认接受, read the whole-group count, tick the acknowledgement and click
   确认这些决定. The confirmation applies to all remaining pending rows in this
   group, not only the sample. Previously decided records are skipped.
3. Click 建议排除 → 抽查本组（最多 8 条） → 批量确认排除, with the same explicit
   confirmation. A disagreeing sample can instead be marked 待核实 individually.
4. Click 重点核实 → 只看关键例外（9）. Resolve only those you can substantiate;
   use 整组标记待核实 to keep unresolved records out of the canonical inventory.
   This does not require inspecting the remaining ambiguous rows individually.
5. Click 导出决定与历史. Return that single JSON for the existing trusted
   `pilot3-workflow.mjs import` and review-build process. No manual CSV editing.

Group confirmation requires a named human and an unchecked-by-default
acknowledgement. It records per-record rule/reason, public source links, the human
name, timestamp and previous state. Existing notes are retained. Suggestions,
sample views and opening the page never write a decision. History remains locked;
previous local drafts are restored only after full session validation. The map
does not automatically publish after a decision or export.

Search automatically spans groups/history and retains the shared reviewed
SAP/NVIDIA alias index. Keyboard shortcuts are suspended during confirmation.

## Verification

123 JavaScript tests pass, including 10 new second-pass tests: known false-positive
patterns, proper metro hints, evidence scopes/conflicts, stale annotation binding,
deterministic sampling, explicit bulk decisions, notes/history preservation and
synthetic confirmed-session import through unchanged canonical validation. Existing
point-click, bilingual search, basemap lifecycle, acquisition budget and 156-file
economic guards pass. Core+ remains exactly 1,212,066.713237 and 37.6335253%.

Real packaging verification confirms 276 pending + 166 locked rows, four approved
frontend files byte-identical, and an in-memory pending-only import yielding zero
new accepts while preserving every one of the 104 features and historical ledger
entries. No real approval was made for testing. Python/model files are unchanged;
the Python suite was not rerun because pytest is unavailable. Live browser visual
QA is unavailable in this managed environment; no screenshot verification claimed.
