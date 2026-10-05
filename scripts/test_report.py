"""Turn a pytest JUnit XML file into a Markdown test report: requirement → TC → result.

Usage: python scripts/test_report.py reports/junit.xml [docs/testing.md]
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET  # noqa: S405 - parses our own pytest output
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


def results(junit: Path) -> dict[str, list[tuple[str, str]]]:
    by_tc: dict[str, list[tuple[str, str]]] = defaultdict(list)
    tree = ET.parse(junit)  # noqa: S314 - trusted local file
    for case in tree.iter("testcase"):
        name = case.get("name", "")
        match = TC_IN_NAME.search(name)
        if not match:
            continue
        tc = f"TC-{match.group(1).upper()}-{match.group(2)}"
        if case.find("failure") is not None or case.find("error") is not None:
            outcome = "fail"
        elif case.find("skipped") is not None:
            outcome = "skipped"
        else:
            outcome = "pass"
        by_tc[tc].append((name.split("[")[0], outcome))
    return by_tc


def main() -> int:
    junit = Path(sys.argv[1])
    testing = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "docs" / "testing.md"
    requirement_of = catalogue(testing)
    by_tc = results(junit)
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
        overall = "fail" if "fail" in outcomes else "skipped" if all(o == "skipped" for o in outcomes) else "pass"
        totals[overall] += 1
        lines.append(f"| {requirement_of.get(tc, '—')} | {tc} | {len(outcomes)} | {overall} |")
    planned = {tc for tc in requirement_of}
    missing = sorted(planned - set(by_tc))
    lines += [
        "",
        f"Test cases: {totals['pass']} pass, {totals['fail']} fail, {totals['skipped']} skipped.",
        f"Catalogue cases without a test in this run: {', '.join(missing) if missing else 'none'}.",
    ]
    print("\n".join(lines))
    return 1 if totals["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
