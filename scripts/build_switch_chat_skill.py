#!/usr/bin/env python3
"""Build a standalone skill ZIP from exact committed public files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = "xingshu-switch-chat"
VERSION = "0.2.0"
FILES = (
    "SKILL.md", "agents/openai.yaml", "agents/interface.yaml", "LICENSE.txt", "manifest.json",
    "references/browser-channels.md", "references/handoff-contract.md",
    "references/evaluation.md", "scripts/validate_run.py",
    "evals/semantic-config.json", "evals/trigger-cases.json",
    "evals/run-cases.json", "reports/output_quality_scorecard.md",
)
ARCHIVE = f"{NAME}-{VERSION}.zip"
INFO = "switch-chat-skill-build-info.json"
SUMS = "SHA256SUMS.txt"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def build_release(output: Path) -> dict:
    commit = git("rev-parse", "HEAD").decode().strip()
    tree = git("rev-parse", "HEAD^{tree}").decode().strip()
    skill = ROOT / "skills" / NAME
    sources = {}
    for name in FILES:
        path = skill / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Required regular file missing: {name}")
        path.resolve().relative_to(ROOT)
        data = path.read_bytes()
        relative = f"skills/{NAME}/{name}"
        if data != git("show", f"{commit}:{relative}"):
            raise ValueError(f"Uncommitted skill content: {name}")
        sources[name] = data
    if sources["LICENSE.txt"] != git("show", f"{commit}:LICENSE"):
        raise ValueError("Skill license does not match the committed repository license")
    if any((output / name).exists() or (output / name).is_symlink()
           for name in (ARCHIVE, INFO, SUMS)):
        raise FileExistsError("Release assets already exist; choose a fresh directory")
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output / ARCHIVE, "x", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as bundle:
        for name, data in sources.items():
            entry = zipfile.ZipInfo(f"{NAME}/{name}", (2026, 10, 12, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(entry, data)
    archive = (output / ARCHIVE).read_bytes()
    metadata = {
        "schema_version": 1,
        "skill": NAME,
        "version": VERSION,
        "repository": "Johnny-us/XINGSHU-Core",
        "source_commit": commit,
        "source_tree": tree,
        "skill_path": f"skills/{NAME}",
        "license": "Apache-2.0",
        "instructions_only": False,
        "includes_optional_offline_validator": True,
        "validator_dependencies": "Python standard library only",
        "requires_core_install": False,
        "full_two_endpoint_live_switch_accepted": False,
        "files": [{"path": f"{NAME}/{name}", "bytes": len(data),
                   "sha256": sha256(data)} for name, data in sources.items()],
        "archive": {"name": ARCHIVE, "bytes": len(archive), "sha256": sha256(archive)},
    }
    info = (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode()
    with (output / INFO).open("xb") as stream:
        stream.write(info)
    with (output / SUMS).open("x", encoding="utf-8") as stream:
        stream.write(f"{sha256(archive)}  {ARCHIVE}\n{sha256(info)}  {INFO}\n")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build_release(args.output), ensure_ascii=False, indent=2))
