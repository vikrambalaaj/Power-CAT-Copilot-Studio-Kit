# Demo and dummy data cleanup — 7 September 2026

**Current verdict: NOT deleted from the working application or deployed environment.** Review found embedded examples and simulation branches. A source cleanup script has been created and exercised on temporary copies, but not applied to the working application, deployed images or stored business records. Do not certify “all demo data deleted” from this deliverable.

## Deliverables

- [Cleanup script](/Users/vikrambala/copilotstudio/deploy/cleanup/remove_runtime_demo_data.py)
- [Exact preview manifest](/Users/vikrambala/copilotstudio/docs/demo-data-cleanup-20260907/cleanup-plan.json): 45 targeted transformations across five source files, with before/after hashes. It contains no credential values or copied sample records.
- [Offline checks](/Users/vikrambala/copilotstudio/deploy/cleanup/test_remove_runtime_demo_data.py)
- [Executed test results](/Users/vikrambala/copilotstudio/docs/demo-data-cleanup-20260907/script-tests.log)

## What the script removes

| Production location | Removed behavior/data | Behavior after cleanup |
|---|---|---|
| Productivity `m365_client.py` | Embedded sample people, mail, meetings, Teams messages and tasks; fixture-seeding function; mock-mode switch; simulated email/meeting/task/message results; fixed pending approvals | Existing live Graph branches remain. Missing credentials or unimplemented live reads raise SOURCE_UNAVAILABLE. No simulated success receipts. Name-only recipients remain unresolved until real directory lookup is available. |
| SAC `client.py` | Three embedded KPI/story/model responses, fixed corporate figures and synthetic summaries | Missing authentication raises SOURCE_UNAVAILABLE; existing live requests remain. Cached data explicitly marked demo/simulated is rejected. |
| SAC `settings.py` | Demo-mode configuration field | Application no longer selects demo response branches. Old deployment variables have no enabling effect but should be removed in the release cleanup. |
| Facilitator `tools.py` | Fixture-seeding function and fixture collections; fixed workforce/AR/margin brief; local collections presented as fetched calendar/history; constructed Loop links presented as provider saves | These unfinished integrations return SOURCE_UNAVAILABLE with no invented facts or destination links. This deliberately exposes incomplete capability implementation. |
| SuccessFactors `policy_admin.py` | Embedded employee example used by the policy preview | Preview reports that authorized input is required. No embedded employee is returned. |

These source files explain where the data originated and why it was not evidence of a real source fetch. The script changes application code; it does not infer which historical records came from those paths.

## How to use

Run from the repository root to regenerate a preview against the latest source:

```sh
python3 deploy/cleanup/remove_runtime_demo_data.py \
  --plan docs/demo-data-cleanup-20260907/cleanup-plan.json
```

Inspect the manifest and capability impacts. Apply exactly that source snapshot:

```sh
python3 deploy/cleanup/remove_runtime_demo_data.py \
  --plan docs/demo-data-cleanup-20260907/cleanup-plan.json \
  --apply
```

Run the offline cleanup checks:

```sh
python3 deploy/cleanup/test_remove_runtime_demo_data.py
```

The apply operation:

1. Restricts edits to five explicit files within the chosen repository root; rejects symlink targets.
2. Parses/transforms/compiles every proposed Python source before writing.
3. Requires the preview root, source hashes, output hashes and transformation list to match exactly.
4. Rechecks a source hash immediately before replacing each file and records application time and hashes in `cleanup-plan.applied.json`.
5. Performs no provider call, email send, deployment, database deletion or keyword-based file purge.

File replacement is atomic per file, not a transaction across all five. Run on a stable checkout without another developer editing the targets. If interrupted after some replacements, inspect the applied files and generate a new preview for the remaining state. Source formatting is normalized by Python's AST serializer; review the resulting diff before release. Existing version-control history is not erased.

## Verification performed

Four test groups passed, including subcases for:

- Preview leaves files byte-for-byte unchanged; changed source is rejected before application.
- Apply succeeds on isolated copies and writes its application record.
- Cleaned output compiles and transformations are idempotent.
- Fourteen Microsoft 365 read/write/approval helper cases reject missing live services; simulated receipt generation is rejected.
- Three SAC operations reject missing authentication and embedded response payloads are absent.
- Facilitator briefing/calendar/Loop paths return unavailable rather than fixed facts or constructed links.
- Embedded SuccessFactors employee preview data is absent.

No live connection or business write was used. These are focused cleanup checks, not full application regression or deployment acceptance.

## Required follow-through before an “all clean” confirmation

1. **Apply and regression-test the source changes.** Existing tests currently import fixture seed helpers from production modules or enable SAC demo mode. Move their synthetic fixtures into test-only modules and mock provider boundaries there; update assertions to verify production failures rather than simulated success. Do not count the earlier 187/188 test result as validation of this proposed cleanup.
2. **Separate test fixtures from runtime packages.** Automated tests still need controlled input. Exclude test directories, caches, old archives and development artifacts from build contexts/runtime images. This script intentionally does not destroy historical review evidence or test assets.
3. **Rebuild every affected artifact.** Existing ZIP packages and ACR images can retain the old code. Build clean images, inspect their contents, deploy their exact digests, and retire old revisions from traffic. A source edit cannot remove data from an already-built image.
4. **Inventory stored records before deleting them.** No current record-level inventory was collected for Dataverse, Azure storage, Loop, mail or tasks. Deletion requires the specific environment, table/container, record IDs and evidence that each record is synthetic. Do not delete based on a name containing “test”, a familiar amount, or a sample-looking date. Do not purge audit history wholesale.
5. **Confirm runtime behavior.** Missing credentials/source outage must produce unavailable/error, never fake records or successful simulated actions. Verify all outputs trace to real authorized sources.
6. **Complete Azure-only storage separately.** Local outbox/home-directory fallbacks, audit buffering, distributed idempotency and storage mounts are separate findings in the full review. This demo-data script does not claim to resolve them.

The runtime scan also found test-only failure switches (`simulate_down`) and provenance fields such as `isDemoData=False` / `cre2f_demodata=False`. Those are not embedded business data. Configuration defaults, legitimate data samples selected from real records, “demographics” code, and explanatory examples in historical documents must not be deleted by a broad keyword search.

No evidence currently supports saying that all dummy data has been removed from the codebase, the deployed Azure environment, or stored records. The exact source cleanup is ready; deployed and persisted data require the follow-through above.
