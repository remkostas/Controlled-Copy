"""NFR-SEC-06 and NFR-REV-01 support: the app never reads eval/, the core never imports layers."""

import ast
from pathlib import Path

import pytest

import controlled_copy
from controlled_copy.plugins import LAYERS

pytestmark = [pytest.mark.unit, pytest.mark.stage1]

PACKAGE = Path(controlled_copy.__file__).parent
# Every optional layer package, e.g. ("governance", "models"), from the one registry.
LAYER_PACKAGES = tuple(module.rsplit(".", 1)[-1] for module, _ in LAYERS.values())
LAYER_MODULES = tuple(module for module, _ in LAYERS.values())


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
    assert set(LAYER_PACKAGES) >= {"governance", "models"}
    for path in python_files(exclude=LAYER_PACKAGES):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [alias.name for alias in node.names]
            if any(name.startswith(LAYER_MODULES) or name in LAYER_PACKAGES for name in names):
                offenders.append(str(path.relative_to(PACKAGE)))
    assert offenders == []


def test_tc_rev_001_core_runs_with_the_layer_switched_off(app, settings):
    """The CI job runs the whole stage 1 suite with FEATURE_GOVERNANCE=false; this guards the switch."""
    if any(getattr(settings, flag) for _, flag in LAYERS.values()):
        pytest.skip("this run has a layer switched on")
    assert app.state.registry.loaded == []
    assert app.state.registry.routers == [] and app.state.registry.migrations == []
    # In a fresh interpreter (test collection may import layer tests), the core app must not
    # import any layer module when the flag is off.
    import subprocess
    import sys

    probe = (
        "import sys, tempfile, pathlib;"
        "from controlled_copy.app import create_app;"
        "from controlled_copy.config import Settings;"
        "create_app(Settings(_env_file=None, app_access_code='x', model_provider='fake',"
        " feature_governance=False, feature_model_picker=False,"
        " data_dir=pathlib.Path(tempfile.mkdtemp())), run_purge=False);"
        f"sys.exit(1 if any(m.startswith({LAYER_MODULES!r}) for m in sys.modules) else 0)"
    )
    assert (
        subprocess.run([sys.executable, "-c", probe], capture_output=True, timeout=60, check=False).returncode
        == 0
    )
