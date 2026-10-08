# Evaluation: generic set

Run 2026-10-05_2224 UTC, generation model `openai/gpt-6-luna`, embeddings `baai/bge-m3`. 5 of 6 cases pass.

| Case | Title | Result | Outcome | Citations | Cited pages | Seconds | Reasons |
| :--- | :--- | :--- | :--- | ---: | :--- | ---: | :--- |
| G-01 | Answerable: the four Core functions | FAIL | refusal | 0 | — | 2.4 | expected an answer, got refusal |
| G-02 | Answerable: characteristics of trustworthy AI | pass | answer | 1 | 17 | 5.4 | — |
| G-03 | Answerable: when the framework is reviewed | pass | answer | 1 | 3 | 1.8 | — |
| G-04 | Unsupported question | pass | refusal | 0 | — | 0.5 | — |
| G-05 | Citation check: definition of an AI system | pass | answer | 2 | 6 | 2.9 | — |
| G-06 | Studio Briefing: every citation verifies | pass | briefing | 11 | — | 15.0 | — |
