# Evaluation

Real-model checks, run by hand (never in CI; a few cents per run). The runner drives the app through its HTTP interface, like a visitor.

| Set | Cases | What it checks |
| :--- | :--- | :--- |
| Generic | G-01 to G-06 | The NotebookLM path on a public 48-page PDF (NIST AI 100-1): answers, a refusal, citations, a Briefing |
| Resolution Cards | E-01 to E-14 | Situations on the synthetic Inbound Operations workspace |
| Reworded | H-01 to H-11 | Paraphrases written before their first run, so the card prompt was not tuned to them |

Every check is mechanical, no model judging a model: answer or refusal as expected, every quote found word for word in its source, the expected pages and terms, and for cards the status, the documents used and excluded, and the actions a correct card must give and must not give.

## Results on the release

Commit `535a152`, 2026-10-08, GPT-6 Luna with the deployed settings:

| Set | Result | Note |
| :--- | :--- | :--- |
| Generic | 6 of 6 | |
| Resolution Cards | 13 of 14 | E-09 (a damaged delivery without detail) chose "expert confirmation required" instead of "context incomplete": the more cautious status |
| Reworded | 11 of 11 | |

The same question can get a different card from one run to the next; E-09 passed on earlier commits. A pass means the expected sources, quotes and actions are there, not that a person confirmed every statement, and the sets are small, so the numbers are indicative. Each run writes a file with every case, every check, the commit and a hash of the case file; the files of the runs above are kept with [commit `6043168`](https://github.com/remkostas/Controlled-Copy/tree/6043168b0d4a7831c496c1119267f1589769d262/eval/results), and the runs made during development are in the Git history.

## Run it

Needs `OPENROUTER_API_KEY` in `.env`. Results go to `eval/results/` (not committed).

```
python eval/run_eval.py generic
python eval/run_eval.py governed
python eval/run_eval.py holdout
```

The public document is downloaded from NIST at run time, checked against its SHA-256 (`sources.json`) and not redistributed. `corpus-extra/` holds one evaluation-only document (a prompt-injection note for E-13).
