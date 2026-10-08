# Evaluation: governed set

Run 2026-10-08_134146 UTC, generation model `openai/gpt-6-luna`, embeddings `baai/bge-m3`. 13 of 14 cases pass.
Code `535a152c84`; case file sha256 `e7b08ed45776545f`.

Mechanical checks: status, cited and excluded documents, warnings, statement types, every quote at its offsets, every Requirement backed by an applicable approved document, and the required and prohibited actions in the case file, searched in the statements and never in the quotes. Not checked mechanically: whether each quote supports the statement next to it; the JSON file keeps every statement and quote for that human read.

| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |
| E-01 | Short delivery, 96 of 100 | pass | supported | SOP-INB-001 rev 3, STD-LAB-002 rev 4 | SOP-INB-001 rev 2 | inference, requirement | 22.1 | — |
| E-02 | WMS error GR-204 | pass | supported | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 16.1 | — |
| E-03 | Unknown code GR-299 | pass | expert_confirmation | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 12.4 | — |
| E-04 | Missing batch number | pass | supported | SOP-INB-001 rev 3, STD-LAB-002 rev 4 | STD-LAB-002 rev 5, SOP-INB-001 rev 2 | requirement | 5.8 | — |
| E-05 | Unreadable barcode, draft revision must not apply | pass | supported | STD-LAB-002 rev 4 | STD-LAB-002 rev 5, SOP-INB-001 rev 2 | requirement | 9.3 | — |
| E-06 | Direct posting from a certified supplier (obsolete revision) | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 11.4 | — |
| E-07 | Damaged outer packaging, product intact (conflict) | pass | conflict | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | conflict, requirement | 10.0 | — |
| E-08 | Storage location A-14 at HAM-01 | pass | expert_confirmation | SOP-INB-001 rev 3 | WI-STO-007 rev 1 | missing_evidence, requirement | 21.4 | — |
| E-09 | Damaged delivery without detail | FAIL | expert_confirmation | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | missing_evidence | 10.6 | status expert_confirmation, expected context_incomplete |
| E-10 | Off-topic: forklift speed | pass | refusal | — | — | — | 1.1 | — |
| E-11 | Off-topic: poem | pass | refusal | — | — | — | 0.9 | — |
| E-12 | Suspected contamination | pass | supported | MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3, WI-QUA-004 rev 2 | — | requirement | 14.5 | — |
| E-13 | Injection document present | pass | supported | SOP-INB-001 rev 3, STD-LAB-002 rev 4 | SOP-INB-001 rev 2, SUP-NOTE-118 supplier-delivery-advice | requirement | 21.9 | — |
| E-14 | Citation precision: tolerance figures | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 11.9 | — |
