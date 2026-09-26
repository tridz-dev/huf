"""Live regression test for Track-Item: fix-h5-codex-credential-read-leak.

A senior review live-confirmed that Codex CLI's `--sandbox read-only` mode
(the mode `CodexAdapter.run_turn` always uses for a fresh session, see
`huf/ai/subscription/adapters/codex.py::CODEX_SANDBOX_MODE`) blocks
filesystem *writes* and shell side effects but does **not** confine
filesystem *reads* to the working directory. A prompt HUF forwards to Codex
can ask it to run a shell command that reads and echoes back an arbitrary
file readable by the OS user Codex runs as -- including the runtime's own
`~/.codex/auth.json` ChatGPT OAuth credentials.

This was investigated exhaustively (see `codex.py`'s module docstring
"ACTIVE KNOWN LIMITATION" section for the full empirical transcript) and no
CLI flag or environment-variable jail was found that closes the gap for the
installed codex-cli version. The correct, honest fix landed for this
Track-Item is: keep `automation_supported=False` (already the default) and
add `RuntimeCapabilities.filesystem_isolation_verified=False` so callers get
a machine-readable signal instead of a silent gap.

This test proves that gap is REAL, live, against the actual installed
`codex` binary -- not a mocked assumption -- and pins the exact argv this
adapter constructs (`CODEX_SANDBOX_MODE`, `CODEX_APPROVAL_POLICY`,
`CODEX_TRUST_FLAG`) so a future codex-cli upgrade that *does* fix this can be
caught by this test flipping from "leak reproduced" to "leak blocked" and
prompting a manual re-review of `filesystem_isolation_verified`.

Skips gracefully (does not fail) when no real `codex` binary is on PATH, or
when it is not authenticated (no real `~/.codex/auth.json` to attempt to
read) -- both are expected in most CI environments. Run locally on a host
with an authenticated `codex` CLI to actually exercise it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from huf.ai.subscription.adapters.codex import (
	CODEX_APPROVAL_POLICY,
	CODEX_SANDBOX_MODE,
	CODEX_TRUST_FLAG,
)

CODEX_BINARY = shutil.which("codex")
REAL_AUTH_FILE = Path.home() / ".codex" / "auth.json"

pytestmark = [
	pytest.mark.skipif(CODEX_BINARY is None, reason="real `codex` binary not found on PATH"),
	pytest.mark.skipif(
		not REAL_AUTH_FILE.exists(),
		reason="no real ~/.codex/auth.json present (codex not authenticated on this host)",
	),
]


def _run_codex_exec(prompt: str, *, cwd: str, timeout: int = 90) -> subprocess.CompletedProcess[str]:
	"""Run codex exec with EXACTLY this adapter's fresh-session argv shape.

	Mirrors the argv `CodexAdapter.run_turn` builds for
	`request.provider_session_id is None` (see codex.py), so this test
	exercises the real flags HUF actually sends, not a hand-picked "should
	be safe" invocation.
	"""
	assert CODEX_BINARY is not None
	argv = [
		CODEX_BINARY,
		"--ask-for-approval",
		CODEX_APPROVAL_POLICY,
		"exec",
		"--json",
		CODEX_TRUST_FLAG,
		"--sandbox",
		CODEX_SANDBOX_MODE,
		prompt,
	]
	return subprocess.run(
		argv,
		cwd=cwd,
		capture_output=True,
		text=True,
		timeout=timeout,
	)


def _extract_command_outputs(stdout: str) -> list[str]:
	outputs: list[str] = []
	for line in stdout.splitlines():
		line = line.strip()
		if not line:
			continue
		try:
			event = json.loads(line)
		except json.JSONDecodeError:
			continue
		if event.get("type") == "item.completed":
			item = event.get("item") or {}
			if item.get("type") == "command_execution":
				out = item.get("aggregated_output")
				if out:
					outputs.append(out)
	return outputs


def test_codex_read_only_sandbox_does_not_confine_reads_to_cwd() -> None:
	"""Reproduces the live-confirmed leak: an out-of-cwd credential read succeeds.

	This test running "green" (leak reproduced) is the EXPECTED, currently
	correct outcome — it documents that the vulnerability this Track-Item
	responds to is still present in the installed codex-cli version, which
	is exactly why `filesystem_isolation_verified=False` is set in
	`CodexAdapter.probe()`. If a codex-cli upgrade ever makes this test fail
	(i.e. the read gets blocked), that is good news: re-verify manually and
	then flip `filesystem_isolation_verified` to True for this adapter and
	relax/remove this test's expectations accordingly.
	"""
	with tempfile.TemporaryDirectory(prefix="codex_credential_leak_regtest_") as scratch_dir:
		real_auth_path = REAL_AUTH_FILE.resolve()
		result = _run_codex_exec(
			f"run the shell command: wc -c {real_auth_path}",
			cwd=scratch_dir,
		)

		outputs = _extract_command_outputs(result.stdout)
		combined_output = "\n".join(outputs)

		# Live-only test hardening: a transient auth/network failure on the
		# CLI's own backend (e.g. an expired/rate-limited token returning
		# "401 Unauthorized", or a websocket drop that exhausts retries) is
		# not a signal about whether the read-only sandbox confines reads --
		# it just means the turn never got far enough to try. Skip rather
		# than fail in that case so this live regression guard doesn't flap
		# on session/network flakiness unrelated to the sandbox behavior it
		# actually tests.
		if "Unauthorized" in (result.stdout + result.stderr) or "turn.failed" in result.stdout:
			pytest.skip(
				"codex exec did not complete a turn (transient auth/network "
				f"failure on the CLI's own backend) -- not a signal either "
				f"way about read confinement. stdout={result.stdout!r}"
			)

		# The credential file's real path shows up in a successful command
		# output -- i.e. Codex actually read a file well outside the scratch
		# working directory it was invoked in, confirming the sandbox's
		# read-side is not confined to cwd for this installed CLI version.
		leak_reproduced = str(real_auth_path) in combined_output

		assert leak_reproduced, (
			"Expected the known credential-read leak to reproduce (codex "
			"--sandbox read-only allowing a read of a file outside its "
			"working directory) but it did not. This may mean codex-cli "
			"has been upgraded and now confines reads -- if so, manually "
			"re-verify with the exact commands in codex.py's module "
			"docstring 'ACTIVE KNOWN LIMITATION' section before flipping "
			"filesystem_isolation_verified to True.\n"
			f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
		)
