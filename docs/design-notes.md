# Design notes

The longer explanations behind the [README](../README.md): everything the app does, a feature-by-feature comparison with NotebookLM, the ten questions the project set out to answer, privacy, and limitations. How the work was done is in [how-it-was-built.md](how-it-was-built.md).

## Everything the app does

- **Sources:** upload PDF, TXT or Markdown, or paste text. Pick which sources a question may use. Open any source in a viewer that shows exactly the text the model saw, including text hidden in the original file.
- **Chat:** ask a question and get short statements with numbered citation chips. A chip opens the source at the highlighted passage. Follow-up questions use the last two turns, and the app shows the standalone search question it built. New chat starts over; an answer still being written when you press it is not kept.
- **Refusal:** a question your sources do not cover gets "Not in the selected sources", with what was searched.
- **Studio:** a short Summary (in short, main topics; also one click from the empty chat), a Briefing (overview, key points, important terms, open questions), an FAQ and a study guide (key concepts, review questions, glossary), in which every item carries a verified citation. Each output type is one JSON template, not a code path. Suggested questions under an empty chat.
- **Deletion:** delete a source or a notebook and everything derived from it disappears: file, chunks, vectors, search index rows, and every answer or output generated from its passages. Log out deletes everything the session added, at once.
- **Resolution Card** (governed layer): describe a situation at the dock and get what the applicable approved instructions require, what information is missing and who decides. Every requirement needs a verified quote from a document that is approved, effective on the chosen date and valid for the chosen site and role. Drafts, obsolete or superseded revisions and other sites' documents are named as "not applied", with the reason. The status (supported, context incomplete, expert confirmation required, conflicting instructions) is chosen by fixed rules: they decide which documents apply, which statements may count and the order of the statuses. Whether two cited passages really conflict, or information is missing, is still the model's reading, and it only counts with verified quotes. Each visitor gets their own copy of a curated "Inbound Operations" workspace and can reset it.
- **Models** (model picker layer): choose which evaluated model writes answers, Studio outputs and cards. Every answer shows the model that wrote it, and "(fallback)" when the fallback model stepped in.
- **Export:** copy any Studio output (Briefing, FAQ, study guide) or Resolution Card as Markdown, or download it, with every verified quote listed under its citation number.
- **Document control:** type a document ID, revision, status, effective date, site and roles when you add a source, instead of writing YAML front matter. The app marks this metadata as asserted by the uploader.

## Compared with NotebookLM

| NotebookLM | Here | Why |
| :--- | :--- | :--- |
| Notebooks of your own sources; pick which sources a question uses | Yes: up to 5 notebooks of 20 sources per visitor | The core interaction |
| Sources: PDF, text, Markdown, pasted text | Yes | |
| Sources: web pages, YouTube, Google Docs and Slides, audio files | No | Each adds a parser or provider surface (web import means server-side requests to arbitrary addresses) without serving the core promise |
| Cited answers; a citation opens the passage | Yes, and the server checks every quote against its passage before you see it | Citations are the promise |
| Follow-up questions | Yes; the app shows the standalone question it searched for | |
| Saying when the sources do not cover a question | Yes: before any answer is generated when nothing relevant is found (only the question is embedded), and when no quote verifies | |
| Answers stream while they are written | No: an answer appears once its quotes are verified | Streaming would show unverified text first |
| Suggested questions | Yes | |
| A short summary of the notebook | Yes: a cited Summary, one click from the chat | NotebookLM shows one when a notebook opens |
| Studio reports: briefing doc, FAQ, study guide | Yes, every item cited; copy or download as Markdown | Each report is one JSON template |
| Audio and Video Overviews, mind maps, quizzes, flashcards | No | Audio and video add a speech provider and one more processor for document content; the learning tools sit outside the controlled-documents use case |
| Notes, sharing, accounts | No: anonymous sessions behind an access code, deleted seven days after the last visit | A demo for strangers; real sign-in is the first item under question 10 |
| Languages | English interface; answers, Studio outputs and cards follow the language of the question, sources or situation | Quotes stay in the language of their source |
| Not in NotebookLM | Document control (revision, status, effective date, site, role), the Resolution Card, a model picker | The use case: which instruction applies, and who decides |

## The ten questions

**1. What problem does it address?** At work, the right instruction often exists, but you have to find which document applies, whether it is the current revision, and whether the answer you were given really comes from it. Generic document chat answers fluently and mixes current and obsolete text without telling you.

