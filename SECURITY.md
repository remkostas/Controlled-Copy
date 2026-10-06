# Security policy

Controlled Copy is a portfolio demonstration that runs on synthetic data. Please do not upload personal or confidential documents to a hosted demo.

## Reporting a vulnerability

Report suspected vulnerabilities privately through GitHub's "Report a vulnerability" (Security tab of this repository) rather than in a public issue. Include the steps to reproduce and what an attacker gains. You can expect an acknowledgement within a few days.

## What is in place

- Anonymous sessions behind a shared access code; every notebook, source, answer and output belongs to one session, and a foreign ID behaves like a missing one.
- CSRF tokens and an Origin check on every state-changing request; a strict Content Security Policy without inline scripts; HSTS, `nosniff` and frame blocking.
- Uploads are typed by content, limited in size, pages and total characters per notebook; PDF text is extracted in a time- and memory-limited child process.
- Every quote in an answer is verified against the source text on the server; text from documents is treated as data, never as instructions.
- Deletion removes the file, chunks, vectors and full-text index entries (SQLite `secure_delete` and FTS5 `secure-delete`) and every answer or output derived from them; sessions not seen for seven days are purged.
- Logs hold IDs, sizes, durations and token counts, never document text, questions or answers.
- Model calls go through OpenRouter with zero-data-retention routing and data collection denied on every request; per-visitor and daily call budgets.
- Dependencies are pinned with hashes, CI actions with commit SHAs; CI scans the history for secrets and the container image for fixable HIGH and CRITICAL vulnerabilities.
- The container runs as a non-root user with a read-only file system, no Linux capabilities and no new privileges; only the reverse proxy publishes ports.

## Known limits

A verified quote proves that the quoted text exists in the source, not that it supports the statement next to it. Prompt injection inside a document can still bias wording within that notebook, but it cannot produce a citation the server cannot verify. See the README for the full list of limitations.
