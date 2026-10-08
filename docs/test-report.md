# Test report

Generated on 2026-10-08 from the release `535a152` with PR #50 (the fixes from the final audits), fake model provider, no key. Two full runs, as in CI:

| Run | Result |
| :--- | :--- |
| Every optional layer off | 530 passed |
| Governance and model picker on | 529 passed, 1 skipped (TC-REV-001 runs only with every layer off, by design) |

The table below is the run with every layer off. Each row is one test case; it passes only if all its tests pass. 88 more tests carry no test-case ID, mostly regression tests written while fixing review findings ([tests/README.md](../tests/README.md) lists where they are). All 88 passed. The stage reports from the build are in [archive/](archive/).

| Requirement | TC | Tests | Result |
| :--- | :--- | ---: | :--- |
| FR-ACC-01 | TC-ACC-001 | 1 | pass |
| FR-ACC-02 | TC-ACC-002 | 1 | pass |
| FR-ACC-03 | TC-ACC-003 | 2 | pass |
| FR-ACC-04 | TC-ACC-004 | 2 | pass |
| FR-ACC-05 | TC-ACC-005 | 2 | pass |
| FR-ACC-06 | TC-ACC-006 | 5 | pass |
| FR-ACC-07 | TC-ACC-007 | 2 | pass |
| FR-ANS-01 | TC-ANS-001 | 1 | pass |
| FR-ANS-02 | TC-ANS-002 | 11 | pass |
| FR-ANS-03 | TC-ANS-003 | 15 | pass |
| FR-ANS-04 | TC-ANS-004 | 1 | pass |
| FR-ANS-05 | TC-ANS-005 | 6 | pass |
| FR-ANS-06 | TC-ANS-006 | 2 | pass |
| FR-ANS-07 | TC-ANS-007 | 1 | pass |
| FR-ANS-08 | TC-ANS-008 | 7 | pass |
| FR-ANS-09 | TC-ANS-009 | 3 | pass |
| FR-ANS-10 | TC-ANS-010 | 9 | pass |
| FR-FUP-01 | TC-FUP-001 | 2 | pass |
| FR-FUP-02 | TC-FUP-002 | 2 | pass |
| FR-FUP-03 | TC-FUP-003 | 1 | pass |
| FR-FUP-04 | TC-FUP-004 | 6 | pass |
| FR-GOV-01 | TC-GOV-001 | 1 | pass |
| FR-GOV-02 | TC-GOV-002 | 1 | pass |
| FR-GOV-03 | TC-GOV-003 | 4 | pass |
| FR-GOV-04 | TC-GOV-004 | 4 | pass |
| FR-GOV-05 | TC-GOV-005 | 3 | pass |
| FR-GOV-05 | TC-GOV-006 | 2 | pass |
| FR-GOV-06 | TC-GOV-007 | 4 | pass |
| FR-GOV-07 | TC-GOV-008 | 8 | pass |
| FR-GOV-08 | TC-GOV-009 | 5 | pass |
| FR-GOV-09 | TC-GOV-010 | 4 | pass |
| FR-IDX-01 | TC-IDX-001 | 3 | pass |
| FR-IDX-02 | TC-IDX-002 | 1 | pass |
| FR-IDX-03 | TC-IDX-003 | 19 | pass |
| FR-IDX-04 | TC-IDX-004 | 1 | pass |
| FR-LEG-01 | TC-LEG-001 | 2 | pass |
| FR-LEG-02 | TC-LEG-002 | 7 | pass |
| FR-LIM-01 | TC-LIM-001 | 1 | pass |
| FR-LIM-02 | TC-LIM-002 | 3 | pass |
| FR-LIM-03 | TC-LIM-003 | 1 | pass |
| FR-META-01 | TC-META-001 | 6 | pass |
| FR-META-02 | TC-META-002 | 5 | pass |
| FR-MOD-01 | TC-MOD-001 | 1 | pass |
| FR-MOD-02 | TC-MOD-002 | 1 | pass |
| FR-MOD-03 | TC-MOD-003 | 2 | pass |
| FR-MOD-04 | TC-MOD-004 | 3 | pass |
| FR-MOD-05 | TC-MOD-005 | 4 | pass |
| FR-NB-01 | TC-NB-001 | 1 | pass |
| FR-NB-02 | TC-NB-002 | 1 | pass |
| FR-NB-03 | TC-NB-003 | 2 | pass |
| FR-OUT-01 | TC-OUT-001 | 10 | pass |
| FR-OUT-02 | TC-OUT-002 | 8 | pass |
| FR-RET-01 | TC-RET-001 | 3 | pass |
| FR-RET-02 | TC-RET-002 | 4 | pass |
| FR-RET-03 | TC-RET-003 | 1 | pass |
| FR-RTN-01 | TC-RTN-001 | 3 | pass |
| FR-SRC-01 | TC-SRC-001 | 1 | pass |
| FR-SRC-02 | TC-SRC-002 | 1 | pass |
| FR-SRC-03 | TC-SRC-003 | 3 | pass |
| FR-SRC-03 | TC-SRC-004 | 1 | pass |
| FR-SRC-04 | TC-SRC-005 | 6 | pass |
| FR-SRC-05 | TC-SRC-006 | 1 | pass |
| FR-SRC-06 | TC-SRC-007 | 1 | pass |
| FR-SRC-07 | TC-SRC-008 | 1 | pass |
| FR-SRC-07 | TC-SRC-009 | 7 | pass |
| FR-SRC-08 | TC-SRC-010 | 1 | pass |
| FR-SRC-09 | TC-SRC-011 | 10 | pass |
| FR-SRC-10 | TC-SRC-012 | 2 | pass |
| FR-SRC-11 | TC-SRC-013 | 2 | pass |
| FR-STU-01 | TC-STU-001 | 7 | pass |
| FR-STU-02 | TC-STU-002 | 6 | pass |
| FR-STU-03 | TC-STU-003 | 4 | pass |
| FR-STU-06 | TC-STU-006 | 3 | pass |
| FR-STU-07 | TC-STU-007 | 4 | pass |
| FR-STU-08 | TC-STU-008 | 4 | pass |
| FR-UI-01 | TC-UI-001 | 6 | pass |
| FR-UI-02 | TC-UI-002 | 3 | pass |
| FR-UI-03 | TC-UI-004 | 1 | pass |
| FR-UI-05 | TC-UI-005 | 1 | pass |
| FR-UI-06 | TC-UI-006 | 1 | pass |
| FR-UI-07 | TC-UI-007 | 3 | pass |
| FR-UI-08 | TC-UI-008 | 10 | pass |
| FR-UI-09 | TC-UI-009 | 4 | pass |
| FR-UI-10 | TC-UI-010 | 2 | pass |
| FR-UI-11 | TC-UI-011 | 1 | pass |
| FR-UI-12 | TC-UI-012 | 4 | pass |
| NFR-EVAL-01 | TC-EVAL-001 | 1 | pass |
| NFR-EVAL-02 | TC-EVAL-002 | 1 | pass |
| NFR-EVAL-02 | TC-EVAL-003 | 1 | pass |
| NFR-EVAL-02 | TC-EVAL-004 | 1 | pass |
| NFR-EVAL-02 | TC-EVAL-006 | 1 | pass |
| NFR-EVAL-02 | TC-EVAL-007 | 1 | pass |
| NFR-EVAL-02 | TC-EVAL-008 | 1 | pass |
| NFR-EVAL-02 | TC-EVAL-009 | 1 | pass |
| NFR-EVAL-02 | TC-EVAL-010 | 1 | pass |
| NFR-EVAL-02 | TC-EVAL-011 | 5 | pass |
| NFR-EVAL-02 | TC-EVAL-012 | 1 | pass |
| NFR-EVAL-02 | TC-EVAL-013 | 3 | pass |
| NFR-EVAL-02 | TC-EVAL-014 | 35 | pass |
| NFR-EVAL-02 | TC-EVAL-015 | 29 | pass |
| NFR-EVAL-03 | TC-EVAL-005 | 1 | pass |
| NFR-LOG-01 | TC-LOG-001 | 1 | pass |
| NFR-REV-01 | TC-REV-001 | 1 | pass |
| NFR-REV-02 | TC-REV-002 | 3 | pass |
| NFR-REV-03 | TC-REV-003 | 3 | pass |
| NFR-SEC-01 | TC-SEC-001 | 1 | pass |
| NFR-SEC-02 | TC-SEC-002 | 7 | pass |
| NFR-SEC-03 | TC-SEC-003 | 2 | pass |
| NFR-SEC-04 | TC-SEC-004 | 22 | pass |
| NFR-SEC-05 | TC-SEC-005 | 2 | pass |
| NFR-SEC-06 | TC-SEC-006 | 2 | pass |
| NFR-SEC-07 | TC-SEC-007 | 1 | pass |
| NFR-UI-01 | TC-UI-003 | 2 | pass |

Test cases: 113 pass, 0 partly skipped, 0 fail, 0 skipped.
Catalogue cases without a test in this run: none.
Other tests (regression tests without a test-case ID): 88 run, 88 pass, 0 fail, 0 skipped.
