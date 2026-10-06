"""Run evaluation cases against the real model through the app's HTTP interface.

Usage: python eval/run_eval.py {generic,governed} [--model MODEL] [--fallback MODEL]
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

from client import EVAL, ROOT, AppClient, eval_settings, fetch_document, provenance, provenance_line

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
    haystack = (
        " ".join(s["text"] for s in answer["statements"]) + " " + " ".join(c["quote"] for c in citations)
    )
    haystack = re.sub(r"\s+", " ", haystack.lower().replace("-\n", "").replace("- ", ""))
    found = [k for k in case["keywords"] if k.lower() in haystack]
    record["keywords_found"] = f"{len(found)}/{len(case['keywords'])}"
    if len(found) < case["min_keywords"]:
        reasons.append(f"only {len(found)} of {case['min_keywords']} required terms present")
    must = case.get("quote_must_contain")
    if must and not any(must.lower() in re.sub(r"\s+", " ", c["quote"].lower()) for c in citations):
        reasons.append(f"no quote contains '{must}'")
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


def model_overrides(model: str | None, fallback: str | None) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    if model:
        overrides["model_generation"] = model
    if fallback:
        overrides["model_generation_fallback"] = fallback
    return overrides


def normalised(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def check_card(
    case: dict[str, Any], status: int, body: dict[str, Any], app: AppClient, texts: dict[str, str]
) -> dict[str, Any]:
    """The mechanical checks of demo-corpus-and-eval.md for one Resolution Card."""
    if status != 200:
        return {"kind": f"error {status}", "error": body.get("error"), "reasons": [f"status {status}"]}
    output = body["output"]
    card = output["card"]
    citations = output.get("citations", [])
    reasons = verify_citations(app, citations, texts)
    label_of = {d["source_id"]: d["label"] for d in card["used"] + card["excluded"]}
    cited = sorted({label_of.get(c["source_id"], c["source_id"]) for c in citations})
    items = [item for section in output["sections"] for item in section["items"]]
    types = sorted({item["type"] for item in items})
    verified = {c["n"] for c in citations}
    source_of = {c["n"]: c["source_id"] for c in citations}

    if card["status"] not in case["expected_status"]:
        reasons.append(f"status {card['status']}, expected {' or '.join(case['expected_status'])}")
    missing_sources = [s for s in case["expected_sources"] if s not in cited]
    if missing_sources:
        reasons.append("does not cite " + ", ".join(missing_sources))
    misused = [m for m in case["must_not_use"] if any(m in label for label in cited)]
    if misused:
        reasons.append("cites " + ", ".join(misused) + " as authority")
    if case["expected_warning"] is True and not card["warnings"]:
        reasons.append("no warning about an excluded document")
    if case["expected_warning"] is False and card["warnings"]:
        reasons.append("unexpected warning: " + ", ".join(w["label"] for w in card["warnings"]))
    absent_types = [t for t in case["expected_statement_types"] if t not in types]
    if absent_types:
        reasons.append("no statement of type " + ", ".join(absent_types))
    unquoted = [
        i for i in items if i["type"] == "requirement" and not {c["n"] for c in i["cites"]} & verified
    ]
    if unquoted:
        reasons.append(f"{len(unquoted)} requirement(s) without a verified quote")
    identifier = case.get("undocumented_identifier")
    if identifier and identifier not in card["undocumented"]:
        reasons.append(f"{identifier} not reported as undocumented")
    shown = normalised(" ".join(i["text"] for i in items))
    for phrase in case.get("forbidden_text", []):
        if phrase.lower() in shown:
            reasons.append(f"shows the forbidden text '{phrase}'")
    for pattern in case.get("forbidden_patterns", []):
        if re.search(pattern, shown, re.IGNORECASE):
            reasons.append(f"shows text matching the forbidden pattern {pattern!r}")
    must = case.get("quote_must_contain")
    if must and not any(must.lower() in normalised(c["quote"]) for c in citations):
        reasons.append(f"no quote contains '{must}'")
    if card["status"] == "refusal" and items:
        reasons.append("a refusal with items")
    detail = [
        {
            "section": section["key"],
            "type": item["type"],
            "text": item["text"],
            "cites": [label_of.get(source_of[c["n"]], "?") for c in item["cites"] if c["n"] in source_of],
            **({"downgraded": item["downgraded"]} if "downgraded" in item else {}),
        }
        for section in output["sections"]
        for item in section["items"]
    ]
    return {
        "kind": card["status"],
        "status_reasons": card["reasons"],
        "detail": detail,
        "cited": cited,
        "warnings": [w["label"] for w in card["warnings"]],
        "types": types,
        "items": len(items),
        "citations": len(citations),
        "removed": output.get("removed", 0),
        "downgraded": output.get("downgraded", 0),
        "model": output.get("model"),
        "reasons": reasons,
    }


def run_governed(
    model: str | None,
    fallback: str | None,
    only: list[str] | None = None,
    cases_file: str = "cases_governed.json",
) -> tuple[str, list[dict[str, Any]]]:
    spec = json.loads((EVAL / cases_file).read_text())
    extra = ROOT / spec["extra"]
    settings = eval_settings(feature_governance=True, **model_overrides(model, fallback))
    app = AppClient(settings)
    results = []
    try:
        for case in spec["cases"]:
            if only and case["case_id"] not in only:
                continue
            notebook, source_ids = app.reset_workspace()
            if case["notebook"] == "demo-plus-injection":
                source_ids.append(app.upload(notebook, extra.name, extra.read_bytes()))
            started = time.monotonic()
            status, body = app.card(notebook, case["situation"], source_ids, spec["default_context"])
            record = check_card(case, status, body, app, {})
            record.update(
                case_id=case["case_id"],
                title=case["title"],
                passed=not record["reasons"],
                seconds=round(time.monotonic() - started, 1),
            )
            results.append(record)
            print(
                f"{case['case_id']}: {'PASS' if record['passed'] else 'FAIL'} {record['kind']} "
                f"{record.get('cited')} {record['reasons']}",
                flush=True,
            )
    finally:
        app.close()
    return settings.model_generation, results


def run_generic(model: str | None, fallback: str | None) -> tuple[str, list[dict[str, Any]]]:
    spec = json.loads((EVAL / "cases_generic.json").read_text())
    name, data = fetch_document(spec["document"])
    settings = eval_settings(**model_overrides(model, fallback))
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


def write_report(
    set_name: str, model: str, results: list[dict[str, Any]], extra: str = "", subset: bool = False
) -> Path:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    slug = model.replace("/", "_")
    name = f"{stamp}-{slug}-{set_name}{'-subset' if subset else ''}"
    json_path, md_path = EVAL / "results" / f"{name}.json", EVAL / "results" / f"{name}.md"
    case_file = {"governed": "cases_governed.json", "holdout": "cases_governed_holdout.json"}.get(
        set_name, "cases_generic.json"
    )
    info = provenance(EVAL / case_file)
    json_path.write_text(
        json.dumps({"model": model, "set": set_name, "provenance": info, "results": results}, indent=2) + "\n"
    )
    passed = sum(1 for r in results if r["passed"])
    lines = [
        f"# Evaluation: {set_name} set",
        "",
        f"Run {stamp} UTC, generation model `{model}`, embeddings `baai/bge-m3`. {passed} of {len(results)} cases pass.",
        provenance_line(info),
        "",
    ]
    if set_name in ("governed", "holdout"):
        lines += [
            "| Case | Title | Result | Status | Cited documents | Warnings | Types | Seconds | Reasons |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | ---: | :--- |",
        ]
        for r in results:
            lines.append(
                f"| {r['case_id']} | {r['title']} | {'pass' if r['passed'] else 'FAIL'} | {r['kind']} | "
                f"{', '.join(r.get('cited', [])) or '—'} | {', '.join(r.get('warnings', [])) or '—'} | "
                f"{', '.join(r.get('types', [])) or '—'} | {r['seconds']} | {'; '.join(r['reasons']) or '—'} |"
            )
    else:
        lines += [
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
    md_path.write_text("\n".join(lines) + "\n")
    return md_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("set", choices=["generic", "governed", "holdout"])
    parser.add_argument("--model")
    parser.add_argument("--fallback")
    parser.add_argument("--cases", help="comma-separated case IDs (governed set only)")
    args = parser.parse_args()
    only = args.cases.split(",") if args.cases else None
    if args.set == "governed":
        model, results = run_governed(args.model, args.fallback, only)
    elif args.set == "holdout":
        model, results = run_governed(args.model, args.fallback, only, "cases_governed_holdout.json")
    else:
        model, results = run_generic(args.model, args.fallback)
    path = write_report(args.set, model, results, subset=bool(args.cases))
    print(path.read_text())
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
