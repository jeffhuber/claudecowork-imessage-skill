from __future__ import annotations

import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = REPO_ROOT / "skills" / "imessage-review"


class PackagingTests(unittest.TestCase):
    def test_bootstrap_copies_every_required_asset(self) -> None:
        source = (SKILL_ROOT / "bootstrap.sh").read_text()
        for required in (
            "install.sh",
            "uninstall.sh",
            "com.jeffhuber.claudecowork-imessage.plist.template",
            "cowork_imessage_helper.c",
            "helper.py",
            "send_gate.py",
            "migrate_legacy_launchagent.py",
        ):
            self.assertIn(required, source)

        installer = (SKILL_ROOT / "install.sh").read_text()
        self.assertIn('SEND_GATE_PY="$BIN_DIR/send_gate.py"', installer)
        self.assertIn('[[ ! -f "$SEND_GATE_PY" ]]', installer)

    def test_claude_identity_does_not_claim_grok_resources(self) -> None:
        for name in ("install.sh", "uninstall.sh"):
            source = (SKILL_ROOT / name).read_text()
            self.assertIn("com.jeffhuber.claudecowork-imessage", source)
            self.assertNotIn("com.jeffhuber.grokbot-imessage", source)

        template = (
            SKILL_ROOT / "com.jeffhuber.claudecowork-imessage.plist.template"
        ).read_text()
        self.assertIn("<string>com.jeffhuber.claudecowork-imessage</string>", template)
        self.assertIn("claude-cowork-imessage-helper", template)


class LegacyMigrationTests(unittest.TestCase):
    def _write_plist(self, path: Path, program: str, watch: str) -> None:
        with path.open("wb") as stream:
            plistlib.dump(
                {
                    "Label": "com.user.cowork-imessage",
                    "ProgramArguments": [program],
                    "WatchPaths": [watch],
                },
                stream,
            )

    def _verify(self, plist: Path, program: str, watch: str) -> int:
        result = subprocess.run(
            [
                sys.executable,
                str(SKILL_ROOT / "tools" / "migrate_legacy_launchagent.py"),
                "--plist",
                str(plist),
                "--program",
                program,
                "--watch",
                watch,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode

    def test_only_exact_claude_install_can_claim_legacy_agent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="claude-imessage-legacy-") as td:
            root = Path(td)
            plist = root / "legacy.plist"
            claude_program = str(root / "claude" / "bin" / "cowork-imessage-helper")
            claude_watch = str(root / "claude" / "control" / "requests")
            self._write_plist(plist, claude_program, claude_watch)

            self.assertEqual(self._verify(plist, claude_program, claude_watch), 0)
            self.assertEqual(
                self._verify(
                    plist,
                    str(root / "grok" / "bin" / "cowork-imessage-helper"),
                    str(root / "grok" / "control" / "requests"),
                ),
                1,
            )


if __name__ == "__main__":
    unittest.main()
