#!/usr/bin/env python3
"""Verify that a release tag matches all shipped component versions."""

from __future__ import annotations

import argparse
import ast
import json
import re
from datetime import date
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


def frontmatter_version(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise RuntimeError(f"YAML frontmatter not found in {path}")
    try:
        end = next(
            index
            for index, line in enumerate(lines[1:], 1)
            if line == "---"
        )
    except StopIteration as error:
        raise RuntimeError(f"YAML frontmatter is not closed in {path}") from error
    matches = re.findall(
        r"^version:[ \t]*([^ \t\r\n]+)[ \t]*$",
        "\n".join(lines[1:end]),
        re.MULTILINE,
    )
    if len(matches) != 1:
        raise RuntimeError(f"expected one frontmatter version in {path}")
    return matches[0]


def skill_version() -> str:
    return frontmatter_version(SKILL_ROOT / "SKILL.md")


def plugin_version() -> str:
    payload = json.loads(
        (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    version = payload.get("version")
    if not isinstance(version, str):
        raise RuntimeError("version not found in .claude-plugin/plugin.json")
    return version


def shared_core_version() -> str:
    payload = json.loads(
        (REPO_ROOT / "shared-core.json").read_text(encoding="utf-8")
    )
    version = payload.get("identity", {}).get("helper_version")
    if not isinstance(version, str):
        raise RuntimeError("identity.helper_version not found in shared-core.json")
    return version


def check_changelog(expected_version: str) -> tuple[bool, str]:
    content = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    pattern = (
        rf"^##[ \t]+{re.escape(expected_version)}[ \t]+-[ \t]+"
        r"([^\r\n]*?)[ \t]*\r?$"
    )
    matches = re.findall(pattern, content, re.MULTILINE)
    if len(matches) != 1:
        return (
            False,
            f"CHANGELOG.md must contain exactly one dated heading for "
            f"version {expected_version}; found {len(matches)}",
        )
    changelog_date = matches[0]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", changelog_date) is None:
        return False, f"CHANGELOG.md has invalid date {changelog_date!r}"
    try:
        date.fromisoformat(changelog_date)
    except ValueError:
        return False, f"CHANGELOG.md has invalid date {changelog_date!r}"
    return True, ""


def check_marketplace() -> tuple[bool, str]:
    """Verify the marketplace manifest stays consistent with plugin.json.

    The marketplace entry must not carry its own version: the version is
    pinned by plugin.json alone, so every release that bumps plugin.json
    flows to marketplace installs without a second edit to forget.
    """
    path = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    if not path.is_file():
        return False, f"marketplace manifest not found at {path}"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return False, f"marketplace.json is not valid JSON: {error}"

    if not isinstance(manifest.get("name"), str) or not manifest["name"]:
        return False, "marketplace.json must set a non-empty name"
    owner = manifest.get("owner")
    if not isinstance(owner, dict) or not isinstance(owner.get("name"), str):
        return False, "marketplace.json must set owner.name"

    plugin = json.loads(
        (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    entries = manifest.get("plugins")
    if not isinstance(entries, list) or len(entries) != 1:
        return False, "marketplace.json must list exactly one plugin entry"
    entry = entries[0]
    if entry.get("name") != plugin.get("name"):
        return (
            False,
            f"marketplace entry name {entry.get('name')!r} does not match "
            f"plugin.json name {plugin.get('name')!r}",
        )
    if entry.get("source") != "./":
        return False, "marketplace entry source must be \"./\" (this repository)"
    if entry.get("description") != plugin.get("description"):
        return False, "marketplace entry description differs from plugin.json"
    if "version" in entry:
        return (
            False,
            "marketplace entry must not set version; plugin.json is the "
            "single version source",
        )
    return True, ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="release tag, for example v1.1.0")
    args = parser.parse_args()

    expected = args.tag[1:] if args.tag.startswith("v") else args.tag
    versions = {
        "helper": helper_version(),
        "skill": skill_version(),
        "plugin": plugin_version(),
        "shared-core": shared_core_version(),
    }
    mismatches = {name: version for name, version in versions.items() if version != expected}
    if mismatches:
        for name, version in mismatches.items():
            print(f"{name} version {version!r} does not match tag {args.tag!r}")
        return 1
    changelog_ok, changelog_error = check_changelog(expected)
    if not changelog_ok:
        print(changelog_error)
        return 1
    marketplace_ok, marketplace_error = check_marketplace()
    if not marketplace_ok:
        print(marketplace_error)
        return 1
    print(f"release versions match {args.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
