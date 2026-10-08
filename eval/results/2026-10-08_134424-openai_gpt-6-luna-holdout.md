# Evaluation: holdout set

Run 2026-10-08_134424 UTC, generation model `openai/gpt-6-luna`, embeddings `baai/bge-m3`. 11 of 11 cases pass.
Code `535a152c84`; case file sha256 `a3f270c7161185dd`.

Mechanical checks: status, cited and excluded documents, warnings, statement types, every quote at its offsets, every Requirement backed by an applicable approved document, and the required and prohibited actions in the case file, searched in the statements and never in the quotes. Not checked mechanically: whether each quote supports the statement next to it; the JSON file keeps every statement and quote for that human read.

| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |
| H-01 | Small shortage within tolerance | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 24.4 | — |
| H-02 | WMS error GR-101 | pass | supported | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 13.6 | — |
| H-03 | Code GR-512 (documented) | pass | supported | GUIDE-WMS-003 rev 1, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 7.6 | — |
| H-04 | Torn stretch wrap, parts intact (conflict) | pass | conflict | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | conflict, requirement | 11.6 | — |
| H-05 | Wet cartons | pass | supported | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | — | requirement | 20.3 | — |
| H-06 | Off-topic: football | pass | refusal | — | — | — | 0.5 | — |
| H-07 | Barcode with the draft revision in mind | pass | supported | STD-LAB-002 rev 4 | STD-LAB-002 rev 5 | requirement | 12.1 | — |
| H-08 | Chemical smell | pass | supported | WI-QUA-004 rev 2 | — | inference, requirement | 13.1 | — |
| H-09 | Damage without detail | pass | context_incomplete | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | missing_evidence, requirement | 28.7 | — |
| H-10 | Aisle A-12 at HAM-01 | pass | expert_confirmation | — | WI-STO-007 rev 1 | recommendation | 12.2 | — |
| H-11 | Unknown code GR-777 | pass | expert_confirmation | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 9.6 | — |
