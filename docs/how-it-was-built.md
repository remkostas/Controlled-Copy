# How it was built

Built in four days with AI coding agents. Claude Code implemented it; Codex and separate Claude Code sessions reviewed it. I set the direction, made the decisions, defined the quality gates, tested the product and merged every pull request.

**Monday:** specification and the NotebookLM core. **Tuesday:** the governed-documents layer, model picker and independent reviews. **Wednesday:** deployment and my own test on the live site. **Thursday:** audits and release.

## How I worked

- **Specification before code.** I set the use case (controlled documents, from my warehouse and quality work) and the constraints, and decided scope, limits, retention and models. Claude Code turned that into a specification and a test plan before any code was written.
- **Agents work against gates.** Every change passes the full test suite with a fake model (rules in [AGENTS.md](../AGENTS.md)). As a rule, a fix comes with a test that fails without it.
- **Independent review.** A second agent reviewed each stage before I merged it; where they disagreed, I decided.
- **My own test on the live site** gave issues #2 to #18, all addressed in pull requests with tests.

## Where I overruled the AI

- **Fallback model:** the bake-off favoured Mistral, but its route failed most calls with rate limits. I chose Gemini 3.5 Flash Lite: another provider, about two seconds, cautious when it misses.
- **Retention:** one week instead of the proposed 72 hours, because reviewers come back.
- **Database:** I challenged SQLite. It stayed because every test runs without containers; storage sits behind one module, so Postgres with pgvector is the production path.

## Two bugs and their root causes

1. **A citation opened one page too far on the first click (#4).** The text reflowed while the reading column animated wider. The viewer now re-centres when the column's own animation ends, and the test hovers before it clicks, as a person does.
2. **Uploads failed under daytime load.** A midday probe showed the embedding route answering bursts with HTTP 429. Uploads now retry with growing, randomised waits within a time budget, and say "busy, nothing was stored" if it still fails.

The decisions behind the IDs in commit messages are in [decisions](decisions.md). Commit messages also name review findings by their ID (for example PDA-01); the review reports themselves stay outside the repository.
