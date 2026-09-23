# Phase 3B: manual GitHub Actions Pilot 1

The same existing AMap credential may be mirrored into the repository Actions
secret **JINKE_AMAP_KEY**. This does not require another AMap-issued key and does
not change the production Site's secret or code.

## Implementation

`.github/workflows/company-access-amap-pilot.yml` has only `workflow_dispatch`,
no inputs, no schedule, and no push/PR trigger. Its job runs only for
`FelixVVu/jinke`, `review/company-access-scaffold`, and run attempt 1. Rerunning a
job is refused so an accidental retry cannot repeat the upstream acquisition.
Concurrency is serialized; separately dispatching again would still start a new
run, so dispatch **once**, inspect its result, and do not dispatch repeatedly to
reach a candidate target.

The adapter `scripts/company-access/amap/actions-pilot.mjs` independently checks
that context. It reads only the existing named credential, passes a narrow
binding object to `runCompanyAccessPilot`, and never serializes the environment.
The fixed job checks the committed geometry hash and uses the existing 16-cell,
25-POI page, maximum 3-pages/cell, maximum 24-attempt, 1,100-ms pacing, one-retry,
200-candidate policy without accepting runtime overrides. No new acquisition
implementation or public proxy is introduced.

The workflow runs mocked JavaScript tests and economic guards before the
credential is made available to the acquisition step. Missing configuration
fails before any request. Fixed-name local checkpoints are written atomically
under the ignored offline-output directory. The existing `prepareFiles` function
then creates `offline-output/company-access/pilot-1/` with provider cache,
normalized candidates, pending CSV/JSON review rows and acquisition QA.

## Downloadable artifact

Name: `company-access-amap-pilot-1-<run_id>` (7-day retention).

Only this allowlist is staged for upload; all files are checked for the raw,
JSON-escaped, URL-encoded and Base64 credential before the artifact-ready flag
is set. The artifact contains no checkout, env files, process environment,
credentials, dependencies, frontend data or accepted records.

```
review/amap-office-review.csv
review/amap-office-review.json
normalized/candidates.json
normalized/raw-input.json
audit/pilot-report.json
audit/pilot-report.md
audit/acquisition-exclusions.json
provider-cache/snapshot.json
```

The snapshot already contains every successful provider response and the query
plan, so separate per-page cache files are unnecessary in the download. It is
sufficient for later review import. All generated outputs remain gitignored.
All review decisions are checked to be `pending`. No UI is connected.

The Actions summary shows only numeric counts and a local stop code; the
key-scanned artifact provides district/type breakdowns, duplicates/conflicts,
coordinate/type/reach exclusions, building coverage, request/cache counts and
full QA. Provider failures still produce downloadable safe partial outputs
when preparation completes, while the acquisition step signals failure. Never
interpret partial outputs as complete coverage.

## Dispatch prerequisite and current execution status

GitHub's [manual workflow documentation](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
states that the workflow must exist on the default branch for workflow_dispatch.
The `--ref` option selects the execution branch after that prerequisite is met.
A new branch-only workflow is therefore not a guaranteed runnable deployment.

This change stays on PR #20's review branch. No workflow registration was added
to main. The existing Pages workflow deploys on pushes to main, so blindly
copying this file to main could trigger a production deployment; **do not do
that**. Default-branch registration would require a separately authorized CI
change that also prevents that production deployment. This task does not
authorize changing main or the deployment workflow.

Once safely registered and the same credential is present in repository Actions
secrets, the exact manual command is:

```sh
gh workflow run company-access-amap-pilot.yml \
  --repo FelixVVu/jinke \
  --ref review/company-access-scaffold
```

Or use Actions → Company Access AMap Pilot 1 → Run workflow and explicitly
select `review/company-access-scaffold`. Do not select main or use Re-run jobs.
There are no query, geometry, budget, URL or credential inputs.

After completion, open the run and download its named artifact. The CSV is at
`review/amap-office-review.csv` inside the ZIP. Edit only review_status and
review_notes; the [existing import workflow](company-access-amap-pilot.md)
accepts the downloaded provider-cache/snapshot.json and CSV. Do not auto-accept
rows or copy the artifacts into the normal frontend.

At implementation time the GitHub connector returned HTTP 400, Invalid MCP
request metadata. This prevented remote PR/secret inspection and dispatch.
No real API execution is claimed: **0 new AMap requests, no real snapshot,
no real review CSV, no Actions run URL or downloadable real artifact**.
The user-provided secret's availability could not be verified.

## Code separation and merge considerations

Reusable: acquisition, client, preparation/import, QA, existing regression tests.
Review activation: this workflow and actions-pilot.mjs. Neither is imported by
the Site, copied by the browser build, or invoked by normal UI/production routes.
Remove the temporary workflow and adapter (and their dedicated test/script entry)
before an eventual production merge unless this manual review facility is
explicitly retained. Their branch/event checks must not be loosened casually.
The corrected acquisition stop reason clears a transient failure after a
successful retry; this reusable fix is covered by the existing retry test.

The 156-file regression baseline remains untouched. Core+ stays exactly
**1,212,066.713237 employment** and **37.6335253% Shanghai share**.

Validation: **83 JavaScript tests and 111 Python tests passed**; static build,
workflow YAML parsing and diff checks passed. Automated acquisition tests used
mock responses only. Direct Git push also lacked write authentication, so these
changes were committed locally on the existing review branch; remote PR update
and dispatch remain pending connector recovery and safe workflow registration.
