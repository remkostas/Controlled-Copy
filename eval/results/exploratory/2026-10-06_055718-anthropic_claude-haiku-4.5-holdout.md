# Evaluation: holdout set

Run 2026-10-06_055718 UTC, generation model `anthropic/claude-haiku-4.5`, embeddings `baai/bge-m3`. 10 of 11 cases pass.

| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |
| H-01 | Small shortage within tolerance | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 5.9 | — |
| H-02 | WMS error GR-101 | pass | supported | GUIDE-WMS-003 rev 1 | SOP-INB-001 rev 2 | requirement | 4.7 | — |
| H-03 | Code GR-512 (documented) | pass | supported | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2 | SOP-INB-001 rev 2 | requirement | 3.7 | — |
| H-04 | Torn stretch wrap, parts intact (conflict) | pass | conflict | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | conflict, missing_evidence, requirement | 6.0 | — |
| H-05 | Wet cartons | pass | supported | MATRIX-ESC-001 rev 2, WI-QUA-004 rev 2 | — | inference, requirement | 4.1 | — |
| H-06 | Off-topic: football | pass | refusal | — | — | — | 2.4 | — |
| H-07 | Barcode with the draft revision in mind | FAIL | context_incomplete | STD-LAB-002 rev 4 | STD-LAB-002 rev 5 | missing_evidence, requirement | 4.8 | status context_incomplete, expected supported |
| H-08 | Chemical smell | pass | supported | WI-QUA-004 rev 2 | — | missing_evidence, requirement | 4.4 | — |
| H-09 | Damage without detail | pass | context_incomplete | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | missing_evidence, requirement | 6.8 | — |
| H-10 | Aisle A-12 at HAM-01 | pass | expert_confirmation | GUIDE-WMS-003 rev 1, SOP-INB-001 rev 3 | WI-STO-007 rev 1 | missing_evidence, requirement | 7.0 | — |
| H-11 | Unknown code GR-777 | pass | expert_confirmation | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2 | SOP-INB-001 rev 2 | requirement | 3.0 | — |
