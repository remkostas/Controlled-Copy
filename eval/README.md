# Evaluation

Mechanical checks against the real model, run by hand (pytest marker `eval`), never in CI. The application never reads this folder (TC-SEC-006); the runner drives the app through its HTTP interface like any client.

| File | Purpose |
| :--- | :--- |
| `cases_generic.json` | G-01 to G-06: the generic NotebookLM path on one public document |
| `sources.json` | Where the public document comes from, its SHA-256 and its licence |
| `client.py` | A small HTTP client for the app (in-process, real model provider) |
| `run_eval.py` | Runs the cases and writes `results/<date>-<model>-<set>.md` and `.json` |
| `bakeoff.py` | Model bake-off: embedding retrieval metrics and generation comparison |
| `corpus-extra/` | Evaluation-only documents (the prompt-injection note) |

The public document (NIST AI 100-1) is downloaded from NIST at run time into `eval/.cache/` (ignored by git) and checked against its SHA-256. It is not redistributed.

Run (needs `OPENROUTER_API_KEY` in `.env`; costs a few cents):

```
python eval/run_eval.py generic
python eval/bakeoff.py
```

Every check is mechanical: answer or refusal as expected, every displayed quote found verbatim at its offsets in the extracted text, expected pages cited, expected terms present in what the answer says (a term that appears only in a quote does not count). No model judges another model. Whether a quote actually supports the statement next to it is not checked mechanically; every result file keeps the statements and quotes so a person can read them. `tests/unit/test_eval_scorer.py` feeds the scorer wrong answers with genuine quotes and checks that it rejects them. Results are published as measured, misses included; the sets are small, so the numbers are indicative only.

## Which results count

Every result file written since 2026-10-06 records its code version: the commit, whether tracked files had uncommitted changes, and a hash of the case file. Only such results from a clean commit count as evidence. The older files in `results/` are exploratory development runs: their code version was not recorded, and some ran between changes to the cases or the scorer. They stay published for transparency, but they are not evidence for a release. [`results/README.md`](results/README.md) lists which file is which.
