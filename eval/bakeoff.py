"""Model bake-off (test plan section 4). Real model calls; costs a few cents.

1. Embeddings: retrieval quality on the labelled G and E questions (hit@3, hit@5,
   mean reciprocal rank), dense only and hybrid (FTS5 + dense, rank fusion), plus
   the best-match cosine of answerable versus off-topic questions, which sets the
   evidence floor.
2. Generation: the same retrieved passages sent to each candidate model on six
   cases: schema validity, quote validity, outcome, latency and cost per answer.

Usage: python eval/bakeoff.py [--skip-generation] [--skip-embeddings]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from client import EVAL, ROOT, eval_settings, fetch_document, provenance, provenance_line
from controlled_copy.answering import prompts
from controlled_copy.answering.answer import AnswerOut
from controlled_copy.answering.citations import CitationNumbering, verify_statements
from controlled_copy.answering.generate import parse_payload
from controlled_copy.ingestion.frontmatter import split_front_matter
from controlled_copy.ingestion.pipeline import embedding_input, extract_upload
from controlled_copy.providers.base import ProviderError
from controlled_copy.providers.openrouter import OpenRouterProvider
from controlled_copy.retrieval.search import Passage, fts_query, rrf

EMBEDDING_MODELS = ["baai/bge-m3", "qwen/qwen3-embedding-8b", "openai/text-embedding-3-small"]
GENERATION_MODELS = ["openai/gpt-6-luna", "openai/gpt-6-luna-pro", "google/gemini-3.5-flash-lite"]
GENERATION_CASES = ["G-01", "G-02", "G-03", "G-04", "G-05", "E-14"]


@dataclass
class DocChunk:
    corpus: str
    doc_label: str
    title: str
    locator: str
    page: int | None
    start: int
    end: int
    text: str
    metadata: dict[str, Any] | None


def load_corpora() -> list[DocChunk]:
    chunks: list[DocChunk] = []
    name, data = fetch_document("nist-ai-rmf")
    extracted = extract_upload(name, data, max_pages=150, timeout=60, memory_mb=1024, title_limit=200)
    for c in extracted.chunks:
        chunks.append(
            DocChunk(
                "nist",
                "NIST AI 100-1",
                extracted.title,
                c.locator,
                c.page,
                c.char_start,
                c.char_end,
                c.text,
                None,
            )
        )
    files = sorted((ROOT / "demo-data" / "inbound-operations").glob("*.md")) + [
        ROOT / "eval" / "corpus-extra" / "SUP-NOTE-118_supplier-delivery-advice.md"
    ]
    for path in files:
        extracted = extract_upload(
            path.name, path.read_bytes(), max_pages=150, timeout=60, memory_mb=1024, title_limit=200
        )
        meta, _, _ = split_front_matter(path.read_text())
        label = f"{meta['document_id']} rev {meta['revision']}" if meta else "SUP-NOTE-118"
        for c in extracted.chunks:
            chunks.append(
                DocChunk(
                    "ops", label, extracted.title, c.locator, c.page, c.char_start, c.char_end, c.text, meta
                )
            )
    return chunks


def queries() -> list[dict[str, Any]]:
    out = []
    for case in json.loads((EVAL / "cases_generic.json").read_text())["cases"]:
        if case["question"]:
            out.append(
                {
                    "id": case["case_id"],
                    "corpus": "nist",
                    "text": case["question"],
                    "pages": case["expected_pages"],
                    "docs": [],
                    "negative": case["kind"] == "refusal",
                }
            )
    for case in json.loads((EVAL / "cases_governed.json").read_text())["cases"]:
        out.append(
            {
                "id": case["case_id"],
                "corpus": "ops",
                "text": case["situation"],
                "pages": [],
                "docs": case["expected_sources"],
                "negative": case["expected_status"] == ["refusal"],
            }
        )
    return out


def relevant(query: dict[str, Any], chunk: DocChunk) -> bool:
    if chunk.corpus != query["corpus"]:
        return False
    if query["pages"]:
        return chunk.page in query["pages"]
    return chunk.doc_label in query["docs"]


def fts_rankings(chunks: list[DocChunk]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE f USING fts5(body, corpus UNINDEXED, tokenize = 'porter unicode61')")
    conn.executemany(
        "INSERT INTO f(rowid, body, corpus) VALUES (?, ?, ?)",
        [(i, f"{c.locator}\n{c.text}", c.corpus) for i, c in enumerate(chunks)],
    )
    return conn


def embed_all(provider: OpenRouterProvider, model: str, texts: list[str]) -> np.ndarray:
    vectors = []
    for i in range(0, len(texts), 64):
        vectors.extend(provider.embed(texts[i : i + 64], model=model).vectors)
    matrix = np.asarray(vectors, dtype=np.float32)
    return matrix / np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-9)


def metrics(ranked: list[int], query: dict[str, Any], chunks: list[DocChunk]) -> tuple[bool, bool, float]:
    first = next(
        (rank for rank, idx in enumerate(ranked[:10], start=1) if relevant(query, chunks[idx])), None
    )
    return (first is not None and first <= 3, first is not None and first <= 5, 1.0 / first if first else 0.0)


def embedding_bakeoff(
    provider: OpenRouterProvider, chunks: list[DocChunk]
) -> tuple[dict[str, Any], dict[str, Any]]:
    fts = fts_rankings(chunks)
    qs = queries()
    report: dict[str, Any] = {}
    cosines: dict[str, Any] = {}
    for model in EMBEDDING_MODELS:
        started = time.monotonic()
        try:
            doc_matrix = embed_all(provider, model, [embedding_input(c.title, c) for c in chunks])  # type: ignore[arg-type]
            query_matrix = embed_all(provider, model, [q["text"] for q in qs])
        except ProviderError as exc:
            report[model] = {"error": str(exc)}
            continue
        rows = {"dense": [], "hybrid": []}
        best: dict[str, float] = {}
        for qi, query in enumerate(qs):
            mask = np.array([c.corpus == query["corpus"] for c in chunks])
            scores = doc_matrix @ query_matrix[qi]
            scores[~mask] = -1
            dense = [int(i) for i in np.argsort(-scores)[:20]]
            best[query["id"]] = float(scores[dense[0]])
            match = fts_query(query["text"])
            lexical = (
                [
                    r[0]
                    for r in fts.execute(
                        "SELECT rowid FROM f WHERE f MATCH ? AND corpus = ? ORDER BY bm25(f) LIMIT 20",
                        (match, query["corpus"]),
                    )
                ]
                if match
                else []
            )
            hybrid = [i for i, _ in rrf([lexical, dense])]
            if not query["negative"] and (query["pages"] or query["docs"]):
                rows["dense"].append(metrics(dense, query, chunks))
                rows["hybrid"].append(metrics(hybrid, query, chunks))
        summary = {}
        for kind, values in rows.items():
            n = len(values)
            summary[kind] = {
                "n": n,
                "hit@3": round(sum(v[0] for v in values) / n, 3),
                "hit@5": round(sum(v[1] for v in values) / n, 3),
                "mrr": round(sum(v[2] for v in values) / n, 3),
            }
        summary["seconds"] = round(time.monotonic() - started, 1)
        report[model] = summary
        cosines[model] = {q["id"]: {"best": round(best[q["id"]], 3), "negative": q["negative"]} for q in qs}
    return report, cosines


def generation_bakeoff(provider: OpenRouterProvider, chunks: list[DocChunk]) -> dict[str, Any]:
    qs = {q["id"]: q for q in queries()}
    generic = {c["case_id"]: c for c in json.loads((EVAL / "cases_generic.json").read_text())["cases"]}
    governed = {c["case_id"]: c for c in json.loads((EVAL / "cases_governed.json").read_text())["cases"]}
    fts = fts_rankings(chunks)
    texts = [embedding_input(c.title, c) for c in chunks]  # type: ignore[arg-type]
    doc_matrix = embed_all(provider, "baai/bge-m3", texts)
    results: dict[str, Any] = {m: [] for m in GENERATION_MODELS}
    for case_id in GENERATION_CASES:
        query = qs[case_id]
        q_vec = embed_all(provider, "baai/bge-m3", [query["text"]])[0]
        mask = np.array([c.corpus == query["corpus"] for c in chunks])
        scores = doc_matrix @ q_vec
        scores[~mask] = -1
        dense = [int(i) for i in np.argsort(-scores)[:20]]
        match = fts_query(query["text"])
        lexical = (
            [
                r[0]
                for r in fts.execute(
                    "SELECT rowid FROM f WHERE f MATCH ? AND corpus = ? ORDER BY bm25(f) LIMIT 20",
                    (match, query["corpus"]),
                )
            ]
            if match
            else []
        )
        top = [i for i, _ in rrf([lexical, dense])][:6]
        passages = [
            Passage(
                i,
                chunks[i].doc_label,
                chunks[i].title,
                "md",
                chunks[i].locator,
                chunks[i].page,
                0,
                len(chunks[i].text),
                chunks[i].text,
                chunks[i].metadata,
                "none",
                float(scores[i]),
                0.0,
            )
            for i in top
        ]
        messages, mapping = prompts.answer_messages(query["text"], passages)
        case = generic.get(case_id) or governed.get(case_id)
        keywords = case.get("keywords", [])
        must = case.get("quote_must_contain")
        negative = query["negative"]
        for model in GENERATION_MODELS:
            started = time.monotonic()
            record: dict[str, Any] = {"case": case_id}
            try:
                result = provider.chat_json(
                    messages, schema=prompts.ANSWER_SCHEMA, schema_name="answer", model=model, timeout=60
                )
            except ProviderError as exc:
                record.update(error=str(exc), seconds=round(time.monotonic() - started, 1))
                results[model].append(record)
                continue
            record.update(
                seconds=round(time.monotonic() - started, 1),
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                provider=result.provider,
            )
            try:
                payload = parse_payload(result.content, AnswerOut)
                record["schema_valid"] = True
            except ProviderError:
                record.update(schema_valid=False, outcome_ok=False)
                results[model].append(record)
                continue
            total = sum(len(s.citations) for s in payload.statements)
            numbering = CitationNumbering()
            verified = verify_statements(payload.statements, mapping, numbering)
            valid = total - verified.removed_citations
            record.update(
                citations=total,
                citations_valid=valid,
                statements=len(payload.statements),
                statements_kept=len(verified.statements),
            )
            text = (
                " ".join(s["text"] for s in verified.statements).lower()
                + " "
                + " ".join(c["quote"].lower() for c in numbering.flat)
            )
            if negative:
                record["outcome_ok"] = not verified.statements
            else:
                found = sum(1 for k in keywords if k.lower() in text)
                ok = bool(verified.statements) and found >= case.get("min_keywords", 0)
                if must:
                    ok = ok and any(must.lower() in c["quote"].lower() for c in numbering.flat)
                record["outcome_ok"] = ok
            results[model].append(record)
            print(f"{model} {case_id}: {record}", flush=True)
    return results


def summarise_generation(results: dict[str, Any]) -> list[str]:
    lines = [
        "| Model | Schema valid | Quotes valid | Outcome correct | Mean latency (s) | Mean cost per answer (USD) | Errors |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for model, records in results.items():
        ok = [r for r in records if "error" not in r]
        schema = sum(1 for r in ok if r.get("schema_valid"))
        cites = sum(r.get("citations", 0) for r in ok)
        valid = sum(r.get("citations_valid", 0) for r in ok)
        outcome = sum(1 for r in ok if r.get("outcome_ok"))
        latency = sum(r["seconds"] for r in ok) / len(ok) if ok else 0
        costs = [r["cost_usd"] for r in ok if r.get("cost_usd") is not None]
        cost = f"{sum(costs) / len(costs):.5f}" if costs else "n/a"
        quotes = f"{valid}/{cites}" if cites else "0/0"
        lines.append(
            f"| `{model}` | {schema}/{len(records)} | {quotes} | {outcome}/{len(records)} | {latency:.1f} | {cost} | {len(records) - len(ok)} |"
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-generation", action="store_true")
    parser.add_argument("--skip-embeddings", action="store_true")
    args = parser.parse_args()
    settings = eval_settings()
    assert settings.openrouter_api_key is not None
    provider = OpenRouterProvider(
        settings.openrouter_api_key.get_secret_value(), settings.openrouter_base_url, 60
    )
    chunks = load_corpora()
    stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M")
    info = provenance(EVAL / "cases_generic.json")
    out: dict[str, Any] = {"run": stamp, "chunks": len(chunks), "provenance": info}
    lines = [
        f"# Model bake-off ({stamp} UTC)",
        "",
        f"Corpus: NIST AI 100-1 plus the synthetic Inbound Operations corpus, {len(chunks)} chunks. "
        + provenance_line(info),
        "",
    ]
    if not args.skip_embeddings:
        report, cosines = embedding_bakeoff(provider, chunks)
        out["embeddings"] = report
        out["best_cosines"] = cosines
        lines += [
            "## Embeddings (retrieval on labelled G and E questions, top 10)",
            "",
            "| Model | Mode | n | hit@3 | hit@5 | MRR | Seconds |",
            "| :--- | :--- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for model, summary in report.items():
            if "error" in summary:
                lines.append(f"| `{model}` | error | | | | | {summary['error']} |")
                continue
            for mode in ("dense", "hybrid"):
                s = summary[mode]
                lines.append(
                    f"| `{model}` | {mode} | {s['n']} | {s['hit@3']} | {s['hit@5']} | {s['mrr']} | {summary['seconds']} |"
                )
        lines += [
            "",
            "Best-match cosine per question (answerable versus off-topic), for the evidence floor:",
            "",
        ]
        for model, values in cosines.items():
            pos = [v["best"] for v in values.values() if not v["negative"]]
            neg = [v["best"] for v in values.values() if v["negative"]]
            lines.append(
                f"- `{model}`: answerable min {min(pos):.3f} (median {sorted(pos)[len(pos) // 2]:.3f}); off-topic max {max(neg):.3f} ({', '.join(f'{k} {v["best"]:.3f}' for k, v in values.items() if v['negative'])})"
            )
        lines.append("")
    if not args.skip_generation:
        results = generation_bakeoff(provider, chunks)
        out["generation"] = results
        lines += [
            "## Generation (same six retrieved contexts for every model: G-01 to G-05, E-14)",
            "",
        ] + summarise_generation(results)
        lines += [
            "",
            "Statement-type correctness needs the typed Resolution Card and is measured with the E-cases in stage 2.",
        ]
    path = EVAL / "results" / f"{stamp}-bakeoff"
    path.with_suffix(".json").write_text(json.dumps(out, indent=2) + "\n")
    path.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    provider.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
