"""Turn a pytest JUnit XML file into a Markdown test report: requirement → TC → result.

Usage: python scripts/test_report.py reports/junit.xml [docs/testing.md]
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TC_IN_NAME = re.compile(r"test_tc_([a-z]+)_(\d{3})")
ROW = re.compile(r"^\|\s*((?:N?FR)-[A-Z]+-\d{2})?\s*\|[^|]*\|\s*(TC-[A-Z]+-\d{3})\s*\|")


def catalogue(path: Path) -> dict[str, str]:
    """TC ID → requirement ID, from the tables in docs/testing.md."""
    mapping: dict[str, str] = {}
    current = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        match = ROW.match(line)
        if match:
            current = match.group(1) or current
            mapping[match.group(2)] = current
    return mapping


def _outcome(case: ET.Element) -> str:
    if case.find("failure") is not None or case.find("error") is not None:
        return "fail"
    if case.find("skipped") is not None:
        return "skipped"
    return "pass"


def results(junit: Path) -> tuple[dict[str, list[tuple[str, str]]], dict[str, int]]:
    """Outcomes per TC ID, and the outcome counts of tests without a TC ID (regression tests
    written for review findings), so the report never hides them."""
    by_tc: dict[str, list[tuple[str, str]]] = defaultdict(list)
    other: dict[str, int] = defaultdict(int)
    tree = ET.parse(junit)  # noqa: S314 - trusted local file
    for case in tree.iter("testcase"):
        name = case.get("name", "")
        match = TC_IN_NAME.search(name)
        if not match:
            other[_outcome(case)] += 1
            continue
        tc = f"TC-{match.group(1).upper()}-{match.group(2)}"
        by_tc[tc].append((name.split("[")[0], _outcome(case)))
    return by_tc, other


def main() -> int:
    junit = Path(sys.argv[1])
    testing = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "docs" / "testing.md"
    requirement_of = catalogue(testing)
    by_tc, other = results(junit)
    lines = [
        "# Test report",
        "",
        f"Source: `{junit.name}`. One row per test case ID; a TC passes only if all its tests pass.",
        "",
        "| Requirement | TC | Tests | Result |",
        "| :--- | :--- | ---: | :--- |",
    ]
    totals = defaultdict(int)
    for tc in sorted(by_tc, key=lambda t: (requirement_of.get(t, "~"), t)):
        outcomes = [o for _, o in by_tc[tc]]
        if "fail" in outcomes:
            overall = "fail"
        elif all(o == "skipped" for o in outcomes):
            overall = "skipped"
        elif "skipped" in outcomes:
            # Some of its tests did not run: never shown as a full pass (full audit DOC-02).
            overall = "partial"
        else:
            overall = "pass"
        totals[overall] += 1
        skipped = outcomes.count("skipped")
        result = f"{overall} ({skipped} of {len(outcomes)} skipped)" if overall == "partial" else overall
        lines.append(f"| {requirement_of.get(tc, '—')} | {tc} | {len(outcomes)} | {result} |")
    planned = {tc for tc in requirement_of}
    missing = sorted(planned - set(by_tc))
    lines += [
        "",
        f"Test cases: {totals['pass']} pass, {totals['partial']} partly skipped, {totals['fail']} fail, "
        f"{totals['skipped']} skipped.",
        f"Catalogue cases without a test in this run: {', '.join(missing) if missing else 'none'}.",
        f"Other tests (regression tests without a test-case ID): {sum(other.values())} run, "
        f"{other['pass']} pass, {other['fail']} fail, {other['skipped']} skipped.",
    ]
    print("\n".join(lines))
    return 1 if totals["fail"] or other["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
