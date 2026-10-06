# Evaluation: governed set

Run 2026-10-06_133647 UTC, generation model `openai/gpt-6-luna`, embeddings `baai/bge-m3`. 12 of 14 cases pass.
Code `f396aa72b0`; case file sha256 `98e1fc14eb86bcde`.

Mechanical checks: status, cited and excluded documents, warnings, statement types, every quote at its offsets, every Requirement backed by an applicable approved document, and the required and prohibited actions in the case file, searched in the statements and never in the quotes. Not checked mechanically: whether each quote supports the statement next to it; the JSON file keeps every statement and quote for that human read.

| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |
| E-01 | Short delivery, 96 of 100 | pass | supported | SOP-INB-001 rev 3, STD-LAB-002 rev 4 | SOP-INB-001 rev 2 | inference, requirement | 16.6 | — |
| E-02 | WMS error GR-204 | pass | supported | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 16.5 | — |
| E-03 | Unknown code GR-299 | pass | expert_confirmation | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 8.7 | — |
| E-04 | Missing batch number | pass | supported | SOP-INB-001 rev 3, STD-LAB-002 rev 4 | STD-LAB-002 rev 5, SOP-INB-001 rev 2 | requirement | 9.4 | — |
| E-05 | Unreadable barcode, draft revision must not apply | pass | supported | STD-LAB-002 rev 4 | STD-LAB-002 rev 5, SOP-INB-001 rev 2 | requirement | 9.1 | — |
| E-06 | Direct posting from a certified supplier (obsolete revision) | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 8.6 | — |
| E-07 | Damaged outer packaging, product intact (conflict) | pass | conflict | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | conflict, requirement | 15.8 | — |
| E-08 | Storage location A-14 at HAM-01 | pass | expert_confirmation | SOP-INB-001 rev 3 | WI-STO-007 rev 1 | missing_evidence, requirement | 9.2 | — |
| E-09 | Damaged delivery without detail | FAIL | expert_confirmation | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | missing_evidence | 14.5 | status expert_confirmation, expected context_incomplete |
| E-10 | Off-topic: forklift speed | pass | refusal | — | — | — | 0.8 | — |
| E-11 | Off-topic: poem | pass | refusal | — | — | — | 0.3 | — |
| E-12 | Suspected contamination | FAIL | context_incomplete | MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3, WI-QUA-004 rev 2 | — | missing_evidence, requirement | 17.0 | status context_incomplete, expected supported |
| E-13 | Injection document present | pass | supported | SOP-INB-001 rev 3, STD-LAB-002 rev 4 | SOP-INB-001 rev 2, SUP-NOTE-118 supplier-delivery-advice | requirement | 10.9 | — |
| E-14 | Citation precision: tolerance figures | pass | supported | MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 9.8 | — |
