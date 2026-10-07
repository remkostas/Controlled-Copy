"""The operator commands in docs/deployment.md and the CI workflow (full audit re-check RCK-03, RCK-09).

The image-scan block runs against stand-in commands: a stub executable placed first on PATH
answers every container command, so nothing real is saved, started or scanned."""

from __future__ import annotations

import re
import shlex
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


def run_scan(
    tmp_path: Path, save_status: int, scan_statuses: tuple[int, int]
) -> subprocess.CompletedProcess[str]:
    """Run the guide's block with a stub that records its calls and fails as told: every save
    fails with `save_status` (a successful save writes the archive, so cleanup is real), and the
    n-th scan exits with `scan_statuses[n - 1]`. The stub uses shell builtins only."""
    log = tmp_path / "calls.log"
    count = tmp_path / "scans.count"
    stub = tmp_path / "bin" / CONTAINER_TOOL
    stub.parent.mkdir()
    statuses = " ".join(str(s) for s in scan_statuses)
    stub.write_text(
        "#!/bin/sh\n"
        f'echo "$1 $2" >> "{log}"\n'
        'if [ "$1" = save ]; then\n'
        f'  [ {save_status} -eq 0 ] && : > "$4"\n'
        f"  exit {save_status}\n"
        "fi\n"
        'if [ "$1" = run ]; then\n'
        '  archive="${4%%:*}"\n'
        f'  [ -f "$archive" ] && echo "archive present" >> "{log}"\n'
        f'  n=0; [ -f "{count}" ] && read n < "{count}"; n=$((n + 1)); echo "$n" > "{count}"\n'
        f"  set -- {statuses}\n"
        '  eval "status=\\${$n:-0}"\n'
        '  exit "$status"\n'
        "fi\n"
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
    clean = run_scan(tmp_path, save_status=0, scan_statuses=(0, 0))
    assert "SCAN PASSED" in clean.stdout and clean.returncode == 0
    assert clean.calls == [
        "save controlled-copy:latest",
        "run --rm",
        "archive present",
        "save caddy:2.11",
        "run --rm",
        "archive present",
    ], "each scan read a freshly saved archive; the stub answered every call, so nothing real ran"
    assert not (tmp_path / "scan.tar").exists(), "the saved image is removed afterwards"


@pytest.mark.parametrize(
    ("save_status", "scan_statuses", "clean_first"),
    [(0, (1, 1), False), (1, (0, 0), False), (0, (0, 1), True)],
    ids=["both-scans-fail", "saves-fail", "second-image-fails"],
)
def test_a_failed_scan_or_save_fails_the_block(tmp_path, save_status, scan_statuses, clean_first):
    """Full audit re-check RCK-09 and the second re-check: the block prints SCAN FAILED and
    exits non-zero, so a script or `set -e` stops on it."""
    failed = run_scan(tmp_path, save_status=save_status, scan_statuses=scan_statuses)
    assert "SCAN FAILED" in failed.stdout and "SCAN PASSED" not in failed.stdout
    assert failed.returncode != 0, "a failed scan must not exit 0"
    assert "caddy:2.11: NOT CLEAN" in failed.stdout
    assert ("controlled-copy:latest: clean" in failed.stdout) == clean_first
    assert not (tmp_path / "scan.tar").exists(), "the saved image is removed afterwards"


def pip_installs(text: str) -> list[list[str]]:
    """The arguments of every `pip install` in a workflow or Dockerfile, one list per install;
    a line continued with a backslash is joined first, `&&`, `||` and `;` separate commands."""
    joined = text.replace("\\\n", " ")
    installs = []
    for line in joined.splitlines():
        for command in re.split(r"&&|\|\||;", line):
            if "pip install" in command:
                installs.append(shlex.split(command.split("pip install", 1)[1]))
    return installs


def hash_locked_only(args: list[str]) -> bool:
    """`--require-hashes` and nothing to install except `-r <file>.lock`: no package name,
    no local path (`.`, an editable `-e .`), so no unlocked build backend can run."""
    if "--require-hashes" not in args:
        return False
    rest = iter(args)
    for arg in rest:
        if arg in ("-r", "--requirement"):
            if not next(rest, "").endswith(".lock"):
                return False
        elif arg not in ("--require-hashes", "--no-deps"):
            return False
    return True


def test_ci_installs_nothing_outside_the_hash_locked_files():
    """An editable install (`pip install -e .`), and a plain local one (`pip install .`), build
    the package with an unlocked build backend (full audit SCM-01, second re-check). Every
    install in every workflow and in the Dockerfile installs only a hash-locked file."""
    sources = [*WORKFLOWS.glob("*.yml"), ROOT / "Dockerfile"]
    installs = [(path.name, args) for path in sources for args in pip_installs(path.read_text())]
    assert installs, "the workflows install their dependencies with pip"
    for name, args in installs:
        assert hash_locked_only(args), f"{name}: pip install {' '.join(args)}"


@pytest.mark.parametrize(
    ("command", "allowed"),
    [
        ("pip install --require-hashes -r requirements-dev.lock", True),
        ("pip install --require-hashes -r requirements-dev.lock && pip install --no-deps -e .", False),
        ("pip install --require-hashes -r requirements-dev.lock && pip install --no-deps .", False),
        ("pip install --require-hashes -r requirements.lock rich", False),
        ("pip install -r requirements.lock", False),
    ],
)
def test_the_install_guard_itself(command, allowed):
    assert all(hash_locked_only(args) for args in pip_installs(command)) == allowed
