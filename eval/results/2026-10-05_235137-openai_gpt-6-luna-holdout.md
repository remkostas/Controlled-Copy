# Evaluation: holdout set

Run 2026-10-05_235137 UTC, generation model `openai/gpt-6-luna`, embeddings `baai/bge-m3`. 9 of 10 cases pass.

| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |
| H-01 | Small shortage within tolerance | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 10.8 | — |
| H-02 | WMS error GR-101 | pass | supported | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 5.8 | — |
| H-03 | Unknown code GR-512 | FAIL | supported | GUIDE-WMS-003 rev 1, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 4.6 | status supported, expected expert_confirmation; does not cite MATRIX-ESC-001 rev 2; GR-512 not reported as undocumented |
| H-04 | Torn stretch wrap, parts intact (conflict) | pass | conflict | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | conflict, requirement | 8.8 | — |
| H-05 | Wet cartons | pass | supported | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | — | requirement | 8.6 | — |
| H-06 | Off-topic: football | pass | refusal | — | — | — | 0.3 | — |
| H-07 | Barcode with the draft revision in mind | pass | supported | STD-LAB-002 rev 4 | STD-LAB-002 rev 5 | requirement | 8.2 | — |
| H-08 | Chemical smell | pass | supported | WI-QUA-004 rev 2 | — | requirement | 9.5 | — |
| H-09 | Damage without detail | pass | context_incomplete | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | missing_evidence, requirement | 13.6 | — |
| H-10 | Aisle A-12 at HAM-01 | pass | expert_confirmation | SOP-INB-001 rev 3 | WI-STO-007 rev 1 | missing_evidence, requirement | 7.4 | — |
