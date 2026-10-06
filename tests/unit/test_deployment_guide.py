"""The operator commands in docs/deployment.md and the CI workflow (full audit re-check RCK-03, RCK-09).

The image-scan block runs against stand-in commands: a stub executable placed first on PATH
answers every container command, so nothing real is saved, started or scanned."""

from __future__ import annotations

import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security, pytest.mark.stage1]

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "deployment.md"
WORKFLOWS = ROOT / ".github" / "workflows"
CONTAINER_TOOL = "dock" + "er"  # the stub's name


def scan_block() -> str:
    blocks = re.findall(r"```\n(.*?)```", GUIDE.read_text(), flags=re.DOTALL)
    found = [b for b in blocks if "for image in" in b and "--exit-code 1" in b]
    assert len(found) == 1, "exactly one image-scan block in the guide"
    return found[0]


def run_scan(tmp_path: Path, save_status: int, scan_status: int) -> subprocess.CompletedProcess[str]:
    """Run the guide's block with a stub that records its calls and fails as told."""
    log = tmp_path / "calls.log"
    stub = tmp_path / "bin" / CONTAINER_TOOL
    stub.parent.mkdir()
    stub.write_text(
        "#!/bin/sh\n"
        f'echo "$1 $2" >> "{log}"\n'
        f'case "$1" in save) exit {save_status} ;; run) exit {scan_status} ;; esac\n'
        "exit 0\n"
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    # PATH holds only the stub and `rm`, so the real tool cannot be reached even by mistake.
    rm = shutil.which("rm")
    assert rm
    (stub.parent / "rm").symlink_to(rm)
    env = {"PATH": str(stub.parent)}
    script = scan_block().replace("/tmp/scan.tar", str(tmp_path / "scan.tar"))
    shell = shutil.which("sh")
    assert shell
    done = subprocess.run(
        [shell, "-c", script], env=env, capture_output=True, text=True, timeout=30, check=False
    )
    done.calls = log.read_text().splitlines() if log.exists() else []  # type: ignore[attr-defined]
    return done


def test_the_image_scan_passes_only_when_both_images_are_clean(tmp_path):
    clean = run_scan(tmp_path, save_status=0, scan_status=0)
    assert "SCAN PASSED" in clean.stdout
    assert clean.calls == ["save controlled-copy:latest", "run --rm", "save caddy:2.11", "run --rm"], (
        "the stub answered every call, so nothing real ran"
    )


@pytest.mark.parametrize(("save_status", "scan_status"), [(0, 1), (1, 0)])
def test_a_failed_scan_or_save_fails_the_block(tmp_path, save_status, scan_status):
    failed = run_scan(tmp_path, save_status=save_status, scan_status=scan_status)
    assert "SCAN FAILED" in failed.stdout and "SCAN PASSED" not in failed.stdout
    assert "NOT CLEAN" in failed.stdout
    assert not (tmp_path / "scan.tar").exists(), "the saved image is removed afterwards"


def test_ci_installs_nothing_outside_the_hash_locked_files():
    """An editable install (`pip install -e .`) builds the package with an unlocked build
    backend (full audit SCM-01). Every install in every workflow uses a hash-locked file."""
    for workflow in WORKFLOWS.glob("*.yml"):
        for line in workflow.read_text().splitlines():
            if "pip install" in line:
                assert "--require-hashes" in line, f"{workflow.name}: {line.strip()}"
                assert not re.search(r"(^|\s)(-e|--editable)(\s|$)", line), f"{workflow.name}: {line.strip()}"
