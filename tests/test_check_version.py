from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from tools import check_version


class ReleaseVersionTests(unittest.TestCase):
    def check(self, content: str, version: str = "1.2.0") -> tuple[bool, str]:
        with tempfile.TemporaryDirectory(prefix="claude-version-check-") as td:
            root = Path(td)
            (root / "CHANGELOG.md").write_text(content, encoding="utf-8")
            with mock.patch.object(check_version, "REPO_ROOT", root):
                return check_version.check_changelog(version)

    def test_historical_release_date_remains_valid(self) -> None:
        self.assertEqual(
            self.check("# Changelog\n\n## 1.2.0 - 2020-01-02\n"),
            (True, ""),
        )

    def test_crlf_release_heading_is_valid(self) -> None:
        self.assertEqual(
            self.check("# Changelog\r\n\r\n## 1.2.0 - 2020-01-02\r\n"),
            (True, ""),
        )

    def test_duplicate_version_headings_are_rejected(self) -> None:
        valid, error = self.check(
            "## 1.2.0 - 2020-01-02\n\n## 1.2.0 - 2020-01-03\n"
        )
        self.assertFalse(valid)
        self.assertIn("found 2", error)

    def test_invalid_calendar_date_is_rejected(self) -> None:
        valid, error = self.check("## 1.2.0 - 2020-02-31\n")
        self.assertFalse(valid)
        self.assertIn("invalid date", error)

    def test_trailing_date_text_is_rejected(self) -> None:
        valid, error = self.check("## 1.2.0 - 2020-01-02 released\n")
        self.assertFalse(valid)
        self.assertIn("invalid date", error)

    def test_heading_cannot_span_lines(self) -> None:
        valid, error = self.check("## 1.2.0\n  - 2020-01-02\n")
        self.assertFalse(valid)
        self.assertIn("found 0", error)

    def test_missing_version_heading_is_rejected(self) -> None:
        valid, error = self.check("## 1.1.0 - 2020-01-02\n")
        self.assertFalse(valid)
        self.assertIn("found 0", error)

    def test_skill_version_is_read_only_from_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory(prefix="claude-skill-version-") as td:
            skill = Path(td) / "SKILL.md"
            skill.write_text(
                "---\nname: example\nversion: 1.2.0\n---\n\nversion: 9.9.9\n",
                encoding="utf-8",
            )
            self.assertEqual(check_version.frontmatter_version(skill), "1.2.0")

    def test_indented_separator_does_not_close_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory(prefix="claude-skill-version-") as td:
            skill = Path(td) / "SKILL.md"
            skill.write_text(
                "---\nname: example\n  ---\nversion: 1.2.0\n---\n",
                encoding="utf-8",
            )
            self.assertEqual(check_version.frontmatter_version(skill), "1.2.0")

    def test_shared_core_version_requires_a_string(self) -> None:
        with tempfile.TemporaryDirectory(prefix="claude-version-check-") as td:
            root = Path(td)
            (root / "shared-core.json").write_text(
                '{"identity":{"helper_version":120}}', encoding="utf-8"
            )
            with mock.patch.object(check_version, "REPO_ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "identity.helper_version"):
                    check_version.shared_core_version()

    def test_shared_core_mismatch_fails_release_check(self) -> None:
        versions = {
            "helper_version": "1.2.0",
            "skill_version": "1.2.0",
            "plugin_version": "1.2.0",
            "shared_core_version": "1.1.0",
            "check_changelog": (True, ""),
        }
        with ExitStack() as stack:
            stack.enter_context(mock.patch("sys.argv", ["check_version.py", "v1.2.0"]))
            stack.enter_context(mock.patch("builtins.print"))
            for name, value in versions.items():
                stack.enter_context(
                    mock.patch.object(check_version, name, return_value=value)
                )
            self.assertEqual(check_version.main(), 1)


class MarketplaceTests(unittest.TestCase):
    PLUGIN = {
        "name": "imessage-review",
        "version": "1.2.2",
        "description": "Read and triage iMessages.",
    }

    def check(
        self,
        marketplace: dict | None,
        plugin: dict | None = None,
    ) -> tuple[bool, str]:
        with tempfile.TemporaryDirectory(prefix="claude-marketplace-") as td:
            root = Path(td)
            plugin_dir = root / ".claude-plugin"
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "plugin.json").write_text(
                json.dumps(plugin or self.PLUGIN), encoding="utf-8"
            )
            if marketplace is not None:
                (plugin_dir / "marketplace.json").write_text(
                    json.dumps(marketplace), encoding="utf-8"
                )
            with mock.patch.object(check_version, "REPO_ROOT", root):
                return check_version.check_marketplace()

    def valid_manifest(self) -> dict:
        return {
            "name": "jeffhuber-plugins",
            "owner": {"name": "Jeff Huber"},
            "plugins": [
                {
                    "name": "imessage-review",
                    "source": "./",
                    "description": "Read and triage iMessages.",
                }
            ],
        }

    def test_consistent_manifest_passes(self) -> None:
        self.assertEqual(self.check(self.valid_manifest()), (True, ""))

    def test_missing_manifest_fails(self) -> None:
        valid, error = self.check(None)
        self.assertFalse(valid)
        self.assertIn("not found", error)

    def test_source_must_be_the_repository_root(self) -> None:
        manifest = self.valid_manifest()
        manifest["plugins"][0]["source"] = "./plugins/imessage-review"
        valid, error = self.check(manifest)
        self.assertFalse(valid)
        self.assertIn("source", error)

    def test_description_drift_fails(self) -> None:
        manifest = self.valid_manifest()
        manifest["plugins"][0]["description"] = "Stale description."
        valid, error = self.check(manifest)
        self.assertFalse(valid)
        self.assertIn("description", error)

    def test_entry_version_is_rejected(self) -> None:
        manifest = self.valid_manifest()
        manifest["plugins"][0]["version"] = "1.2.2"
        valid, error = self.check(manifest)
        self.assertFalse(valid)
        self.assertIn("single version source", error)

    def test_exactly_one_entry_is_required(self) -> None:
        manifest = self.valid_manifest()
        manifest["plugins"].append(dict(manifest["plugins"][0]))
        valid, error = self.check(manifest)
        self.assertFalse(valid)
        self.assertIn("exactly one", error)

    def test_release_check_fails_on_inconsistent_marketplace(self) -> None:
        versions = {
            "helper_version": "1.2.2",
            "skill_version": "1.2.2",
            "plugin_version": "1.2.2",
            "shared_core_version": "1.2.2",
            "check_changelog": (True, ""),
            "check_marketplace": (False, "marketplace drift"),
        }
        with ExitStack() as stack:
            stack.enter_context(mock.patch("sys.argv", ["check_version.py", "v1.2.2"]))
            stack.enter_context(mock.patch("builtins.print"))
            for name, value in versions.items():
                stack.enter_context(
                    mock.patch.object(check_version, name, return_value=value)
                )
            self.assertEqual(check_version.main(), 1)


if __name__ == "__main__":
    unittest.main()
