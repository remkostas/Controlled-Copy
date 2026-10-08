"""Full audit DOC-02: the requirement report never shows a partly skipped case as passed."""

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.stage1]

ROOT = Path(__file__).resolve().parents[2]

JUNIT = """<testsuites><testsuite name="t">
<testcase classname="tests.x" name="test_tc_acc_001_a" />
<testcase classname="tests.x" name="test_tc_acc_001_b"><skipped message="no browser" /></testcase>
<testcase classname="tests.x" name="test_tc_acc_002_a" />
</testsuite></testsuites>"""


def test_doc_02_a_partly_skipped_case_is_reported_as_partial(tmp_path):
    junit = tmp_path / "junit.xml"
    junit.write_text(JUNIT)
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "test_report.py"), str(junit), str(ROOT / "docs/testing.md")],
        capture_output=True,
        text=True,
        check=False,
    )
    cells = [line.split("|") for line in done.stdout.splitlines() if "| TC-ACC" in line]
    rows = {cell[2].strip(): cell[4].strip() for cell in cells}
    assert rows["TC-ACC-001"] == "partial (1 of 2 skipped)"
    assert rows["TC-ACC-002"] == "pass"
    assert "1 partly skipped" in done.stdout


def test_tests_without_a_case_id_are_counted_not_hidden(tmp_path):
    """Pre-delivery audit (Codex PDA-05): regression tests without a TC ID appear in the report,
    and a failing one fails the report."""
    junit = tmp_path / "junit.xml"
    junit.write_text(
        """<testsuites><testsuite name="t">
<testcase classname="tests.x" name="test_tc_acc_002_a" />
<testcase classname="tests.x" name="test_logout_race" />
<testcase classname="tests.x" name="test_refusal_export"><failure message="x" /></testcase>
</testsuite></testsuites>"""
    )
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "test_report.py"), str(junit), str(ROOT / "docs/testing.md")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert (
        "Other tests (regression tests without a test-case ID): 2 run, 1 pass, 1 fail, 0 skipped."
        in done.stdout
    )
    assert done.returncode == 1
