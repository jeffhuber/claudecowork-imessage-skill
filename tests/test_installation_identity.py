from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = REPO_ROOT / "skills" / "imessage-review"


class PackagingTests(unittest.TestCase):
    def test_installers_skip_an_unsupported_path_python(self) -> None:
        with tempfile.TemporaryDirectory(prefix="claude-imessage-python-") as td:
            fake_bin = Path(td)
            unsupported = fake_bin / "python3"
            unsupported.write_text("#!/bin/sh\nexit 97\n", encoding="utf-8")
            unsupported.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
            selector = SKILL_ROOT / "tools" / "select_python.sh"

            def select(candidate: str | None = None) -> subprocess.CompletedProcess[str]:
                run_env = env.copy()
                if candidate is None:
                    run_env.pop("IMESSAGE_PYTHON", None)
                else:
                    run_env["IMESSAGE_PYTHON"] = candidate
                return subprocess.run(
                    [
                        "bash",
                        "-c",
                        'source "$1"; find_supported_python',
                        "selector-test",
                        str(selector),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    env=run_env,
                )

            fallback = select()
            self.assertEqual(fallback.returncode, 0, fallback.stderr)
            self.assertNotEqual(Path(fallback.stdout.strip()), unsupported)

            override = select(sys.executable)
            self.assertEqual(override.returncode, 0, override.stderr)
            self.assertEqual(override.stdout.strip(), sys.executable)

            for invalid in (str(unsupported), "", "python3"):
                failed = select(invalid)
                self.assertNotEqual(failed.returncode, 0, invalid)
                self.assertEqual(failed.stdout, "", invalid)

            for name in ("install.sh", "install-hardened.sh"):
                source = (SKILL_ROOT / name).read_text(encoding="utf-8")
                self.assertIn('source "$PYTHON_SELECTOR"', source, name)
                self.assertIn(
                    'PYTHON3_PATH="$(find_supported_python)"', source, name
                )
            hardened = (SKILL_ROOT / "install-hardened.sh").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                'hardened_python_is_trusted "$PYTHON3_PATH"', hardened
            )

    @unittest.skipUnless(sys.platform == "darwin", "macOS stat semantics")
    def test_hardened_python_rejects_user_writable_paths(self) -> None:
        selector = SKILL_ROOT / "tools" / "select_python.sh"

        def trusted(path: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    "bash",
                    "-c",
                    'source "$1"; hardened_python_is_trusted "$2"',
                    "selector-test",
                    str(selector),
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        trusted_python = Path("/usr/bin/python3")
        if not trusted_python.is_file():
            self.skipTest("/usr/bin/python3 is unavailable on this runner")

        self.assertEqual(trusted(trusted_python).returncode, 0)
        with tempfile.TemporaryDirectory(prefix="claude-untrusted-python-") as td:
            untrusted = Path(td) / "python3"
            untrusted.write_bytes(trusted_python.read_bytes())
            untrusted.chmod(0o755)
            self.assertNotEqual(trusted(untrusted).returncode, 0)
            symlinked = Path(td) / "python-link"
            symlinked.symlink_to("/usr/bin/python3")
            self.assertNotEqual(trusted(symlinked).returncode, 0)

    def test_bootstrap_copies_every_required_asset(self) -> None:
        source = (SKILL_ROOT / "bootstrap.sh").read_text()
        for required in (
            "install.sh",
            "install-hardened.sh",
            "uninstall.sh",
            "uninstall-hardened.sh",
            "com.jeffhuber.claudecowork-imessage.plist.template",
            "imessage_helper.c",
            "confirm_imessage_send.m",
            "helper.py",
            "send_gate.py",
            "doctor.py",
            "configure_allowlist.py",
            "migrate_legacy_launchagent.py",
            "select_python.sh",
        ):
            self.assertIn(required, source)

        installer = (SKILL_ROOT / "install.sh").read_text()
        self.assertIn('SEND_GATE_PY="$BIN_DIR/send_gate.py"', installer)
        self.assertIn('[[ ! -f "$SEND_GATE_PY" ]]', installer)

    def test_bootstrap_produces_a_complete_installable_bridge(self) -> None:
        with tempfile.TemporaryDirectory(prefix="claude-imessage-bootstrap-") as td:
            bridge = Path(td) / "bridge"
            result = subprocess.run(
                ["bash", str(SKILL_ROOT / "bootstrap.sh"), str(bridge)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            for relative in (
                "install.sh",
                "install-hardened.sh",
                "uninstall.sh",
                "uninstall-hardened.sh",
                "com.jeffhuber.claudecowork-imessage.plist.template",
                "bin/imessage_helper.c",
                "bin/confirm_imessage_send.m",
                "bin/helper.py",
                "bin/send_gate.py",
                "tools/doctor.py",
                "tools/configure_allowlist.py",
                "tools/migrate_legacy_launchagent.py",
                "tools/select_python.sh",
                "contacts/allowed_chats.txt.template",
                "contacts/blocked_chats.txt.template",
            ):
                self.assertTrue((bridge / relative).is_file(), relative)

            for relative in (
                "install.sh",
                "install-hardened.sh",
                "uninstall.sh",
                "uninstall-hardened.sh",
            ):
                self.assertTrue(os.access(bridge / relative, os.X_OK), relative)

    def test_claude_identity_does_not_claim_grok_resources(self) -> None:
        for name in (
            "install.sh",
            "install-hardened.sh",
            "uninstall.sh",
            "uninstall-hardened.sh",
        ):
            source = (SKILL_ROOT / name).read_text()
            self.assertIn("com.jeffhuber.claudecowork-imessage", source)
            self.assertNotIn("com.jeffhuber.grokbot-imessage", source)

        template = (
            SKILL_ROOT / "com.jeffhuber.claudecowork-imessage.plist.template"
        ).read_text()
        self.assertIn("<string>com.jeffhuber.claudecowork-imessage</string>", template)
        self.assertIn("claude-cowork-imessage-helper", template)

    def test_claude_and_grok_resource_contracts_are_disjoint(self) -> None:
        claude = {
            "com.jeffhuber.claudecowork-imessage",
            "claude-cowork-imessage-helper",
            "claude-cowork-imessage-confirm",
            "/Library/Application Support/ClaudeCoworkIMessage",
            "CLAUDE_COWORK_IMESSAGE_BRIDGE",
        }
        grok = {
            "com.jeffhuber.grokbot-imessage",
            "grokbot-imessage-helper",
            "grokbot-imessage-confirm",
            "/Library/Application Support/GrokBotIMessage",
            "GROKBOT_IMESSAGE_BRIDGE",
        }
        self.assertTrue(claude.isdisjoint(grok))

        shipped = "\n".join(
            (SKILL_ROOT / name).read_text()
            for name in (
                "install.sh",
                "install-hardened.sh",
                "uninstall.sh",
                "uninstall-hardened.sh",
                "com.jeffhuber.claudecowork-imessage.plist.template",
            )
        )
        for resource in claude:
            self.assertIn(resource, shipped)
        for resource in grok:
            self.assertNotIn(resource, shipped)

    def test_uninstallers_never_remove_the_legacy_shared_agent(self) -> None:
        for name in ("uninstall.sh", "uninstall-hardened.sh"):
            self.assertNotIn(
                "com.user.cowork-imessage", (SKILL_ROOT / name).read_text()
            )


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

    def test_non_dictionary_legacy_plist_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="claude-imessage-legacy-") as td:
            plist = Path(td) / "legacy.plist"
            with plist.open("wb") as stream:
                plistlib.dump(["not", "a", "launch-agent"], stream)

            self.assertEqual(self._verify(plist, "/tmp/helper", "/tmp/requests"), 1)


if __name__ == "__main__":
    unittest.main()
