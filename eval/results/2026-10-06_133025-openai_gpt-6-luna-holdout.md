# Evaluation: holdout set

Run 2026-10-06_133025 UTC, generation model `openai/gpt-6-luna`, embeddings `baai/bge-m3`. 11 of 11 cases pass.
Code `f6da0bdb14`; case file sha256 `ad8ed053143a4c64`.

Mechanical checks: status, cited and excluded documents, warnings, statement types, every quote at its offsets, every Requirement backed by an applicable approved document, and the required and prohibited actions in the case file, searched in the statements and never in the quotes. Not checked mechanically: whether each quote supports the statement next to it; the JSON file keeps every statement and quote for that human read.

| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |
| H-01 | Small shortage within tolerance | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 19.0 | — |
| H-02 | WMS error GR-101 | pass | supported | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | missing_evidence, requirement | 9.9 | — |
| H-03 | Code GR-512 (documented) | pass | supported | GUIDE-WMS-003 rev 1, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 14.8 | — |
| H-04 | Torn stretch wrap, parts intact (conflict) | pass | conflict | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | conflict, requirement | 12.5 | — |
| H-05 | Wet cartons | pass | supported | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | — | requirement | 5.9 | — |
| H-06 | Off-topic: football | pass | refusal | — | — | — | 0.8 | — |
| H-07 | Barcode with the draft revision in mind | pass | supported | STD-LAB-002 rev 4 | STD-LAB-002 rev 5 | inference, requirement | 10.9 | — |
| H-08 | Chemical smell | pass | supported | WI-QUA-004 rev 2 | — | requirement | 10.8 | — |
| H-09 | Damage without detail | pass | context_incomplete | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | missing_evidence, requirement | 20.6 | — |
| H-10 | Aisle A-12 at HAM-01 | pass | expert_confirmation | SOP-INB-001 rev 3 | WI-STO-007 rev 1 | missing_evidence, requirement | 10.2 | — |
| H-11 | Unknown code GR-777 | pass | expert_confirmation | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2 | SOP-INB-001 rev 2 | requirement | 7.8 | — |
