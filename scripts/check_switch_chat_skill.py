#!/usr/bin/env python3
"""Verify standalone skill assets and isolated local install/removal layout."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import stat
import tempfile
import zipfile

import yaml

from build_switch_chat_skill import ARCHIVE, FILES, INFO, NAME, ROOT, SUMS, VERSION, build_release, sha256


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="xingshu-skill-check-") as directory:
        temporary = Path(directory)
        first = temporary / "first"
        second = temporary / "second"
        metadata = build_release(first)
        build_release(second)
        for name in (ARCHIVE, INFO, SUMS):
            assert (first / name).read_bytes() == (second / name).read_bytes(), name
        previous = {name: (first / name).read_bytes() for name in (ARCHIVE, INFO, SUMS)}
        try:
            build_release(first)
        except FileExistsError:
            pass
        else:
            raise AssertionError("Existing release assets were overwritten")
        assert previous == {name: (first / name).read_bytes() for name in previous}
        assert json.loads((first / INFO).read_text()) == metadata
        for line in (first / SUMS).read_text().splitlines():
            digest, name = line.split("  ")
            assert sha256((first / name).read_bytes()) == digest

        discovery = temporary / "project" / ".agents" / "skills"
        with zipfile.ZipFile(first / ARCHIVE) as bundle:
            assert bundle.namelist() == [f"{NAME}/{name}" for name in FILES]
            assert bundle.testzip() is None
            assert all(stat.S_ISREG(entry.external_attr >> 16) for entry in bundle.infolist())
            for item in metadata["files"]:
                data = bundle.read(item["path"])
                assert len(data) == item["bytes"] and sha256(data) == item["sha256"]
            bundle.extractall(discovery)
        installed = discovery / NAME
        for name in FILES:
            assert (installed / name).read_bytes() == (ROOT / "skills" / NAME / name).read_bytes()
        frontmatter = (installed / "SKILL.md").read_text().split("---", 2)[1]
        descriptor = yaml.safe_load(frontmatter)
        assert descriptor["name"] == NAME and descriptor["metadata"]["version"] == VERSION
        assert descriptor["description"] and descriptor["license"] == "Apache-2.0"
        presentation = yaml.safe_load((installed / "agents" / "openai.yaml").read_text())
        assert presentation["policy"]["allow_implicit_invocation"] is False
        assert f"${NAME}" in presentation["interface"]["default_prompt"]
        assert 25 <= len(presentation["interface"]["short_description"]) <= 64
        archived = temporary / "disabled-skills" / NAME
        archived.parent.mkdir()
        shutil.move(str(installed), str(archived))
        assert not installed.exists()
        for name in FILES:
            assert (archived / name).read_bytes() == (ROOT / "skills" / NAME / name).read_bytes()
    print("PASS: exact standalone ZIP, reproducible assets, checksums, explicit policy, isolated install/removal")


if __name__ == "__main__":
    main()
