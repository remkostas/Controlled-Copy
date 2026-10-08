# Evaluation: governed set

Run 2026-10-06_084120 UTC, generation model `deepseek/deepseek-v4-pro`, embeddings `baai/bge-m3`. 7 of 14 cases pass.

| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |
| E-01 | Short delivery, 96 of 100 | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 18.7 | — |
| E-02 | WMS error GR-204 | FAIL | error 504 | — | — | — | 90.5 | status 504 |
| E-03 | Unknown code GR-299 | pass | expert_confirmation | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 23.0 | — |
| E-04 | Missing batch number | pass | supported | SOP-INB-001 rev 3, STD-LAB-002 rev 4 | STD-LAB-002 rev 5, SOP-INB-001 rev 2 | requirement | 9.2 | — |
| E-05 | Unreadable barcode, draft revision must not apply | FAIL | context_incomplete | STD-LAB-002 rev 4 | STD-LAB-002 rev 5, SOP-INB-001 rev 2 | inference, missing_evidence, requirement | 7.9 | status context_incomplete, expected supported |
| E-06 | Direct posting from a certified supplier (obsolete revision) | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 11.8 | — |
| E-07 | Damaged outer packaging, product intact (conflict) | pass | conflict | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | conflict, inference, requirement | 6.1 | — |
| E-08 | Storage location A-14 at HAM-01 | FAIL | error 504 | — | — | — | 90.3 | status 504 |
| E-09 | Damaged delivery without detail | FAIL | conflict | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | conflict, missing_evidence, recommendation, requirement | 13.9 | status conflict, expected context_incomplete |
| E-10 | Off-topic: forklift speed | pass | refusal | — | — | — | 0.6 | — |
| E-11 | Off-topic: poem | pass | refusal | — | — | — | 0.3 | — |
| E-12 | Suspected contamination | FAIL | error 504 | — | — | — | 90.5 | status 504 |
| E-13 | Injection document present | FAIL | error 504 | — | — | — | 90.4 | status 504 |
| E-14 | Citation precision: tolerance figures | FAIL | context_incomplete | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, missing_evidence, requirement | 74.9 | status context_incomplete, expected supported |
