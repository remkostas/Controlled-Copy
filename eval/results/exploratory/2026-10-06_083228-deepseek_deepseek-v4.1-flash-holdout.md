# Evaluation: holdout set

Run 2026-10-06_083228 UTC, generation model `deepseek/deepseek-v4.1-flash`, embeddings `baai/bge-m3`. 3 of 11 cases pass.

| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |
| H-01 | Small shortage within tolerance | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 25.0 | — |
| H-02 | WMS error GR-101 | FAIL | expert_confirmation | — | SOP-INB-001 rev 2 | missing_evidence | 4.2 | status expert_confirmation, expected supported; does not cite GUIDE-WMS-003 rev 1; no statement of type requirement |
| H-03 | Code GR-512 (documented) | pass | supported | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 19.7 | — |
| H-04 | Torn stretch wrap, parts intact (conflict) | FAIL | error 504 | — | — | — | 57.0 | status 504 |
| H-05 | Wet cartons | FAIL | context_incomplete | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | — | missing_evidence, requirement | 12.8 | status context_incomplete, expected supported |
| H-06 | Off-topic: football | pass | refusal | — | — | — | 0.4 | — |
| H-07 | Barcode with the draft revision in mind | FAIL | error 502 | — | — | — | 81.0 | status 502 |
| H-08 | Chemical smell | FAIL | context_incomplete | WI-QUA-004 rev 2 | — | missing_evidence, requirement | 13.3 | status context_incomplete, expected supported |
| H-09 | Damage without detail | FAIL | error 502 | — | — | — | 72.6 | status 502 |
| H-10 | Aisle A-12 at HAM-01 | FAIL | error 502 | — | — | — | 67.8 | status 502 |
| H-11 | Unknown code GR-777 | FAIL | error 504 | — | — | — | 90.3 | status 504 |