**2. Who has the problem?** In the demo, a receiving operator and shift lead at a fictional distribution centre (Kestrova Components GmbH, site HAM-01) who need the current procedure for an exception at the dock. The process owner who maintains those documents owns the problem in real life. The core notebook works for anyone with documents.

**3. Why is ordinary document chat not enough?** It cites loosely or not at all, and it rarely refuses. Controlled Copy answers in statements that each need a quote from a passage that was actually retrieved; the server verifies the quote and drops any statement whose quote it cannot find. If nothing survives, you get a refusal.

**4. What did I prioritise?** A complete, recognisable NotebookLM core first: three panels (Sources, Chat, Studio), verified citations, follow-ups, refusal, cited Studio outputs (Briefing, FAQ, study guide), and real deletion. Stage 2 adds document control: revision, status, effective date and site as metadata, a split into authoritative and excluded documents, and a Resolution Card that separates requirements from inferences and recommendations.

**5. What alternatives did I consider?** A pure clone, a draft checker, and a process-brief generator. For the stack, Streamlit and a Next.js front end lost to one FastAPI service with server-rendered HTML and htmx: one process, one language, full control over the layout. PostgreSQL with pgvector lost to SQLite for a single-node demo; the storage code sits behind one module, so pgvector stays the production path.

**6. What did I leave out on purpose?** Audio and video overviews, quizzes, mind maps, accounts and sharing, OCR, web import and DOCX. Each one adds parser or provider surface without serving the core promise.

**7. What data leaves the system?** Chunk text goes once to the embedding model at upload. For each question, the question and the top six passages go to the generation model. Both go through OpenRouter with zero-data-retention routing and data collection denied on every request. Vectors, files and chats stay in the app's SQLite file. Logs hold IDs, sizes, durations and token counts, never document text, questions or answers; a test checks this with a canary string.

**8. How does it handle unsupported information?** In three layers. Retrieval refuses before any answer is generated when the best match is weaker than an evidence floor (only the question itself is embedded for the comparison; exact codes such as `GR-204` bypass the floor). The model must return statements with quotes in a fixed JSON schema. The server then checks every quote against its passage and removes what fails, so an answer the model invented cannot reach you with a citation attached.

**9. How did I evaluate it?** With mechanical checks only, no model judging another model, on three case sets: six questions on a public 48-page PDF (NIST AI 100-1), 14 Resolution Card situations on the curated workspace, and 11 reworded situations written before their first run. On the release, 6 of 6, 13 of 14 and 11 of 11; the one miss chose the more cautious status. The models were chosen the same way: the embedding model by retrieval hit rates, the main and fallback generation models and the picker's list by the card sets. A pass means the expected sources, quotes and actions are there, not that a person confirmed every statement; the sets are small. Details: [`eval/README.md`](../eval/README.md).

**10. What would production need?** Real sign-in instead of a shared access code, row-level isolation for a shared company workspace, a data processing agreement with every processor and EU-only model routing, document status coming from a real document-control system instead of uploaded front matter, a sandboxed parsing service with malware scanning, encryption at rest with deletion that reaches backups, monitoring, and a review with the works council and the data protection officer before any pilot. From my own test of the demo, the next product steps would be: a Studio output opened over the chat, with follow-up questions on a card; a chat history with several chats per notebook; and a site and role filter for the whole workspace instead of per card.

## Privacy and security

- Synthetic demo data only. The landing page asks visitors not to upload personal or confidential documents.
- Each visitor gets an anonymous session; all data belongs to that session, and a foreign ID behaves like a missing one. Sessions not seen for seven days are deleted with everything in them.
- Processors: the host and OpenRouter with the model providers it routes to. EU in-region routing needs an OpenRouter business plan, so the demo does not claim it.
- I make no compliance claims. The design follows data-protection principles (minimal data, purpose limitation, deletion that works), and a production deployment would need the legal review listed under question 10.

## Limitations

A quote can exist in a passage and still not support the statement next to it; the app verifies existence, not support. Prompt injection inside a document can still bias wording within that notebook, although it cannot produce a citation the server cannot verify. There is no OCR, so scanned PDFs show a warning and contribute no text. The interface is in English; answers, Studio outputs and Resolution Cards follow the language of the question, sources or situation (German was checked), and quotes stay in the language of their source. A question in one language about documents in another matches more weakly and is refused sooner (seen with an English question about a German document).
