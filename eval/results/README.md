# Results

Each run writes a `.json` file (every case, every check) and a `.md` summary. A file counts as evidence only when its `provenance` block names a commit with `"dirty": false`: that commit's code and case file (by hash) produced it.

## Versioned

| File | Code | Cases | Result | Note |
| :--- | :--- | :--- | :--- | :--- |
| `2026-10-06_1302-openai_gpt-6-luna-generic` | `3d4c88e`, clean | `26cfa0915630d06d` | 6 of 6 | Scored before the scorer stopped counting terms that appear only in quotes (EVAL-01) |

## Exploratory (code version not recorded)

These runs happened during development, before result files recorded their code version. Some ran between changes to the cases, the prompts or the scorer, so they cannot be reproduced exactly. They stay here as a record of what was measured at the time, misses included, not as release evidence.

- `2026-10-05_2218-bakeoff`, `2026-10-06_0610-bakeoff`: the embedding and generation model comparisons.
- `2026-10-05_2224`, `2026-10-05_2226`, `2026-10-05_2304`, `2026-10-05_2319` and `2026-10-06_0820` `-openai_gpt-6-luna-generic`: earlier generic runs.
