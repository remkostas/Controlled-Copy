# Evaluation

Mechanical checks against the real model, run by hand (pytest marker `eval`), never in CI. The application never reads this folder (TC-SEC-006); the runner drives the app through its HTTP interface like any client.

| File | Purpose |
| :--- | :--- |
| `cases_generic.json` | G-01 to G-06: the generic NotebookLM path on one public document |
| `cases_governed.json` | E-01 to E-14: Resolution Cards on the synthetic Inbound Operations workspace (stage 2) |
| `cases_governed_holdout.json` | H-01 to H-11: paraphrases written after the card prompt was tuned on the E-cases, to check that the tuning generalises |
| `sources.json` | Where the public document comes from, its SHA-256 and its licence |
| `client.py` | A small HTTP client for the app (in-process, real model provider) |
| `run_eval.py` | Runs a set and writes `results/<date>-<model>-<set>.md` and `.json` (`-subset` when `--cases` picks some) |
| `bakeoff.py` | Model bake-off: embedding retrieval metrics and generation comparison |
| `corpus-extra/` | Evaluation-only documents (the prompt-injection note) |

The public document (NIST AI 100-1) is downloaded from NIST at run time into `eval/.cache/` (ignored by git) and checked against its SHA-256. It is not redistributed.

Run (needs `OPENROUTER_API_KEY` in `.env`; costs a few cents):

```
python eval/run_eval.py generic
python eval/run_eval.py governed          # stage 2, needs the governed layer's code
python eval/run_eval.py holdout
python eval/run_eval.py governed --model google/gemini-3.5-flash-lite --cases E-07,E-09
python eval/bakeoff.py
```

The governed runner resets the visitor's workspace before every case, adds `corpus-extra/SUP-NOTE-118` for E-13, and builds the card with the context in the case file (HAM-01, warehouse operator, 2026-10-07). Checks per case: result status, cited documents against `expected_sources` and `must_not_use`, a warning about an excluded document when the case expects one, required statement types, every requirement backed by a verified quote, undocumented codes reported, forbidden text absent, exact quote content. Each result file also lists every card item with its type and cited documents, so a reader can judge the misses.

Every check is mechanical: answer or refusal as expected, every displayed quote found verbatim at its offsets in the extracted text, expected pages cited, expected terms present. No model judges another model. Results are published as measured, misses included; the sets are small, so the numbers are indicative only.
