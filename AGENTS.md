# Rules for coding agents in this repository

These are the rules Claude Code (the builder) and the reviewers (Codex and separate Claude sessions) worked under while Controlled Copy was built. A new agent should follow them too. How they were used is described in [docs/how-it-was-built.md](docs/how-it-was-built.md).

## Roles

- **Remko** owns the product: scope, decisions, the manual system test, and every merge into `main`.
- **The builder** implements against the specification and test plan, runs the gates, audits its own work at each milestone, and fixes review findings.
- **Reviewers** read only. They pin the commit they review, run the gates themselves, write findings with severity and evidence, and never edit code, push or merge.

## Git

- Never push to `main`, never force-push, never rewrite pushed history. Every change reaches `main` through a pull request that Remko merges, with a merge commit.
- One concern per branch and per pull request. Fixes from the manual test are small PRs from `main` that say `Fixes #N`.
- Commits are authored as Remko's GitHub no-reply address and end with a `Co-Authored-By` trailer naming the AI tool, so the AI's part stays visible.
- Do not change repository settings or visibility.

## Stages and reversibility

- The NotebookLM core (Stage 1) must work on its own and must never get worse because of a later layer.
- Each extension is a layer behind a flag: `FEATURE_GOVERNANCE` (the governed-documents workspace and Resolution Card) and `FEATURE_MODEL_PICKER`. The core never imports a layer; the layer registers itself.
- Database migrations are additive only, so a layer can be switched off without a data change.
- CI proves this: the core suite runs with every layer off, and the full suite runs with the layers on.

## Gates (run before every commit that changes code)

```bash
# every layer off
PYTHONPATH=src python -m pytest -m "(stage1 or stage2 or stage3) and not eval and not smoke_live" -q
# every layer on
FEATURE_GOVERNANCE=true FEATURE_MODEL_PICKER=true PYTHONPATH=src python -m pytest -m "(stage1 or stage2 or stage3) and not eval and not smoke_live" -q
ruff check src tests && ruff format --check src tests
```

- A fix comes with a test that fails without it. Check that by reverting the fix, not by assuming.
- Tests use the fake model provider (`providers/fake.py`). No test calls a paid model; the live smoke tests (`-m smoke_live`) run only on request.
- Requirements have IDs in `docs/testing.md`. A test for a requirement carries its test-case ID in its name; regression tests from reviews may not have one (see [tests/README.md](tests/README.md)).

## Evaluation

- The app never reads `eval/`. Evaluation cases are scored mechanically (statuses, cited documents, verified quotes, required and forbidden actions); no model judges the model.
- Never tune the app to a case. Held-out cases are committed before their first run.
- Every published number names its result file and the commit it ran on, misses included. Do not promote a better older run as current.

## Secrets and data

- Never print, read or copy `.env` or any secrets file. The app loads them at runtime.
- No personal data in the repository, the demo corpus or the logs. Logs carry events and counts, never document or question text.
- The demo company and documents are fictional.

## Writing

- Plain English, short sentences, no em dashes.
- Commit messages say what changed and why, in words a reader outside the project can follow. When a review finding is the reason, name it once (for example "pre-delivery audit PDA-03"); [docs/reviews.md](docs/reviews.md) explains the IDs.
