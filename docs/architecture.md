# Architecture

## ADR-001: Module layout and the plugin registration point

**Status:** Accepted (by default during the overnight build, for review)
**Date:** 2026-10-05

### Context

The product is a NotebookLM-style notebook (the core) with an optional governed-documents layer added in a later stage. The core must keep working, unchanged, when the layer is switched off or removed. The whole service is one FastAPI process with a SQLite file, rendered HTML and htmx, and a model provider behind an adapter.

### Decision

One Python package, `controlled_copy`, with the core modules at the top level and each optional layer in its own subpackage:

```
controlled_copy/
  config.py       settings from environment variables (.env locally)
  app.py          create_app(): wiring, middleware, routers, plugin loading
  plugins.py      the registration point: what a plugin may add
  storage/        SQLite connection, migrations, scoped data access
  ingestion/      validation, extraction (PDF in a time-limited subprocess), front matter, chunking
  retrieval/      full-text search, vector search, rank fusion, evidence floor
  answering/      prompts, quote verification, answers, follow-up rewriting
  studio/         template engine; templates are JSON data files
  providers/      model provider interface, OpenRouter adapter, fake provider for tests
  web/            routes, security (session, CSRF, headers), templates, static files
  governance/     stage 2 layer (only imported by name when FEATURE_GOVERNANCE is on)
```

A plugin is a module with a `register(registry)` function. `app.py` imports it by name through `importlib` only when its feature flag is on. Through the registry a plugin can add: routers, database migrations (additive only), Studio actions, top-bar, chat and upload partials, output renderers (HTML and Markdown), template folders, notebook kinds, workspace and view hooks, and a model resolver that picks the visitor's generation model for a request. The core never imports a plugin module; a unit test scans the core for imports of every package listed in `plugins.LAYERS`, and a fresh interpreter checks that no layer module is loaded when every flag is off.

Two layers exist: `governance` (stage 2, `FEATURE_GOVERNANCE`: the Inbound Operations workspace, document-control rules and the Resolution Card) and `models` (stage 3, `FEATURE_MODEL_PICKER`: a per-session choice from the `MODEL_CHOICES` allowlist, stored in an additive `model_choice` table and applied through the model resolver; the configured fallback stays automatic).

### Options considered

| Option | Complexity | Reversibility | Notes |
| :--- | :--- | :--- | :--- |
| A. One package, layer in a subpackage, registry and flag (chosen) | Low | High: flag off in seconds, subpackage removable | One place to read the wiring |
| B. Separate distributions (core and layer as two packages) | Medium | High | Two build artefacts and version pinning for a one-week demo |
| C. Layer code mixed into core modules behind `if` checks | Low at first | Low | Every core change risks the layer and the reverse |

### Consequences

- Turning the layer off is a configuration change; the core test suite runs with the flag off on every pull request (TC-REV-001).
- Layer migrations only add tables or nullable columns, so a stage 1 database keeps working after stage 2 migrations (TC-REV-002).
- The registry is a small, explicit surface. Anything a plugin needs that it does not offer becomes a visible change to `plugins.py`.

## Request path for a question

```
browser ──htmx POST /notebooks/{id}/ask──> FastAPI route (session + CSRF checked)
  1. follow-up?  last two turns + question ──model──> standalone search question
  2. retrieval:  FTS5 top 20  +  vector top 20 (exact cosine, numpy)  ──RRF──> top 6
  3. evidence floor: weak best match and no exact identifier hit ──> refusal, no model call
  4. answer:     question + 6 delimited passages ──model, JSON schema──> statements + quotes
  5. verify:     every quote must occur in its cited passage (normalised); failed citations removed
  6. render:     statements with numbered citation chips, or the refusal
```

## Data

SQLite in WAL mode with foreign keys on and `secure_delete` on, so deleted rows are overwritten. Every row hangs off a visitor session: session → notebook → source → chunk → vector and full-text row. Deleting any parent removes its children in one transaction; a trigger keeps the FTS5 index in step with the chunk table. Vectors are float32 blobs; search is exact (a few thousand chunks per notebook at most).

## Security boundaries

- Browser to app: access code, signed session cookie, CSRF token on every state-changing request, strict Content Security Policy (no inline script, no third-party origins), escaped output everywhere.
- App to model provider: only chunk text (embeddings, once at upload) and the question with the top passages (generation). Requests ask OpenRouter for zero-data-retention endpoints and no data collection.
- Uploaded files: type decided by content, size and page limits, PDF parsing in a separate process with a time and memory limit.
- Logs: IDs, sizes, durations, token counts and status only. Never document text, questions or answers.
