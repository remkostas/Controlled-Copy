# Evaluation: holdout set

Run 2026-10-06_110517 UTC, generation model `openai/gpt-6-luna`, embeddings `baai/bge-m3`. 11 of 11 cases pass.
Code `357b1fb0d8`; case file sha256 `a9453aeccf8a7b46`.

| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |
| H-01 | Small shortage within tolerance | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 13.8 | — |
| H-02 | WMS error GR-101 | pass | supported | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 10.6 | — |
| H-03 | Code GR-512 (documented) | pass | supported | GUIDE-WMS-003 rev 1, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 7.1 | — |
| H-04 | Torn stretch wrap, parts intact (conflict) | pass | conflict | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | conflict, requirement | 13.5 | — |
| H-05 | Wet cartons | pass | supported | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | — | requirement | 9.9 | — |
| H-06 | Off-topic: football | pass | refusal | — | — | — | 0.4 | — |
| H-07 | Barcode with the draft revision in mind | pass | supported | STD-LAB-002 rev 4 | STD-LAB-002 rev 5 | requirement | 10.1 | — |
| H-08 | Chemical smell | pass | supported | WI-QUA-004 rev 2 | — | inference, requirement | 8.5 | — |
| H-09 | Damage without detail | pass | context_incomplete | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | missing_evidence, requirement | 16.2 | — |
| H-10 | Aisle A-12 at HAM-01 | pass | expert_confirmation | SOP-INB-001 rev 3 | WI-STO-007 rev 1 | missing_evidence, requirement | 9.7 | — |
| H-11 | Unknown code GR-777 | pass | expert_confirmation | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 7.0 | — |
