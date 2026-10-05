"""NFR-SEC-06 and NFR-REV-01 support: the app never reads eval/, the core never imports layers."""

import ast
from pathlib import Path

import pytest

import controlled_copy

pytestmark = [pytest.mark.unit, pytest.mark.stage1]

PACKAGE = Path(controlled_copy.__file__).parent


def python_files(exclude: tuple[str, ...] = ()) -> list[Path]:
    return [
        p for p in PACKAGE.rglob("*.py") if not any(part in exclude for part in p.relative_to(PACKAGE).parts)
    ]


def test_tc_sec_006_application_never_references_the_eval_folder():
    offenders = []
    for path in [*python_files(), *PACKAGE.rglob("*.html"), *PACKAGE.rglob("*.json"), *PACKAGE.rglob("*.js")]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in ('"eval/', "'eval/", "/eval/", '"eval"', "'eval'", "cases_generic", "cases_governed"):
            if token in text:
                offenders.append(f"{path.relative_to(PACKAGE)}: {token}")
    assert offenders == []


def test_tc_sec_006_core_never_imports_a_layer_package():
    offenders = []
    for path in python_files(exclude=("governance",)):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [alias.name for alias in node.names]
            if any(name.startswith("controlled_copy.governance") or name == "governance" for name in names):
                offenders.append(str(path.relative_to(PACKAGE)))
    assert offenders == []


def test_tc_rev_001_core_runs_with_the_layer_switched_off(app, settings):
    """The CI job runs the whole stage 1 suite with FEATURE_GOVERNANCE=false; this guards the switch."""
    if settings.feature_governance:
        pytest.skip("this run has the governance layer switched on")
    assert app.state.registry.loaded == []
    assert app.state.registry.routers == [] and app.state.registry.migrations == []
    assert "controlled_copy.governance" not in __import__("sys").modules
