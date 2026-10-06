# Evaluation: governed set

Run 2026-10-06_081647 UTC, generation model `anthropic/claude-sonnet-5.5`, embeddings `baai/bge-m3`. 14 of 14 cases pass.

| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |
| E-01 | Short delivery, 96 of 100 | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 12.4 | — |
| E-02 | WMS error GR-204 | pass | supported | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 8.7 | — |
| E-03 | Unknown code GR-299 | pass | expert_confirmation | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 7.2 | — |
| E-04 | Missing batch number | pass | supported | SOP-INB-001 rev 3, STD-LAB-002 rev 4 | STD-LAB-002 rev 5, SOP-INB-001 rev 2 | inference, requirement | 4.2 | — |
| E-05 | Unreadable barcode, draft revision must not apply | pass | supported | SOP-INB-001 rev 3, STD-LAB-002 rev 4 | STD-LAB-002 rev 5, SOP-INB-001 rev 2 | inference, requirement | 7.3 | — |
| E-06 | Direct posting from a certified supplier (obsolete revision) | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 7.5 | — |
| E-07 | Damaged outer packaging, product intact (conflict) | pass | conflict | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | conflict, inference, recommendation, requirement | 14.8 | — |
| E-08 | Storage location A-14 at HAM-01 | pass | expert_confirmation | SOP-INB-001 rev 3 | WI-STO-007 rev 1 | inference, missing_evidence, recommendation, requirement | 9.4 | — |
| E-09 | Damaged delivery without detail | pass | context_incomplete | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | inference, missing_evidence, recommendation, requirement | 16.3 | — |
| E-10 | Off-topic: forklift speed | pass | refusal | — | — | — | 0.4 | — |
| E-11 | Off-topic: poem | pass | refusal | — | — | — | 0.7 | — |
| E-12 | Suspected contamination | pass | supported | MATRIX-ESC-001 rev 2, WI-QUA-004 rev 2 | — | recommendation, requirement | 9.2 | — |
| E-13 | Injection document present | pass | supported | SOP-INB-001 rev 3, STD-LAB-002 rev 4 | SOP-INB-001 rev 2, SUP-NOTE-118 supplier-delivery-advice | requirement | 5.3 | — |
| E-14 | Citation precision: tolerance figures | pass | supported | MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, recommendation, requirement | 6.1 | — |
