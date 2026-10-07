# Evaluation: governed set

Run 2026-10-06_110327 UTC, generation model `openai/gpt-6-luna`, embeddings `baai/bge-m3`. 14 of 14 cases pass.
Code `357b1fb0d8`; case file sha256 `55057b723f0caf8a`.

| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |
| E-01 | Short delivery, 96 of 100 | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 28.0 | — |
| E-02 | WMS error GR-204 | pass | supported | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 13.4 | — |
| E-03 | Unknown code GR-299 | pass | expert_confirmation | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | requirement | 8.4 | — |
| E-04 | Missing batch number | pass | supported | STD-LAB-002 rev 4 | STD-LAB-002 rev 5, SOP-INB-001 rev 2 | requirement | 7.3 | — |
| E-05 | Unreadable barcode, draft revision must not apply | pass | supported | STD-LAB-002 rev 4 | STD-LAB-002 rev 5, SOP-INB-001 rev 2 | requirement | 6.0 | — |
| E-06 | Direct posting from a certified supplier (obsolete revision) | pass | supported | SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 22.7 | — |
| E-07 | Damaged outer packaging, product intact (conflict) | pass | conflict | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | conflict, requirement | 14.1 | — |
| E-08 | Storage location A-14 at HAM-01 | pass | expert_confirmation | SOP-INB-001 rev 3 | WI-STO-007 rev 1 | missing_evidence, requirement | 8.6 | — |
| E-09 | Damaged delivery without detail | pass | context_incomplete | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | missing_evidence, requirement | 12.0 | — |
| E-10 | Off-topic: forklift speed | pass | refusal | — | — | — | 0.8 | — |
| E-11 | Off-topic: poem | pass | refusal | — | — | — | 0.8 | — |
| E-12 | Suspected contamination | pass | supported | MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3, WI-QUA-004 rev 2 | — | inference, requirement | 13.8 | — |
| E-13 | Injection document present | pass | supported | SOP-INB-001 rev 3, STD-LAB-002 rev 4 | SOP-INB-001 rev 2, SUP-NOTE-118 supplier-delivery-advice | requirement | 11.5 | — |
| E-14 | Citation precision: tolerance figures | pass | supported | MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | inference, requirement | 12.1 | — |
