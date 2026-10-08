# Tests

Run them with the commands in [AGENTS.md](../AGENTS.md#gates-run-before-every-commit-that-changes-code). Every test uses the fake model provider unless it is marked `eval` or `smoke_live`.

| Folder | What it covers |
| :--- | :--- |
| `unit/` | Pure functions: chunking, quote verification, retrieval scoring, templates, settings, provider requests and retries |
| `integration/` | The app through its HTTP API with a temporary database: sources, answers, follow-ups, Studio, sessions, deletion, limits |
| `governance/` | The governed-documents layer: the document-control split, status rules, the Resolution Card and its export |
| `models/` | The model picker layer |
| `security/` | CSRF and Origin checks, upload safety, untrusted text, sharp edges, secrets in the repository |
| `api/` | The access gate, notebooks, sources, limits, headers and the Markdown export through their routes |
| `e2e/` | Real browser (Playwright and Chromium): layout, journeys, citations, contrast |
| `live/` | Two smoke journeys against a deployed site; run only on request |

## Where to start

- The core journey in a browser: `e2e/test_journey_a.py`.
- Answers that cannot be backed by a word-for-word quote are dropped: `unit/test_verify.py` and `integration/test_answers.py`.
- One visitor never sees another's data: `integration/test_access_and_notebooks.py` (`test_tc_acc_005_data_is_scoped_to_the_session`).

## Files named after review rounds

Five files hold regression tests written while fixing findings from independent reviews: `integration/test_codex_pr1.py`, `integration/test_full_audit_core.py`, `integration/test_recheck2_core.py`, `integration/test_audit_regressions.py` and `governance/test_full_audit_fixes.py`. Each test is named after the behaviour it checks.
