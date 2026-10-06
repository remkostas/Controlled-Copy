# Evaluation: holdout set

Run 2026-10-06_084936 UTC, generation model `deepseek/deepseek-v4-pro`, embeddings `baai/bge-m3`. 6 of 11 cases pass.

| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |
| H-01 | Small shortage within tolerance | FAIL | error 504 | — | — | — | 91.3 | status 504 |
| H-02 | WMS error GR-101 | pass | supported | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2 | SOP-INB-001 rev 2 | inference, requirement | 33.5 | — |
| H-03 | Code GR-512 (documented) | pass | supported | GUIDE-WMS-003 rev 1, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 6.4 | — |
| H-04 | Torn stretch wrap, parts intact (conflict) | pass | conflict | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | conflict, inference, requirement | 7.5 | — |
| H-05 | Wet cartons | FAIL | context_incomplete | WI-QUA-004 rev 2 | — | missing_evidence, requirement | 89.3 | status context_incomplete, expected supported |
| H-06 | Off-topic: football | pass | refusal | — | — | — | 1.0 | — |
| H-07 | Barcode with the draft revision in mind | FAIL | context_incomplete | STD-LAB-002 rev 4 | STD-LAB-002 rev 5 | inference, missing_evidence, requirement | 6.1 | status context_incomplete, expected supported |
| H-08 | Chemical smell | pass | supported | WI-QUA-004 rev 2 | — | requirement | 43.3 | — |
| H-09 | Damage without detail | FAIL | error 504 | — | — | — | 90.8 | status 504 |
| H-10 | Aisle A-12 at HAM-01 | FAIL | error 504 | — | — | — | 90.4 | status 504 |
| H-11 | Unknown code GR-777 | pass | expert_confirmation | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 31.7 | — |
