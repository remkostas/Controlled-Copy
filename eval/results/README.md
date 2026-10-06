# Results

Each run writes a `.json` file (every case, every check) and a `.md` summary. A file counts as evidence only when its `provenance` block names a commit with `"dirty": false`: that commit's code and case file (by hash) produced it.

## Versioned

| File | Code | Cases | Result | Note |
| :--- | :--- | :--- | :--- | :--- |
| `2026-10-06_155000-openai_gpt-6-luna-governed` | `653188c`, clean | `c3327bfb4a93f2dd` | 14 of 14 | Stage 3 code, action checks as revised after the re-check (RCK-02) |
| `2026-10-06_155231-openai_gpt-6-luna-holdout` | `653188c`, clean | `d734949bd05c8858` | 11 of 11 | Stage 3 code, action checks as revised after the re-check (RCK-02) |
| `2026-10-06_153902-openai_gpt-6-luna-governed` | `06f20cf`, clean | `c3327bfb4a93f2dd` | 13 of 14 | Stage 2 code, action checks as revised after the re-check (RCK-02). E-09: expert confirmation instead of context incomplete (no requirement, one missing-information item) |
| `2026-10-06_154144-openai_gpt-6-luna-holdout` | `06f20cf`, clean | `d734949bd05c8858` | 11 of 11 | Stage 2 code, action checks as revised after the re-check (RCK-02) |
| `2026-10-06_133647-openai_gpt-6-luna-governed` | `f396aa7`, clean | `98e1fc14eb86bcde` | 12 of 14 | Stage 3 code, first version of the action checks. E-09: expert confirmation instead of context incomplete; E-12: context incomplete instead of supported (it asked whether the product inside is intact), with every required action given |
| `2026-10-06_133907-openai_gpt-6-luna-holdout` | `f396aa7`, clean | `ad8ed053143a4c64` | 11 of 11 | Stage 3 code, first version of the action checks |
| `2026-10-06_132816-openai_gpt-6-luna-governed` | `f6da0bd`, clean | `98e1fc14eb86bcde` | 14 of 14 | Stage 2 code, first version of the action checks (EVAL-01) |
| `2026-10-06_133025-openai_gpt-6-luna-holdout` | `f6da0bd`, clean | `ad8ed053143a4c64` | 11 of 11 | Stage 2 code, first version of the action checks (EVAL-01) |
| `2026-10-06_110327-openai_gpt-6-luna-governed` | `357b1fb`, clean | `55057b723f0caf8a` | 14 of 14 | Before the action checks |
| `2026-10-06_110517-openai_gpt-6-luna-holdout` | `357b1fb`, clean | `a9453aeccf8a7b46` | 11 of 11 | Before the action checks |
| `2026-10-06_1316-openai_gpt-6-luna-generic` | `d82528a`, clean | `26cfa0915630d06d` | 6 of 6 | Current scorer: terms counted only in the statements; statements and quotes kept |
| `2026-10-06_1302-openai_gpt-6-luna-generic` | `3d4c88e`, clean | `26cfa0915630d06d` | 6 of 6 | Scored before the scorer stopped counting terms that appear only in quotes (EVAL-01) |

Second re-check of the full-audit fixes (2026-10-06, evening): the action checks were revised again (a negation counts only in the action's own part of the sentence; more words for the same actions). Re-scoring the stored statements of all 255 cards in this folder with the revised checks changes no verdict, so every number above also stands under the current checks.

## Exploratory (code version not recorded)

These runs happened during development, before result files recorded their code version. Some ran between changes to the cases, the prompts or the scorer, so they cannot be reproduced exactly. All governed and held-out runs here also predate the action checks (`must_say`, `must_not_say`). They stay here as a record of what was measured at the time, misses included, not as release evidence.

- `2026-10-05_2218-bakeoff`, `2026-10-06_0610-bakeoff`: the embedding and generation model comparisons.
- `2026-10-05_2224`, `2026-10-05_2226`, `2026-10-05_2304`, `2026-10-05_2319` and `2026-10-06_0820` `-openai_gpt-6-luna-generic`: earlier generic runs.
- Every `-governed`, `-governed-subset`, `-holdout` and `-holdout-subset` file dated 2026-10-05 or 2026-10-06 up to 10:12 UTC: Resolution Card runs while the card prompt and the cases were tuned, the fallback comparison (Gemini 3.5 Flash Lite, Gemini 3.8 Flash, Claude Haiku 4.5, GPT-6 Luna Pro) and the model picker comparison (GPT-6 Sol, Gemini 3.7 Flash, Claude Sonnet 5.5, GLM 5.2 and 5.1, DeepSeek V4 Pro and V4.1 Flash, Qwen 3.5 397B, Grok 4.7, Kimi K2.6). The `openai_no-such-model-smoke` files check that an unknown model fails cleanly; they are not quality results.

Re-scored offline with the action checks (the stored statements, not new model calls), the exploratory outputs show these extra misses: Gemini 3.5 Flash Lite (the fallback) and one early GPT-6 Luna run answer the barcode cases (E-05, H-07) with "do not type it in" but never say that the shift lead does it; DeepSeek V4.1 Flash gives the WMS key user for E-03 only as a recommendation, not as a requirement. No stored output was re-scored from failing to passing.
