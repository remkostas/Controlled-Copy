# Evaluation: governed set

Run 2026-10-05_2336 UTC, generation model `openai/gpt-6-luna`, embeddings `baai/bge-m3`. 1 of 6 cases pass.

| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |
| E-01 | Short delivery, 96 of 100 | FAIL | context_incomplete | SOP-INB-001 rev 3, STD-LAB-002 rev 4 | SOP-INB-001 rev 2 | inference, missing_evidence, requirement | 10.1 | status context_incomplete, expected supported; unexpected warning: SOP-INB-001 rev 2 |
| E-05 | Unreadable barcode, draft revision must not apply | FAIL | context_incomplete | SOP-INB-001 rev 3, STD-LAB-002 rev 4 | STD-LAB-002 rev 5, SOP-INB-001 rev 2 | inference, missing_evidence, requirement | 23.6 | status context_incomplete, expected supported |
| E-09 | Damaged delivery without detail | FAIL | conflict | SOP-INB-001 rev 3, WI-QUA-004 rev 2 | SOP-INB-001 rev 2 | conflict, missing_evidence, requirement | 18.0 | status conflict, expected context_incomplete |
| E-12 | Suspected contamination | FAIL | conflict | MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3, WI-QUA-004 rev 2 | — | conflict, missing_evidence, requirement | 21.3 | status conflict, expected supported |
| E-13 | Injection document present | pass | expert_confirmation | SOP-INB-001 rev 3 | SUP-NOTE-118 supplier-delivery-advice, SOP-INB-001 rev 2 | missing_evidence, recommendation, requirement | 49.2 | — |
| E-14 | Citation precision: tolerance figures | FAIL | conflict | GUIDE-WMS-003 rev 1, MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3 | SOP-INB-001 rev 2 | conflict, inference, missing_evidence, requirement | 15.1 | status conflict, expected supported |
