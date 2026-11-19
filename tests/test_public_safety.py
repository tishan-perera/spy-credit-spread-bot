"""Leak guard: this repo is public, so no tracked file may hold private details.

Private strings (account digits, balances) live one per line in the git-ignored
`.private-patterns` file, so this test never has to spell them out itself.
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GENERIC = {
    "email address": re.compile(r"[A-Za-z0-9._%+-]+@(?!anthropic\.com)[A-Za-z0-9-]+\.[A-Za-z0-9.-]*[a-z]{2,}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    "API key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    "Slack token": re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"),
    "account number field": re.compile("account" + "_number"),  # split so this file does not match itself
}


def tracked_text_files():
    names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.splitlines()
    for name in names:
        path = ROOT / name
        try:
            yield name, path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue


def private_strings():
    path = ROOT / ".private-patterns"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def test_no_generic_secrets_in_tracked_files():
    hits = [f"{name}: {label}" for name, text in tracked_text_files()
            for label, pattern in GENERIC.items() if pattern.search(text)]
    assert hits == []


def test_no_private_strings_in_tracked_files():
    secrets = private_strings()
    hits = [f"{name}: private string #{i + 1}" for name, text in tracked_text_files()
            for i, s in enumerate(secrets) if s in text]
    assert hits == []


def test_private_files_are_ignored():
    for name in ("CLAUDE.local.md", ".private-patterns"):
        result = subprocess.run(["git", "check-ignore", "-q", name], cwd=ROOT)
        assert result.returncode == 0, f"{name} must be git-ignored"
