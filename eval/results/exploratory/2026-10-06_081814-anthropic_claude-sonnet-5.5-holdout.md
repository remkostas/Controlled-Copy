# Evaluation: holdout set

Run 2026-10-06_081814 UTC, generation model `anthropic/claude-sonnet-5.5`, embeddings `baai/bge-m3`. 10 of 11 cases pass.

| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |
| H-01 | Small shortage within tolerance | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 7.6 | — |
| H-02 | WMS error GR-101 | pass | supported | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 3.9 | — |
| H-03 | Code GR-512 (documented) | pass | supported | GUIDE-WMS-003 rev 1, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 8.3 | — |
| H-04 | Torn stretch wrap, parts intact (conflict) | pass | conflict | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | conflict, inference, recommendation, requirement | 14.3 | — |
| H-05 | Wet cartons | pass | supported | MATRIX-ESC-001 rev 2, WI-QUA-004 rev 2 | — | inference, recommendation, requirement | 11.7 | — |
| H-06 | Off-topic: football | pass | refusal | — | — | — | 0.5 | — |
| H-07 | Barcode with the draft revision in mind | FAIL | context_incomplete | STD-LAB-002 rev 4 | STD-LAB-002 rev 5 | inference, missing_evidence, recommendation, requirement | 5.9 | status context_incomplete, expected supported |
| H-08 | Chemical smell | pass | supported | WI-QUA-004 rev 2 | — | requirement | 3.5 | — |
| H-09 | Damage without detail | pass | context_incomplete | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | inference, missing_evidence, requirement | 14.7 | — |
| H-10 | Aisle A-12 at HAM-01 | pass | expert_confirmation | SOP-INB-001 rev 3 | WI-STO-007 rev 1 | inference, missing_evidence, recommendation, requirement | 8.2 | — |
| H-11 | Unknown code GR-777 | pass | expert_confirmation | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 4.2 | — |
