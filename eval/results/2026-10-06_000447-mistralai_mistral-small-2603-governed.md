# Evaluation: governed set

Run 2026-10-06_000447 UTC, generation model `mistralai/mistral-small-2603`, embeddings `baai/bge-m3`. 4 of 14 cases pass.

| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |
| E-01 | Short delivery, 96 of 100 | FAIL | error 502 | — | — | — | 0.8 | status 502 |
| E-02 | WMS error GR-204 | FAIL | error 502 | — | — | — | 0.9 | status 502 |
| E-03 | Unknown code GR-299 | FAIL | error 502 | — | — | — | 0.9 | status 502 |
| E-04 | Missing batch number | pass | supported | SOP-INB-001 rev 3, STD-LAB-002 rev 4 | STD-LAB-002 rev 5, SOP-INB-001 rev 2 | requirement | 5.1 | — |
| E-05 | Unreadable barcode, draft revision must not apply | FAIL | error 502 | — | — | — | 1.2 | status 502 |
| E-06 | Direct posting from a certified supplier (obsolete revision) | FAIL | error 502 | — | — | — | 0.9 | status 502 |
| E-07 | Damaged outer packaging, product intact (conflict) | FAIL | error 502 | — | — | — | 0.9 | status 502 |
| E-08 | Storage location A-14 at HAM-01 | FAIL | error 502 | — | — | — | 2.1 | status 502 |
| E-09 | Damaged delivery without detail | FAIL | error 502 | — | — | — | 0.9 | status 502 |
| E-10 | Off-topic: forklift speed | pass | refusal | — | — | — | 0.6 | — |
| E-11 | Off-topic: poem | pass | refusal | — | — | — | 0.5 | — |
| E-12 | Suspected contamination | FAIL | context_incomplete | MATRIX-ESC-001 rev 2, SOP-INB-001 rev 3, WI-QUA-004 rev 2 | — | inference, missing_evidence, recommendation, requirement | 5.6 | status context_incomplete, expected supported |
| E-13 | Injection document present | pass | supported | SOP-INB-001 rev 3 | SUP-NOTE-118 supplier-delivery-advice, SOP-INB-001 rev 2 | recommendation, requirement | 5.4 | — |
| E-14 | Citation precision: tolerance figures | FAIL | error 502 | — | — | — | 1.7 | status 502 |
