# Evaluation: holdout set

Run 2026-10-06_060525 UTC, generation model `openai/gpt-6-luna-pro`, embeddings `baai/bge-m3`. 11 of 11 cases pass.

| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |
| H-01 | Small shortage within tolerance | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 21.2 | — |
| H-02 | WMS error GR-101 | pass | supported | GUIDE-WMS-003 rev 1, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 13.7 | — |
| H-03 | Code GR-512 (documented) | pass | supported | GUIDE-WMS-003 rev 1 | SOP-INB-001 rev 2 | requirement | 11.1 | — |
| H-04 | Torn stretch wrap, parts intact (conflict) | pass | conflict | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | conflict, requirement | 25.5 | — |
| H-05 | Wet cartons | pass | supported | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | — | requirement | 16.1 | — |
| H-06 | Off-topic: football | pass | refusal | — | — | — | 0.7 | — |
| H-07 | Barcode with the draft revision in mind | pass | supported | STD-LAB-002 rev 4 | STD-LAB-002 rev 5 | inference, requirement | 14.2 | — |
| H-08 | Chemical smell | pass | supported | WI-QUA-004 rev 2 | — | inference, requirement | 33.8 | — |
| H-09 | Damage without detail | pass | context_incomplete | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | missing_evidence, requirement | 27.4 | — |
| H-10 | Aisle A-12 at HAM-01 | pass | expert_confirmation | SOP-INB-001 rev 3 | WI-STO-007 rev 1 | missing_evidence, requirement | 18.3 | — |
| H-11 | Unknown code GR-777 | pass | expert_confirmation | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 13.3 | — |
