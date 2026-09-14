# AATC review evidence pack

**Outcome: NOT READY.** Read [REVIEW.md](REVIEW.md) first. This is local engineering evidence, not live acceptance or security certification.

- `REVIEW.md`: findings, fixes, scope, test results and closure requirements.
- `control-review-matrix.csv`: all 58 original security control IDs and requirements, with open findings and acceptance evidence.
- `test-summary.json`: final suite counts; suite XML and logs contain underlying results.
- `security-probe-results-before.json`: initial reproduced issues before the federation fix.
- `security-probe-results.json`: final probes, including confirmed remaining audit/approval bypasses.
- `security_probes.py`: reproducible offline probes with synthetic credentials and blocked outbound calls.
- `source-snapshot.json`, `source-changes-during-review.json`, `final-source-manifest.json`: initial/final hashes and drift.
- `auth-configuration-summary.json`, `configuration-name-inventory.json`: local configuration names/presence; no secret values.
- `azure-read-verification.json`: live inventory blocked by Azure read authorization.
- `matrix-test-reference-check.json`: verification of the old matrix's named test references.
- `python-syntax-review.json`: Python syntax results.
- `review-runtime-requirements.txt`, `offline_test_runner.py`: review runtime and isolation harness.
- `artifact-sha256.json`: evidence file integrity hashes.

Test doubles are isolated testing tools, not mock business data offered as live evidence. No provider credentials or bearer assertions are included.
