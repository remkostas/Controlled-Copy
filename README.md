# Controlled Copy

**A NotebookLM-style notebook for controlled documents.**

Ask questions about your own documents. Every statement links to the exact passage it came from, and the server checks each quote against its source before you see it. When your sources do not cover a question, the app says so instead of guessing.

**Try it:** https://controlled-copy.remkostas.com (access code on request)

![Workspace with sources, a cited answer, a follow-up, a refusal and a Studio Briefing](docs/screenshots/app-workspace.png)

Built in four days with AI coding agents, on synthetic data: [how it was built](docs/how-it-was-built.md).

## Two-minute tour

1. Upload a PDF, TXT or Markdown file, click **Summarise the selected sources**, then ask a question and click a citation: the source opens at the passage.
2. Ask a follow-up, then something your sources do not cover: "Not in the selected sources". **New chat** starts over.
3. **Studio:** Summary, Briefing, FAQ or study guide, every point cited. A new output opens large over the chat; copy it, download it or print it. Collapse the Sources panel for more room.
4. **The addition:** open **Inbound Operations**, pick "Short delivery" and build a **Resolution Card**: what the current, approved instructions for this site require, what is missing, and who decides. Old revisions, drafts and other sites' documents are listed as not applied, with the reason.

![A Resolution Card in the reading view: supported by an approved instruction, every requirement cited](docs/screenshots/app-card-supported.png)

## Scope

- **The clone:** notebooks of your own sources, cited chat with follow-ups and refusals, Studio reports, a source viewer, and deletion that also removes every answer built on a deleted source.
- **One addition:** document control. Revision, status, effective date, site and role are data, and fixed rules decide which documents may back an answer before the model writes anything. The core works without it (feature flag).
- **Left out on purpose:** audio and video overviews, mind maps, quizzes, web import, accounts. Answers appear once their quotes are verified, so they do not stream. Details: [design notes](docs/design-notes.md).

## How it works

```mermaid
flowchart TD
    U["Upload: PDF, TXT or Markdown"] --> P["Cut into passages,<br/>each with its exact place"]
    P --> I["Indexed twice:<br/>by words and by meaning"]
    I --> Q
    I --> ST
    I --> C
    Q["Chat: a question"] --> S["Search the passages"]
    C["Resolution Card: a situation"] --> R["Rules first: approved,<br/>in effect, this site and role"]
    R --> S
    S --> F{"Good<br/>match?"}
    F -- no --> N["Not in the sources"]
    F -- yes --> M
    ST["Studio: Summary, Briefing,<br/>FAQ, study guide"] --> SP["Passages from across<br/>each selected source"]
    SP --> M["The model writes statements,<br/>each with a word-for-word quote"]
    M --> V{"Quote found<br/>in its passage?"}
    V -- no --> X["Statement removed"]
    V -- yes --> A["Shown, linked to<br/>the passage"]
    classDef stop fill:#f4f4f5,stroke:#a1a1aa,color:#3f3f46
    classDef done fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef rule fill:#fef3c7,stroke:#d97706,color:#78350f
    class N,X stop
    class A done
    class C,R rule
```

- **Upload:** the text is cut into passages of a few paragraphs, and each passage keeps its exact place in the document, so a citation can open it. Every passage is indexed twice: by its words, for exact terms and codes, and by its meaning (an embedding), for questions in other words.
- **Chat:** a question searches both indexes. If no passage matches well, the answer is "Not in the selected sources" and no model is asked.
- **Studio:** a Summary, Briefing, FAQ or study guide reads passages spread across each selected source.
- **Resolution Card:** fixed rules first pick the documents that count (approved, in effect, this site and role). Only their passages go to the model; the others are listed as not applied, with the reason.
- **Every answer and output:** the model must write statements that each quote a passage word for word. The server looks for every quote in its passage and removes any statement whose quote is not there.

**Under the hood:** one Python service (FastAPI, pages rendered on the server with htmx) and one SQLite database file, on a small server in Germany. The models run through OpenRouter, with zero data retention requested: BGE-M3 for the embeddings, GPT-6 Luna for the answers, and Gemini 3.5 Flash Lite as the fallback. More: [architecture](docs/architecture.md).

## Evidence

- **More than 500 automated tests** with a deterministic fake model, in CI with every optional layer off and on, including browser tests ([where to start](tests/README.md)). Most carry the ID of the test case they implement; the regression tests added during the reviews are named after what they guard.
- **Real model:** 6 of 6 questions on a public 48-page PDF, 13 of 14 Resolution Cards (the miss chose the more cautious status), 11 of 11 reworded cases written before their first run. Scored by code, misses included ([evaluation](eval/README.md)).

## Limitations

- The app verifies that a quote exists in its passage, not that it fully supports the statement next to it.
- No OCR: scanned PDFs contribute no text. The interface is English; answers follow the language of the question.
- The test sets are small, so the numbers are indicative.

## Run it

Python 3.12 or newer and an OpenRouter API key:

```
python -m venv .venv && .venv/bin/pip install --require-hashes -r requirements-dev.lock
cp .env.example .env   # fill in OPENROUTER_API_KEY, APP_ACCESS_CODE, APP_SECRET_KEY
PYTHONPATH=src .venv/bin/uvicorn controlled_copy.app:app --port 8000
PYTHONPATH=src .venv/bin/python -m pytest -m "stage1 and not eval and not smoke_live"   # tests, no key needed
```

Docker Compose with Caddy: [deployment](docs/deployment.md). Browser tests need `playwright install chromium`.

## More

**Read in this order:** [how it was built](docs/how-it-was-built.md) (the approach, one page), then the [design notes](docs/design-notes.md) (ten questions on scope, data and limits). The rest is reference: [decisions](docs/decisions.md), [architecture](docs/architecture.md), [deployment](docs/deployment.md), [testing](docs/testing.md), [evaluation](eval/README.md), [security](SECURITY.md).

Synthetic demo data only; please do not upload personal documents. [Privacy notice](https://controlled-copy.remkostas.com/privacy). Sessions are deleted at log out or seven days after the last visit. Credits: [htmx](https://htmx.org) (0BSD), [IBM Plex](https://github.com/IBM/plex) (OFL 1.1), [Lucide](https://lucide.dev) (ISC); NIST AI 100-1 is downloaded for the evaluation, not redistributed. MIT License.
