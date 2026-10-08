# Decisions

The decision log behind Controlled Copy, shortened for readers outside the project. Commit messages cite these IDs. The full log, with options, trade-offs and "revisit if" notes, is kept privately; it also holds notes that do not belong in a public repository.

**Who decided:**

- **Remko:** his choice, often after Claude Code laid out the options.
- **Remko, after a challenge:** one side questioned the other's proposal before it was settled.
- **Recommended, then accepted:** built as Claude Code recommended in the specification and accepted when Remko reviewed and merged that stage.
- **Delegated:** Remko asked Claude Code to decide. The choice was logged for his review.

| ID | Date (2026-10) | Decision | Why | Who decided |
| :--- | :--- | :--- | :--- | :--- |
| D-001 | 05 | Work under a codename until the scope is clear; the name follows the product. Final name: Controlled Copy | "SourceFrame", the first candidate, was too close to an existing product | Remko |
| D-003 | 05 | A NotebookLM clone first, with a light governed-documents layer second | The assignment asks for a clone; one layer on top shows where cited answers matter most at work: documents that must be current and approved | Remko |
| D-004 | 05 | Demo persona: a warehouse operator asking about controlled instructions; the generic core serves anyone | A concrete person makes the problem clear quickly and gives objective test cases | Recommended, then accepted |
| D-005, D-006 | 05 | Core workflow and scope for Friday: text only, no audio or video | Everything in scope either completes the NotebookLM core or serves the governed layer | Remko (text only); the rest recommended, then accepted |
| D-007, D-015, D-027 | 05 | Embeddings and generation through OpenRouter, zero-data-retention routing, `data_collection: deny`. Embedding model BGE-M3 | One provider and one key; no model download; small server. The privacy cost (text goes to the provider) is disclosed | Remko |
| D-008, D-020 | 05 | Every statement needs a word-for-word quote that code finds in the cited passage. Statements are typed: Requirement, Inference, Recommendation, Missing evidence | Deterministic and explainable; a confidence score would look precise without being so | Recommended, then accepted |
| D-009 | 05 | Hybrid retrieval: full-text search plus vectors, combined by rank fusion, with section-aware chunks | Error codes and document numbers need exact matching | Recommended, then accepted |
| D-010 | 05 | File types: PDF, TXT, Markdown (with front matter for document control) and pasted text | Few parsers keep the attack surface small | Recommended, then accepted |
| D-011 | 05 | An access code on a landing page, one private space per browser session, no accounts | Blocks abuse and cost, keeps reviewers apart, collects no personal data | Delegated |
| D-012 | 05 | Host on a small separate server (Hetzner) | The app parses untrusted uploads; on its own server that parser touches nothing else | Remko, on Claude Code's recommendation |
| D-013, D-014 | 05 | One service: FastAPI renders the pages with htmx, SQLite inside, Docker Compose with Caddy | Easiest to understand, explain and demo; deletion and isolation are provable in one place | Remko |
| D-016 | 05 | Evaluation scored mechanically: statuses, cited documents, quote validity, statement types. No model judges the model | Repeatable and honest | Recommended, then accepted |
| D-017, D-024 | 05 | Demo documents are synthetic, from a fictional company, Kestrova Components GmbH, with designed traps (obsolete, draft, other site, conflict, prompt injection) | No licence questions; traps are only possible with our own documents; a fictional name avoids looking like a real company's papers | Recommended, then accepted |
| D-018 | 05 | Private repository until delivery; MIT licence; Remko makes the merges | No half-finished work or accidental leaks in public | Recommended, then accepted |
| D-019 | 05 | Product and repository in English (amended by D-049) | One language to build and test | Remko |
| D-021 | 05 | Document control is data: revision, status, effective date, site, role. Rules, not the model, decide which documents may be used | Testable without a model | Recommended, then accepted |
| D-022 | 05 | The video in English, self-recorded, lightly edited; the live test uncut. Hosted on the app's own `/video` page | A clear English explanation; hosting under our control | Remko |
| D-023 | 05 | Clone-first weighting: Journey A (the NotebookLM core) gets the first build day and the polish; the layer stays small | The e-mail says "clone" twice and asks to test the clone live | Remko |
| D-026 | 05 | Deploy by pulling `main` on the server, by hand, only after the product works completely in local testing | No registry, no CI secret, every deploy a deliberate step | Remko |
| D-028 | 05 | Each visitor gets a private copy of the curated workspace. Remko's idea of one shared workspace with roles and a profile switcher was narrowed to this | Reviewers would see each other's changes in a shared space; the core must never get worse (Remko's condition) | Remko proposed it and asked to be challenged; the design was delegated |
| D-029 | 05 | Git workflow: branches per stage, PRs that Remko merges, no pushes to `main`, AI co-author trailers | The history becomes a development trail; every merge is a visible human decision | Delegated |
| D-030 | 05 | Codex reviews independently and read-only; Claude Code fixes or answers each finding; Remko decides | One agent builds, another challenges, a person decides | Remko |
| D-031 | 05 | Visual identity: industrial but light. Graphite bars, steel-grey surfaces, one amber accent, paper-white reading panels | Distinct from Google's look while keeping NotebookLM's structure. Remko first asked for a darker look, then for "not too dark" | Remko |
| D-032 | 05 | Every stage can be switched off by a flag and removed by a revert; the core never imports a layer | If the governed layer turns out to be a bad idea, it must come out cleanly | Remko |
| D-033 | 05 | SQLite, with storage behind one module so PostgreSQL with pgvector stays the production path | Remko challenged SQLite from his Postgres experience. It stayed because the build agent could run its integration tests without containers | Remko, after a challenge |
| D-034 | 05 | Models from a measured bake-off: BGE-M3 embeddings, GPT-6 Luna generation, evidence floor 0.52 | Best mean reciprocal rank for retrieval; the only generation model correct on all six cases, and the cheapest | Remko, from measurements |
| D-035 | 05 | Public test document: NIST AI 100-1, downloaded at run time and pinned by hash, never committed. An answer that cites a deleted source is removed with it | Public domain in the US; no redistribution | Recommended, then accepted |
| D-036, D-039 | 06 | Uploaded Markdown front matter counts as document control, marked "asserted by uploader". In the curated workspace an upload can never count as a controlled document | Reviewers can try their own controlled documents; the audit showed an upload could otherwise steer a card | Remko |
| D-037 | 06 | Card changes after the first real-model run (5 of 14 passed): general rules only, nothing keyed to a test case | Fixing the cases one by one would be tuning to the test | Recommended, then accepted |
| D-038, D-040 | 06 | No Mistral anywhere. Fallback model Gemini 3.5 Flash Lite | Remko does not use Mistral in his own environment; the measured Mistral route also failed most calls with rate limits | Remko, overruling the first recommendation |
| D-041, D-042 | 06 | Stage 3: a model picker as a third layer (allowlist, price caps on every request), Copy as Markdown, and a document-control form for uploads | Remko asked for them; the picker stays switchable like the governed layer | Remko asked; the design was delegated |
| D-043 | 06 | Dependencies hash-locked and current; CI builds the image, starts the stack behind Caddy, and scans it | Remko asked for production readiness | Delegated |
| D-044 to D-047 | 06 | Every review finding fixed on the branch it belongs to and merged forward. Spending is reserved at its worst case before each paid call | A public demo on one paid key must not overspend under parallel calls, retries or timeouts | Remko on the price cap; details delegated |
| D-048 | 07 | No audio, video, mind maps, quizzes or flashcards. FAQ and study guide added as two template files | Audio adds a provider, cost and risk two days before delivery, and does not serve the use case | Recommended, then kept by Remko |
| D-049 | 07 | Answers follow the language of the question; German words are searchable. Interface and repository stay English | The reviewers work in German and may use German documents | Recommended, then kept by Remko |
| D-050 | 07 | Make the repository easy and honest to check for people and AI agents alike, without tuning anything to a metric | "So we can see how you work" | Delegated, from Remko's request |
| D-052 | 07 | Repository public at delivery; site at `controlled-copy.remkostas.com` | | Remko |
| D-053 | 07 | Manual system test first; every real finding becomes a GitHub issue; fixes as small PRs from `main`, one concern each, with `Fixes #N` | The normal way a team handles findings, and a visible trail | Remko |
