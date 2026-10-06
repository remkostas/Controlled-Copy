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
python eval/run_eval.py governed --model openai/gpt-6-luna-pro --fallback openai/gpt-6-luna-pro --cases E-07,E-09
python eval/bakeoff.py
```

The governed runner resets the visitor's workspace before every case, adds `corpus-extra/SUP-NOTE-118` for E-13, and builds the card with the context in the case file (HAM-01, warehouse operator, 2026-10-07). Checks per case: result status, cited documents against `expected_sources` and `must_not_use`, a warning about an excluded document when the case expects one, required statement types, every requirement backed by a verified quote from an applicable approved document, undocumented codes reported, forbidden text and forbidden patterns absent (E-13: no paraphrase of the injected instruction), exact quote content.

Since the full audit (EVAL-01) each case also names the actions a correct card must give (`must_say`, for example stop unloading, isolate the area, notify the QA lead and EHS for E-12) and the ones it must not give (`must_not_say`, for example keep unloading, or leave out QA or EHS). They are regular expressions over the statements the card shows, never over the quotes, so a genuine quote next to a wrong instruction fails. A negation just before a required action cancels it; a prohibited action counts unless a negation comes before it in the same clause or the rest of the clause forbids it or makes it conditional ("only after EHS clears the area"). The checks were written from the corpus text and the expected column of the case specification, then run against every stored output only to make sure correct wording passes. `tests/governance/test_eval_card_scorer.py` holds the counterexamples the scorer must reject. These are still word patterns: they catch a missing or reversed instruction, not every wrong one, so each result file keeps every statement, its type, its cited documents and every quote for a human read.

Every check is mechanical: answer or refusal as expected, every displayed quote found verbatim at its offsets in the extracted text, expected pages cited, expected terms present in what the answer says (a term that appears only in a quote does not count). No model judges another model. Whether a quote actually supports the statement next to it is not checked mechanically; every result file keeps the statements and quotes so a person can read them. `tests/unit/test_eval_scorer.py` feeds the scorer wrong answers with genuine quotes and checks that it rejects them. Results are published as measured, misses included; the sets are small, so the numbers are indicative only.

## Which results count

Every result file written since 2026-10-06 records its code version: the commit, whether tracked files had uncommitted changes, and a hash of the case file. Only such results from a clean commit count as evidence. The older files in `results/` are exploratory development runs: their code version was not recorded, and some ran between changes to the cases or the scorer. They stay published for transparency, but they are not evidence for a release. [`results/README.md`](results/README.md) lists which file is which.
