# Results

Each run writes a `.json` file (every case, every check) and a `.md` summary. A file counts as evidence only when its `provenance` block names a commit with `"dirty": false`: that commit's code and case file (by hash) produced it.

## Versioned

| File | Code | Cases | Result | Note |
| :--- | :--- | :--- | :--- | :--- |
| `2026-10-06_132816-openai_gpt-6-luna-governed` | `f6da0bd`, clean | `98e1fc14eb86bcde` | 14 of 14 | With the action checks (EVAL-01) |
| `2026-10-06_133025-openai_gpt-6-luna-holdout` | `f6da0bd`, clean | `ad8ed053143a4c64` | 11 of 11 | With the action checks (EVAL-01) |
| `2026-10-06_1316-openai_gpt-6-luna-generic` | `d82528a`, clean | `26cfa0915630d06d` | 6 of 6 | Current scorer: terms counted only in the statements; statements and quotes kept |
| `2026-10-06_1302-openai_gpt-6-luna-generic` | `3d4c88e`, clean | `26cfa0915630d06d` | 6 of 6 | Scored before the scorer stopped counting terms that appear only in quotes (EVAL-01) |

## Exploratory (code version not recorded)

These runs happened during development, before result files recorded their code version. Some ran between changes to the cases, the prompts or the scorer, so they cannot be reproduced exactly. All governed and held-out runs here also predate the action checks (`must_say`, `must_not_say`). They stay here as a record of what was measured at the time, misses included, not as release evidence.

- `2026-10-05_2218-bakeoff`, `2026-10-06_0610-bakeoff`: the embedding and generation model comparisons.
- `2026-10-05_2224`, `2026-10-05_2226`, `2026-10-05_2304`, `2026-10-05_2319` and `2026-10-06_0820` `-openai_gpt-6-luna-generic`: earlier generic runs.
- Every `-governed`, `-governed-subset`, `-holdout` and `-holdout-subset` file dated 2026-10-05 or 2026-10-06 before 07:00 UTC: Resolution Card runs while the card prompt and the cases were tuned, and the first fallback comparisons (Gemini 3.5 Flash Lite, Gemini 3.8 Flash, Claude Haiku 4.5, GPT-6 Luna Pro). The `openai_no-such-model-smoke` files check that an unknown model fails cleanly; they are not quality results.
