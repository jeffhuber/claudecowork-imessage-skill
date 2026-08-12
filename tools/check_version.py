#!/usr/bin/env python3
"""Verify that a release tag matches the helper and skill versions."""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = REPO_ROOT / "skills" / "imessage-review"


def helper_version() -> str:
    module = ast.parse((SKILL_ROOT / "bin" / "helper.py").read_text(encoding="utf-8"))
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "HELPER_VERSION":
                    value = ast.literal_eval(node.value)
                    if isinstance(value, str):
                        return value
    raise RuntimeError("HELPER_VERSION not found in the bundled helper")


def skill_version() -> str:
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"^version:\s*([^\s]+)\s*$", text, re.MULTILINE)
    if match is None:
        raise RuntimeError("version not found in SKILL.md front matter")
    return match.group(1)


def plugin_version() -> str:
    payload = json.loads(
        (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    version = payload.get("version")
    if not isinstance(version, str):
        raise RuntimeError("version not found in .claude-plugin/plugin.json")
    return version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="release tag, for example v1.1.0")
    args = parser.parse_args()

    expected = args.tag[1:] if args.tag.startswith("v") else args.tag
    versions = {
        "helper": helper_version(),
        "skill": skill_version(),
        "plugin": plugin_version(),
    }
    mismatches = {name: version for name, version in versions.items() if version != expected}
    if mismatches:
        for name, version in mismatches.items():
            print(f"{name} version {version!r} does not match tag {args.tag!r}")
        return 1
    print(f"release versions match {args.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
