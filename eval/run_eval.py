"""Run evaluation cases against the real model through the app's HTTP interface.

Usage: python eval/run_eval.py generic [--model MODEL] [--fallback MODEL]
Writes eval/results/<date>-<model>-<set>.json and .md. Every check is mechanical.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from client import EVAL, AppClient, eval_settings, fetch_document, provenance, provenance_line

PAGE_RE = re.compile(r"page (\d+)")


def verify_citations(app: AppClient, citations: list[dict[str, Any]], texts: dict[str, str]) -> list[str]:
    problems = []
    for citation in citations:
        source_id = citation["source_id"]
        if source_id not in texts:
            texts[source_id] = app.source_text(source_id)
        actual = texts[source_id][citation["start"] : citation["end"]]
        if actual != citation["quote"]:
            problems.append(f"citation {citation['n']} does not match the source text at its offsets")
    return problems


def cited_pages(citations: list[dict[str, Any]]) -> set[int]:
    pages = set()
    for citation in citations:
        match = PAGE_RE.search(citation["label"])
        if match:
            pages.add(int(match.group(1)))
    return pages


def check_answer(
    case: dict[str, Any], status: int, body: dict[str, Any], app: AppClient, texts: dict[str, str]
) -> dict[str, Any]:
    reasons: list[str] = []
    answer = body.get("answer", {})
    kind = answer.get("kind") if status == 200 else f"error {status}"
    citations = answer.get("citations", [])
    record: dict[str, Any] = {
        "kind": kind,
        "statements": len(answer.get("statements", [])),
        "citations": len(citations),
        "removed": answer.get("removed", 0),
        "cited_pages": sorted(cited_pages(citations)),
        "model": answer.get("model"),
        "error": body.get("error"),
    }
    if case["kind"] == "refusal":
        if kind != "refusal":
            reasons.append(f"expected a refusal, got {kind}")
        return {**record, "reasons": reasons}
    if kind != "answer":
        reasons.append(f"expected an answer, got {kind}")
        return {**record, "reasons": reasons}
    reasons += verify_citations(app, citations, texts)
    if case["expected_pages"] and not (cited_pages(citations) & set(case["expected_pages"])):
        reasons.append(f"no citation from expected pages {case['expected_pages']}")
    # The expected terms must be in what the answer says, not only in its quotes: a quote can
    # contain the right words while the statement next to it says something else (EVAL-01).
    said = " ".join(s["text"] for s in answer["statements"])
    said = re.sub(r"\s+", " ", said.lower().replace("-\n", "").replace("- ", ""))
    found = [k for k in case["keywords"] if k.lower() in said]
    record["keywords_found"] = f"{len(found)}/{len(case['keywords'])}"
    if len(found) < case["min_keywords"]:
        reasons.append(f"only {len(found)} of {case['min_keywords']} required terms present")
    must = case.get("quote_must_contain")
    if must and not any(must.lower() in re.sub(r"\s+", " ", c["quote"].lower()) for c in citations):
        reasons.append(f"no quote contains '{must}'")
    # The full answer is kept for a human read: whether a quote supports its statement is not
    # checked mechanically.
    record["said"] = [s["text"] for s in answer["statements"]]
    record["quotes"] = [{"n": c["n"], "label": c["label"], "quote": c["quote"]} for c in citations]
    return {**record, "reasons": reasons}


def check_briefing(
    case: dict[str, Any], status: int, body: dict[str, Any], app: AppClient, texts: dict[str, str]
) -> dict[str, Any]:
    reasons: list[str] = []
    if status != 200:
        return {"kind": f"error {status}", "error": body.get("error"), "reasons": [f"status {status}"]}
    output = body["output"]
    citations = output.get("citations", [])
    reasons += verify_citations(app, citations, texts)
    filled = sum(1 for s in output["sections"] if s["items"])
    if filled < case.get("min_sections_with_items", 1):
        reasons.append(f"only {filled} sections have items")
    for section in output["sections"]:
        for item in section["items"]:
            if not item.get("cites"):
                reasons.append("an item has no citation")
    return {
        "kind": "briefing",
        "sections_filled": f"{filled}/{len(output['sections'])}",
        "items": sum(len(s["items"]) for s in output["sections"]),
        "citations": len(citations),
        "removed": output.get("removed", 0),
        "model": output.get("model"),
        "reasons": reasons,
    }


def run_generic(model: str | None, fallback: str | None) -> tuple[str, list[dict[str, Any]]]:
    spec = json.loads((EVAL / "cases_generic.json").read_text())
    name, data = fetch_document(spec["document"])
    overrides: dict[str, Any] = {}
    if model:
        overrides["model_generation"] = model
    if fallback:
        overrides["model_generation_fallback"] = fallback
    settings = eval_settings(**overrides)
    app = AppClient(settings)
    results = []
    try:
        for case in spec["cases"]:
            notebook = app.new_notebook(case["case_id"])
            source_id = app.upload(notebook, name, data)
            texts: dict[str, str] = {}
            started = time.monotonic()
            if case["kind"] == "briefing":
                status, body = app.studio(notebook, "briefing", [source_id])
                record = check_briefing(case, status, body, app, texts)
            else:
                status, body = app.ask(notebook, case["question"], [source_id])
                record = check_answer(case, status, body, app, texts)
            record.update(
                case_id=case["case_id"],
                title=case["title"],
                passed=not record["reasons"],
                seconds=round(time.monotonic() - started, 1),
            )
            results.append(record)
            print(
                f"{case['case_id']}: {'PASS' if record['passed'] else 'FAIL'} {record['reasons']}", flush=True
            )
            app.delete_notebook(notebook)
    finally:
        app.close()
    return settings.model_generation, results


def write_report(set_name: str, model: str, results: list[dict[str, Any]], extra: str = "") -> Path:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M")
    slug = model.replace("/", "_")
    base = EVAL / "results" / f"{stamp}-{slug}-{set_name}"
    info = provenance(EVAL / "cases_generic.json")
    base.with_suffix(".json").write_text(
        json.dumps({"model": model, "set": set_name, "provenance": info, "results": results}, indent=2) + "\n"
    )
    passed = sum(1 for r in results if r["passed"])
    lines = [
        f"# Evaluation: {set_name} set",
        "",
        f"Run {stamp} UTC, generation model `{model}`, embeddings `baai/bge-m3`. {passed} of {len(results)} cases pass.",
        provenance_line(info),
        "",
        "| Case | Title | Result | Outcome | Citations | Cited pages | Seconds | Reasons |",
        "| :--- | :--- | :--- | :--- | ---: | :--- | ---: | :--- |",
    ]
    for r in results:
        pages = ", ".join(str(p) for p in r.get("cited_pages", [])) or "—"
        reasons = "; ".join(r["reasons"]) or "—"
        lines.append(
            f"| {r['case_id']} | {r['title']} | {'pass' if r['passed'] else 'FAIL'} | {r['kind']} | "
            f"{r.get('citations', 0)} | {pages} | {r['seconds']} | {reasons} |"
        )
    if extra:
        lines += ["", extra]
    base.with_suffix(".md").write_text("\n".join(lines) + "\n")
    return base.with_suffix(".md")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("set", choices=["generic"])
    parser.add_argument("--model")
    parser.add_argument("--fallback")
    args = parser.parse_args()
    model, results = run_generic(args.model, args.fallback)
    path = write_report(args.set, model, results)
    print(path.read_text())
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
