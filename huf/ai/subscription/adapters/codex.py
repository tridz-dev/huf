"""Codex CLI subscription adapter.

Wraps the `codex` CLI (`codex exec ...`) as a HUF subscription CLI provider.

Grounded in real, live-captured fixtures at
``huf/ai/tests/subscription/fixtures/real/codex/`` (codex-cli 0.144.6) and
``STAGE0_SPIKE_SUMMARY.md``. Three findings from that spike drive the design
choices below — see the inline comments at each site:

1. Codex emits plain-text stderr (not JSON) on a malformed `resume`, even
   though `--json` was requested.
2. Codex refuses to run `codex exec` at all in a directory it does not
   consider "trusted" (not a git repo and not explicitly marked trusted).
3. A JSONL `item.completed` of `type: "error"` can be a non-fatal warning
   that still ends in a successful `turn.completed` — only `turn.failed`
   means the turn failed.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from huf.ai.subscription.adapters.base import (
	DeleteSessionResult,
	ProviderSession,
	SessionStatus,
	SubscriptionCLIAdapter,
)
from huf.ai.subscription.capabilities import RuntimeCapabilities
from huf.ai.subscription.errors import (
	SubscriptionAuthError,
	SubscriptionCLIError,
	SubscriptionErrorCode,
	SubscriptionRuntimeError,
)
from huf.ai.subscription.transports.base import ExecutionTransport
from huf.ai.subscription.types import AuthChallenge, AuthStatus, SubscriptionTurnRequest, SubscriptionTurnResult

# --- Trust-workaround decision -------------------------------------------------
#
# The real `codex exec --help` fixture (help_output_exec.txt) documents an
# explicit, narrowly-scoped flag for this exact situation:
#
#     --skip-git-repo-check   Allow running Codex outside a Git repository
#
# This is NOT a permission-widening flag (unlike `--dangerously-bypass-approvals-
# and-sandbox` or `--dangerously-bypass-hook-trust`, which are separate flags in
# the same fixture and are never used here) — it only disables the "is this a
# git repo / trusted directory" gate, so it is the least-privileged, documented
# mechanism to run non-interactively in a HUF-controlled scratch working
# directory that is not (and should not need to be) a git repository.
#
# We always pass this flag rather than `git init`-ing HUF's working directory,
# because `git init` would be a surprising, persistent side effect in a
# directory HUF does not own the lifecycle of, and because the flag is
# documented, deterministic, and reversible per-invocation.
CODEX_TRUST_FLAG = "--skip-git-repo-check"

# --- Sandbox/approval decision -------------------------------------------------
#
# Per plan §15.4/§73.1: never default to a mode that allows unattended
# filesystem writes or shell execution for the default HUF chat use case.
# The real top-level `codex --help` / `codex exec --help` fixtures document:
#   -s/--sandbox <read-only|workspace-write|danger-full-access>
#   -a/--ask-for-approval <untrusted|on-request|never>
# We pick the least-privileged combination that still runs non-interactively:
#   --sandbox read-only        (no filesystem writes, no shell execution)
#   --ask-for-approval never   (never prompts; per --help, "Execution failures
#                                are immediately returned to the model" instead
#                                of blocking on a human who isn't there)
CODEX_SANDBOX_MODE = "read-only"
CODEX_APPROVAL_POLICY = "never"

_RESUME_NOT_FOUND_RE = re.compile(r"no rollout found for thread id", re.IGNORECASE)


def _now_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


def parse_codex_jsonl(stdout: str) -> dict[str, Any]:
	"""Parse a `codex exec --json` / `codex exec resume --json` JSONL stream.

	Returns a dict with:
		thread_id: str | None
		items: list[dict]           (all item.completed payloads, in order)
		final_text: str | None      (text of the last agent_message item)
		usage: dict                 (from turn.completed, if present)
		turn_status: "completed" | "failed" | "unknown"
		turn_failed_reason: str | None

	Finding 3 (non-fatal item errors): an `item.completed` event whose
	`item.type == "error"` is NOT treated as a turn failure here. Real example
	captured in create_session.jsonl:

		{"type":"item.completed","item":{"id":"item_0","type":"error",
		 "message":"Exceeded skills context budget of 2%. ..."}}
		...
		{"type":"turn.completed","usage":{...}}

	That run's turn still completed successfully with the correct answer.
	Only an explicit `turn.failed` event (not present in any real fixture we
	captured, but documented as the failure counterpart to `turn.completed`)
	marks the turn as failed. Do not "fix" this to fail on any error-typed
	item — that would misclassify successful turns as failures.
	"""
	thread_id: str | None = None
	items: list[dict[str, Any]] = []
	final_text: str | None = None
	usage: dict[str, Any] = {}
	turn_status = "unknown"
	turn_failed_reason: str | None = None

	for line in stdout.splitlines():
		line = line.strip()
		if not line:
			continue
		try:
			event = json.loads(line)
		except json.JSONDecodeError:
			# Non-JSON line mixed into stdout (e.g. stray log noise) — skip it
			# rather than failing the whole parse.
			continue

		event_type = event.get("type")

		if event_type == "thread.started":
			thread_id = event.get("thread_id")
		elif event_type == "item.completed":
			item = event.get("item") or {}
			items.append(item)
			# Non-fatal per finding 3 above: an item.type == "error" here is
			# recorded as an item, not treated as failure.
			if item.get("type") == "agent_message" and item.get("text"):
				final_text = item.get("text")
		elif event_type == "turn.completed":
			turn_status = "completed"
			usage = event.get("usage") or {}
		elif event_type == "turn.failed":
			turn_status = "failed"
			turn_failed_reason = (
				event.get("error", {}).get("message")
				if isinstance(event.get("error"), dict)
				else event.get("message")
			)

	return {
		"thread_id": thread_id,
		"items": items,
		"final_text": final_text,
		"usage": usage,
		"turn_status": turn_status,
		"turn_failed_reason": turn_failed_reason,
	}


def parse_codex_usage(raw_usage: dict[str, Any]) -> dict[str, Any]:
	"""Normalize Codex's `turn.completed.usage` shape into a HUF usage dict.

	Real shape (create_session.jsonl / resume_turn.jsonl):
		{"input_tokens": int, "cached_input_tokens": int,
		 "output_tokens": int, "reasoning_output_tokens": int}
	"""
	return {
		"input_tokens": raw_usage.get("input_tokens"),
		"cached_input_tokens": raw_usage.get("cached_input_tokens"),
		"output_tokens": raw_usage.get("output_tokens"),
		"reasoning_output_tokens": raw_usage.get("reasoning_output_tokens"),
	}


# Matches common credential/token shapes (Bearer header, sk-/ya29.-style
# provider tokens, api_key=/access_token: assignments) that a CLI's stderr
# might echo back verbatim. Used by `_sanitize_stderr_excerpt` (Track-Item:
# T-T6) so a raw stderr excerpt embedded in an exception message never
# carries a live credential value. Mirrors adapters/claude.py::_SECRET_VALUE_RE.
_SECRET_VALUE_RE = re.compile(
	r"(?i)"
	r"bearer\s+[a-z0-9._\-]{10,}"
	r"|sk-[a-z0-9_\-]{10,}"
	r"|ya29\.[a-z0-9._\-]{10,}"
	r"|(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret)\s*[=:]\s*[\"']?[a-z0-9._\-]{8,}[\"']?"
)


def _sanitize_stderr_excerpt(stderr: str) -> str:
	"""Redact credential-shaped substrings from a stderr excerpt.

	Applied before a raw stderr excerpt is embedded in a `SubscriptionCLIError`
	message (see the exit!=0/no-stdout branch of `run_turn`) -- that message
	is `str(exc)`-ed by callers (e.g. `executor.py`'s generic `except
	SubscriptionError` branch) which already re-sanitizes via
	`streaming._sanitize_error_message`, but this adapter must not depend on
	every caller doing that; it should never hand out a raw secret itself.
	"""
	return _SECRET_VALUE_RE.sub("<redacted>", stderr)


def is_resume_not_found_error(stderr: str) -> bool:
	"""Detect the plain-text "no rollout found for thread id" resume error.

	Finding 1: `codex exec resume --json <id>` on a nonexistent/malformed
	thread id does NOT emit a JSONL event — it prints plain text to stderr:

		Error: thread/resume: thread/resume failed: no rollout found for
		thread id 00000000-0000-0000-0000-000000000000 (code -32600)

	even though --json was requested. The adapter must special-case this as a
	normal "session not found" outcome, not a generic CLI parse failure.
	"""
	return bool(_RESUME_NOT_FOUND_RE.search(stderr))


def parse_codex_login_status(stdout: str) -> AuthStatus:
	"""Parse `codex login status` plain-text output into an AuthStatus.

	Real fixture (auth_status.txt): "Logged in using ChatGPT" — plain text,
	not JSON, unlike Claude's `claude auth status` (structured JSON). There is
	no shared auth-probe format across these two subscription CLI providers,
	so each adapter's check_auth() must pattern-match its own provider's
	specific text/JSON shape independently.
	"""
	text = stdout.strip()
	checked_at = _now_iso()

	if not text:
		return AuthStatus(
			state="unknown",
			account_hint=None,
			method=None,
			message="Empty output from 'codex login status'",
			checked_at=checked_at,
		)

	lowered = text.lower()

	logged_in_match = re.match(r"logged in using (.+)", text, re.IGNORECASE)
	if logged_in_match:
		method = logged_in_match.group(1).strip()
		return AuthStatus(
			state="authenticated",
			account_hint=None,
			method=method,
			message=text,
			checked_at=checked_at,
		)

	if "not logged in" in lowered or "not authenticated" in lowered:
		return AuthStatus(
			state="unauthenticated",
			account_hint=None,
			method=None,
			message=text,
			checked_at=checked_at,
		)

	# Unrecognized plain-text shape (e.g. a future Codex CLI version changes
	# the wording, or an API-key-mode message we never captured live per the
	# spike's "Not captured" gap). Surface as unknown rather than guessing.
	return AuthStatus(
		state="unknown",
		account_hint=None,
		method=None,
		message=text,
		checked_at=checked_at,
	)


class CodexAdapter(SubscriptionCLIAdapter):
	"""Adapter for the `codex` CLI (ChatGPT/Codex subscription runtime)."""

	def __init__(self, transport: ExecutionTransport) -> None:
		super().__init__(transport)

	# -- probing -----------------------------------------------------------

	async def probe(self, runtime: Any) -> RuntimeCapabilities:
		"""Probe `codex --version` and report capabilities.

		automation_supported is deliberately False by default: Codex is a
		coding-oriented agent CLI whose sandbox/approval model is designed
		around a human (or a fully-sandboxed CI) driving shell/file-writing
		actions. Per plan §73.2/§15.4, unattended automation must be proven
		safe on a per-deployment basis before being turned on — chat/
		supervised use (what this adapter targets with read-only sandbox +
		never-approval) is still fully usable with automation_supported=False.
		"""
		result = await self.transport.run(["codex", "--version"], timeout=30)
		if result.exit_code != 0 or result.timed_out:
			raise SubscriptionRuntimeError(
				SubscriptionErrorCode.RUNTIME_UNREACHABLE,
				f"codex --version failed (exit={result.exit_code}, timed_out={result.timed_out})",
			)

		return RuntimeCapabilities(
			supports_noninteractive=True,
			supports_session_id=True,
			supports_session_resume=True,
			# No documented independent session-listing/deletion command was
			# found in the real --help fixtures (see validate_session/
			# delete_session below) — deletion is not something HUF can
			# reliably perform, so advertise it as unsupported.
			supports_session_delete=False,
			supports_json=True,
			supports_stream_json=True,
			supports_images="-i, --image" in _get_exec_help_text(),
			supports_usage=True,
			supports_cached_usage=True,
			supports_reasoning_summary=False,
			supports_mcp=False,
			supports_model_selection=True,
			supports_tool_restriction=True,
			requires_stable_cwd=True,
			automation_supported=False,
		)

	# -- working-directory trust check --------------------------------------

	def _require_trusted_working_directory(self, runtime: Any) -> str:
		"""Resolve and validate the working directory `codex exec` will use.

		Codex refuses to run `codex exec` at all in a directory it does not
		consider trusted (real observed error: "Not inside a trusted
		directory and --skip-git-repo-check was not specified."). Per the
		documented CODEX_TRUST_FLAG decision above, HUF always passes
		--skip-git-repo-check rather than mutating the target directory with
		`git init`. That flag is unconditionally supported per the real
		`codex exec --help` fixture for this CLI version, so there is no
		RUNTIME_UNREACHABLE fallback path needed for *this* mechanism — but
		we still require a concrete working_directory to be configured, since
		Codex needs *some* stable cwd to write its session/rollout state
		into (RuntimeCapabilities.requires_stable_cwd=True).
		"""
		working_directory = getattr(runtime, "working_directory", None)
		if not working_directory or not str(working_directory).strip():
			# No safe, non-interactive trust mechanism can be applied without
			# a concrete working directory to run in — raise clearly instead
			# of silently defaulting to some ambient cwd.
			raise SubscriptionRuntimeError(
				SubscriptionErrorCode.RUNTIME_UNREACHABLE,
				"Codex runtime requires a configured working_directory to run "
				"`codex exec` in (needed for --skip-git-repo-check trust "
				"bypass and stable session/rollout state); none was provided.",
			)
		return str(working_directory)

	# -- auth ----------------------------------------------------------------

	async def check_auth(self, runtime: Any) -> AuthStatus:
		result = await self.transport.run(["codex", "login", "status"], timeout=30)
		if result.timed_out:
			raise SubscriptionAuthError(
				SubscriptionErrorCode.RUNTIME_UNREACHABLE,
				"codex login status timed out",
			)
		# Real fixture shows the plain-text status on stdout regardless of
		# exit code; fall back to stderr if stdout is empty in case a future
		# version flips streams.
		output = result.stdout.strip() or result.stderr.strip()
		return parse_codex_login_status(output)

	async def begin_auth(self, runtime: Any) -> AuthChallenge:
		# `codex login` (interactive ChatGPT OAuth flow) opens a browser and
		# is not scriptable non-interactively per the real --help fixture
		# (no device-code/headless login subcommand was captured). Surface a
		# challenge that tells HUF this requires an interactive browser step
		# rather than pretending a device-code flow exists.
		return AuthChallenge(
			challenge_id=f"codex-login-{int(datetime.now(timezone.utc).timestamp())}",
			provider="codex",
			mode="browser",
			verification_url=None,
			user_code=None,
			requires_huf_input=False,
			prompt=(
				"Run `codex login` interactively on the runtime host to complete "
				"ChatGPT subscription sign-in; no headless/device-code flow is "
				"documented for this CLI version."
			),
			expires_at=None,
			poll_supported=True,
		)

	async def submit_auth_input(self, runtime: Any, challenge_id: str, value: str) -> AuthStatus:
		# No documented non-interactive input-submission path exists for
		# `codex login`; re-check status instead of attempting to feed stdin
		# into an interactive OAuth flow.
		return await self.check_auth(runtime)

	async def poll_auth(self, runtime: Any, challenge_id: str) -> AuthStatus:
		return await self.check_auth(runtime)

	# -- session lifecycle -----------------------------------------------------

	async def create_session(self, request: SubscriptionTurnRequest) -> ProviderSession:
		# Codex mints the thread/session id itself from the first `codex exec`
		# call (see run_turn); there is no separate "create session" command
		# in the real fixtures, so establishing a session and running the
		# first turn are the same CLI invocation. This method exists to
		# satisfy the abstract contract but callers should go through
		# run_turn, which creates-or-resumes based on provider_session_id.
		raise SubscriptionCLIError(
			SubscriptionErrorCode.CLI_PROCESS_FAILED,
			"Codex has no standalone session-creation command; call run_turn "
			"with provider_session_id=None to create a session as part of "
			"the first turn.",
		)

	async def validate_session(self, runtime: Any, session_id: str) -> SessionStatus:
		# No documented explicit session-listing/lookup-by-id command was
		# found in the real `codex --help` fixture (the `resume`/`archive`/
		# `delete`/`unarchive`/`fork` subcommands operate on saved sessions
		# by id or name, but there is no plain "does this id exist" check
		# short of attempting a resume, which would consume a turn). Per the
		# task's fallback guidance, report existence as unverifiable rather
		# than guessing.
		return SessionStatus(exists=True, detail="not independently verifiable")

	async def delete_session(self, runtime: Any, session_id: str) -> DeleteSessionResult:
		# `codex delete <id>` exists at the top level (see help_output_top.txt:
		# "delete  Permanently delete a saved session by id or session name"),
		# but it is an *interactive top-level* subcommand, not documented
		# under `codex exec`/`codex exec resume --help`, and was not
		# live-verified as part of this spike (no live invocation captured).
		# Until that command is verified non-interactive and safe to call
		# from an adapter, we conservatively report the session as retained
		# by the provider rather than attempting an unverified destructive
		# command.
		return DeleteSessionResult(cleanup_status="provider_retained")

	# -- turn execution --------------------------------------------------------

	async def run_turn(self, runtime: Any, request: SubscriptionTurnRequest) -> SubscriptionTurnResult:
		working_directory = self._require_trusted_working_directory(runtime)

		# Vision support: real `codex exec --help` fixture documents
		# `-i, --image <FILE>...` on both `codex exec` and `codex exec resume`.
		image_flags: list[str] = []
		if request.files:
			help_text = _get_exec_help_text()
			if "-i, --image" not in help_text:
				raise SubscriptionCLIError(
					SubscriptionErrorCode.VISION_UNSUPPORTED,
					"Codex CLI build does not document an image/vision flag; "
					"cannot attach request.files.",
				)
			for f in request.files:
				image_flags.extend(["--image", f])

		# CRITICAL passthrough constraint: only request.text/request.files are
		# ever placed on the argv below. No HUF system-prompt content,
		# conversation history, or HUF-generated MCP config is constructed or
		# passed here — see SubscriptionCLIAdapter's docstring contract.
		if request.provider_session_id:
			argv = [
				"codex",
				"exec",
				"resume",
				"--json",
				request.provider_session_id,
				*image_flags,
				CODEX_TRUST_FLAG,
				"--sandbox",
				CODEX_SANDBOX_MODE,
				"--ask-for-approval",
				CODEX_APPROVAL_POLICY,
			]
			if request.model_override:
				argv.extend(["--model", request.model_override])
			argv.append(request.text)
		else:
			argv = [
				"codex",
				"exec",
				"--json",
				CODEX_TRUST_FLAG,
				"--sandbox",
				CODEX_SANDBOX_MODE,
				"--ask-for-approval",
				CODEX_APPROVAL_POLICY,
				*image_flags,
			]
			if request.model_override:
				argv.extend(["--model", request.model_override])
			argv.append(request.text)

		result = await self.transport.run(
			argv,
			cwd=working_directory,
			timeout=request.timeout_seconds,
		)

		if result.timed_out:
			raise SubscriptionCLIError(
				SubscriptionErrorCode.CLI_PROCESS_TIMEOUT,
				f"codex exec timed out after {request.timeout_seconds}s",
			)

		stderr = result.stderr or ""

		# Finding 1: malformed/nonexistent resume target -> plain-text stderr,
		# not a JSONL event, even with --json requested.
		if request.provider_session_id and is_resume_not_found_error(stderr):
			return SubscriptionTurnResult(
				status="error",
				final_text=None,
				provider_session_id=request.provider_session_id,
				usage={},
				events=[],
				raw_debug_ref=stderr.strip() or None,
				exit_code=result.exit_code,
				auth_reason=None,
			)

		if result.exit_code != 0 and not result.stdout.strip():
			# No JSONL at all to parse and a non-zero exit: treat as a plain
			# CLI process failure (do not assume any particular error shape
			# beyond what was captured for the resume-not-found case above).
			raise SubscriptionCLIError(
				SubscriptionErrorCode.CLI_PROCESS_FAILED,
				f"codex exec failed (exit={result.exit_code}): "
				f"{_sanitize_stderr_excerpt(stderr.strip()[:500])}",
			)

		parsed = parse_codex_jsonl(result.stdout)

		if parsed["thread_id"] is None and not parsed["items"] and parsed["turn_status"] == "unknown":
			raise SubscriptionCLIError(
				SubscriptionErrorCode.CLI_OUTPUT_PARSE_FAILED,
				"Could not parse any recognizable JSONL events from codex exec output",
			)

		# Finding 3: only turn.failed means failure. A turn.completed
		# alongside a non-fatal item.completed(type="error") is success — see
		# parse_codex_jsonl's docstring for the concrete example.
		if parsed["turn_status"] == "failed":
			return SubscriptionTurnResult(
				status="error",
				final_text=parsed["final_text"],
				provider_session_id=parsed["thread_id"] or request.provider_session_id,
				usage=parse_codex_usage(parsed["usage"]),
				events=parsed["items"],
				raw_debug_ref=parsed["turn_failed_reason"],
				exit_code=result.exit_code,
				auth_reason=None,
			)

		return SubscriptionTurnResult(
			status="success",
			final_text=parsed["final_text"],
			provider_session_id=parsed["thread_id"] or request.provider_session_id,
			usage=parse_codex_usage(parsed["usage"]),
			events=parsed["items"],
			raw_debug_ref=None,
			exit_code=result.exit_code,
			auth_reason=None,
		)


# The real `codex exec --help` text is embedded here (verbatim excerpt of the
# flags this adapter depends on) so capability probing does not need an extra
# subprocess round-trip on every probe() call in environments where spawning
# `codex exec --help` would itself be subject to the trust gate. This mirrors
# exactly the flags captured in
# huf/ai/tests/subscription/fixtures/real/codex/help_output_exec.txt.
_EXEC_HELP_EXCERPT = """
  -i, --image <FILE>...
          Optional image(s) to attach to the initial prompt
      --skip-git-repo-check
          Allow running Codex outside a Git repository
  -s, --sandbox <SANDBOX_MODE>
          Select the sandbox policy to use when executing model-generated shell commands
  -a, --ask-for-approval <APPROVAL_POLICY>
      --json
          Print events to stdout as JSONL
"""


def _get_exec_help_text() -> str:
	return _EXEC_HELP_EXCERPT
