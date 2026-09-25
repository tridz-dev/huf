"""Claude Code CLI adapter for the subscription CLI provider system.

Ground truth for every flag/shape used here is the live-captured fixture set at
``huf/ai/tests/subscription/fixtures/real/claude/`` (see
``STAGE0_SPIKE_SUMMARY.md`` in the track directory). Nothing here is guessed
beyond what those fixtures (or their ``.meta.md`` notes) document; anywhere the
spike could not capture live behavior, the code says so in a comment.

Passthrough constraint (see ``adapters/base.py``): this adapter never builds a
system prompt from HUF Agent instructions, never attaches HUF conversation
history, and never wires an HUF-generated MCP config or tool schema. Only the
current turn's ``text``/``files`` from ``SubscriptionTurnRequest`` are ever
sent to the CLI. ``--strict-mcp-config`` is passed with no ``--mcp-config``
value, which makes Claude ignore ambient project/user MCP servers entirely
(fixture: ``help_output.txt`` documents both flags) -- this is a safety
measure, not a passthrough of any config.
"""

from __future__ import annotations

import json
import re
import uuid
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
	SubscriptionError,
	SubscriptionErrorCode,
)
from huf.ai.subscription.types import AuthChallenge, AuthStatus, SubscriptionTurnRequest, SubscriptionTurnResult

# Flags confirmed in huf/ai/tests/subscription/fixtures/real/claude/help_output.txt
_FLAG_PRINT = "-p"
_FLAG_OUTPUT_FORMAT = "--output-format"
_FLAG_SESSION_ID = "--session-id"
_FLAG_RESUME = "--resume"
_FLAG_STRICT_MCP_CONFIG = "--strict-mcp-config"
_FLAG_RESTRICTED = "--restricted"
_FLAG_MODEL = "--model"

_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+)")

# Substrings from the REAL captured malformed-resume error
# (fixtures/real/claude/error_malformed_resume.txt):
#   'Error: --resume requires a valid session ID or session title when used
#    with --print. ... Provided value "<id>" is not a UUID and does not match
#    any session title.'
_RESUME_NOT_FOUND_MARKERS = ("is not a uuid", "does not match")

# Matches common credential/token shapes that a CLI's stderr/stdout might
# echo back verbatim (e.g. from an underlying HTTP client's error message):
# `Authorization: Bearer <token>`, an Anthropic/OpenAI-style `sk-...` secret
# key, a Google OAuth `ya29....` access token, or an `api_key=`/
# `access_token:`-style assignment. Used by `_sanitize` (Track-Item: T-T6)
# so adapter-classified error text never carries a live credential value.
_SECRET_VALUE_RE = re.compile(
	r"(?i)"
	r"bearer\s+[a-z0-9._\-]{10,}"
	r"|sk-[a-z0-9_\-]{10,}"
	r"|ya29\.[a-z0-9._\-]{10,}"
	r"|(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret)\s*[=:]\s*[\"']?[a-z0-9._\-]{8,}[\"']?"
)


class ClaudeAdapter(SubscriptionCLIAdapter):
	"""Adapter for the Claude Code CLI (``claude``) subscription runtime.

	See module docstring for the fixture-grounding rules this implementation
	follows.
	"""

	# Fallback executable name used only where no `runtime` object is available
	# (create_session/run_turn per the base class contract take a bare
	# SubscriptionTurnRequest with no runtime handle). probe/check_auth/etc.
	# prefer `runtime.cli_path` when given, matching how other adapters in
	# this codebase resolve the CLI path.
	DEFAULT_EXECUTABLE = "claude"

	def _executable(self, runtime: Any = None) -> str:
		return getattr(runtime, "cli_path", None) or self.DEFAULT_EXECUTABLE

	# ------------------------------------------------------------------
	# Probe / auth
	# ------------------------------------------------------------------

	async def probe(self, runtime: Any) -> RuntimeCapabilities:
		"""Run `claude --version` and report capabilities confirmed by the real fixtures.

		Flags/behavior cited:
		- supports_json: `--output-format json` (create_session.json / resume_turn.json, both REAL)
		- supports_session_resume: `-r/--resume` (resume_turn.json, REAL; also documented in help_output.txt)
		- supports_session_id: `--session-id <uuid>` (help_output.txt; not exercised live but flag exists)
		- supports_images: no dedicated image/vision flag exists in help_output.txt --
		  Claude Code takes images via file paths/paste in prompt content, not a
		  CLI flag. Set False per plan §20.3 ("fail clearly rather than silently
		  dropping the image").
		- supports_mcp: True, but ONLY in the "suppress ambient config" sense --
		  `--strict-mcp-config` (help_output.txt) with no `--mcp-config` value
		  makes the CLI ignore ambient project/user MCP servers. This adapter
		  never passes an HUF-generated MCP config.
		- supports_tool_restriction: `--restricted` (help_output.txt) removes
		  command/code-running tools and WebFetch.
		- supports_session_delete: False -- no session-delete command was found
		  anywhere in `claude --help` (see delete_session below).
		"""
		argv = [self._executable(runtime), "--version"]
		result = await self.transport.run(argv, timeout=30)
		if result.timed_out:
			raise SubscriptionCLIError(SubscriptionErrorCode.CLI_PROCESS_TIMEOUT)
		if result.exit_code != 0:
			raise SubscriptionCLIError(
				SubscriptionErrorCode.CLI_NOT_INSTALLED,
				message=self._sanitize(result.stderr or result.stdout),
			)

		version_match = _VERSION_RE.search(result.stdout or "")
		if version_match is None:
			raise SubscriptionCLIError(
				SubscriptionErrorCode.CLI_UNSUPPORTED_VERSION,
				message="Could not parse a version number from `claude --version` output",
			)

		return RuntimeCapabilities(
			supports_noninteractive=True,
			supports_session_id=True,
			supports_session_resume=True,
			supports_session_delete=False,
			supports_json=True,
			supports_stream_json=True,
			supports_images=False,
			supports_usage=True,
			supports_cached_usage=True,
			supports_reasoning_summary=False,
			supports_mcp=True,
			supports_model_selection=True,
			supports_tool_restriction=True,
			requires_stable_cwd=False,
			automation_supported=True,
		)

	async def check_auth(self, runtime: Any) -> AuthStatus:
		"""Run `claude auth status` and parse its JSON output.

		Shape confirmed by fixtures/real/claude/auth_status.json (REAL, sanitized):
		top-level `loggedIn` (bool), `authMethod` (e.g. "claude.ai" = subscription
		OAuth), `apiProvider` (e.g. "firstParty"), `subscriptionType` (e.g. "max").

		NOTE: the logged-out JSON shape was NOT captured live (see
		auth_status.meta.md) -- if `loggedIn` is absent/false or the process exits
		non-zero without JSON, we fall back to state="unknown"/"unauthenticated"
		rather than guessing an unverified shape.
		"""
		argv = [self._executable(runtime), "auth", "status"]
		result = await self.transport.run(argv, timeout=30)
		checked_at = _utcnow_iso()

		data: dict[str, Any] | None = None
		stripped = (result.stdout or "").strip()
		if stripped:
			try:
				parsed = json.loads(stripped)
				if isinstance(parsed, dict):
					data = parsed
			except json.JSONDecodeError:
				data = None

		if data is None:
			return AuthStatus(
				state="unknown",
				account_hint=None,
				method=None,
				message=self._sanitize(result.stderr or result.stdout),
				checked_at=checked_at,
			)

		logged_in = bool(data.get("loggedIn"))
		return AuthStatus(
			state="authenticated" if logged_in else "unauthenticated",
			account_hint=data.get("email") or data.get("orgName"),
			method=data.get("authMethod"),
			message=f"apiProvider={data.get('apiProvider')} subscriptionType={data.get('subscriptionType')}",
			checked_at=checked_at,
		)

	async def begin_auth(self, runtime: Any) -> AuthChallenge:
		"""Initiate an interactive login flow.

		NOT LIVE-VERIFIED -- verify against a real logout/re-login before
		shipping (plan §75.7 / Stage 12 manual follow-up). The spike never logged
		out the real, in-use account (see auth_status.meta.md), so no live
		`claude auth login` (or similar) transcript exists. `claude --help`
		documents an `auth` command ("Manage authentication") and a `setup-token`
		command ("Set up a long-lived authentication token (requires Claude
		subscription)") but not their sub-flag output shape.

		Best-effort structured version: run `claude auth login`, and if a URL
		appears in stdout/stderr, surface it as verification_url with
		requires_huf_input=True (assume a device/browser code flow, mirroring the
		industry-standard OAuth device flow other subscription CLIs use).
		"""
		argv = [self._executable(runtime), "auth", "login"]
		result = await self.transport.run(argv, timeout=30)

		combined = f"{result.stdout or ''}\n{result.stderr or ''}"
		url_match = re.search(r"https?://\S+", combined)
		code_match = re.search(r"\b([A-Z0-9]{4}-[A-Z0-9]{4})\b", combined)

		return AuthChallenge(
			challenge_id=str(uuid.uuid4()),
			provider="claude",
			mode="browser",
			verification_url=url_match.group(0) if url_match else None,
			user_code=code_match.group(1) if code_match else None,
			requires_huf_input=True,
			prompt=self._sanitize(combined.strip()) or "Complete Claude Code login in a browser",
			expires_at=None,
			poll_supported=True,
		)

	async def submit_auth_input(self, runtime: Any, challenge_id: str, value: str) -> AuthStatus:
		"""Submit a code/approval to an active login challenge.

		NOT LIVE-VERIFIED -- verify against a real logout/re-login before
		shipping (plan §75.7 / Stage 12). Best effort: Claude's browser-based
		device flow does not take further HUF-relayed input once
		`claude auth login` has printed its URL/code (the person approves in the
		browser directly); this simply re-checks auth status.
		"""
		return await self.check_auth(runtime)

	async def poll_auth(self, runtime: Any, challenge_id: str) -> AuthStatus:
		"""Poll for completion of a login challenge.

		NOT LIVE-VERIFIED -- verify against a real logout/re-login before
		shipping (plan §75.7 / Stage 12). Best effort: re-run `claude auth
		status` and let the caller compare state transitions across polls.
		"""
		return await self.check_auth(runtime)

	async def logout(self, runtime: Any) -> None:
		"""NOT LIVE-VERIFIED -- best-effort `claude auth logout`.

		`claude --help`'s `auth` subcommand is documented only as "Manage
		authentication" with no exhaustive sub-flag listing captured live.
		"""
		argv = [self._executable(runtime), "auth", "logout"]
		await self.transport.run(argv, timeout=30)

	# ------------------------------------------------------------------
	# Sessions / turns
	# ------------------------------------------------------------------

	def _build_argv(
		self,
		*,
		text: str,
		session_id: str | None,
		resume_id: str | None,
		model_override: str | None,
	) -> list[str]:
		"""Build the argv for a turn.

		Always includes `--strict-mcp-config` (suppress ambient MCP config) and
		`--restricted` (tool restriction, help_output.txt) -- and NEVER
		`--mcp-config`/`--append-system-prompt`, per the passthrough constraint
		in adapters/base.py. See test_adapter_claude.py's argv self-check.
		"""
		argv = [self.DEFAULT_EXECUTABLE, _FLAG_PRINT, text]
		if resume_id is not None:
			argv += [_FLAG_RESUME, resume_id]
		elif session_id is not None:
			argv += [_FLAG_SESSION_ID, session_id]
		argv += [_FLAG_OUTPUT_FORMAT, "json", _FLAG_STRICT_MCP_CONFIG, _FLAG_RESTRICTED]
		if model_override:
			argv += [_FLAG_MODEL, model_override]
		return argv

	def _reject_unsupported_images(self, request: SubscriptionTurnRequest) -> None:
		"""Fail clearly (plan §20.3) rather than silently dropping image input.

		No dedicated image/vision flag was found in help_output.txt (REAL,
		captured live) -- Claude Code takes images via file paths/paste in
		prompt content rather than a CLI flag, so there is nothing safe for this
		adapter to wire up mechanically.
		"""
		if request.files:
			raise SubscriptionError(
				SubscriptionErrorCode.VISION_UNSUPPORTED,
				message="Claude CLI adapter has no dedicated image/vision flag (see help_output.txt); "
				"cannot attach files to this turn",
			)

	def _classify_stderr(self, stderr_text: str) -> SubscriptionErrorCode:
		"""Classify a plain-text CLI error into a stable HUF error code.

		Grounded in fixtures/real/claude/error_malformed_resume.txt (REAL):
		'Error: --resume requires a valid session ID or session title when used
		with --print. ... Provided value "..." is not a UUID and does not match
		any session title.'
		"""
		lowered = stderr_text.lower()
		if all(marker in lowered for marker in _RESUME_NOT_FOUND_MARKERS):
			return SubscriptionErrorCode.SESSION_NOT_FOUND
		if "resume" in lowered:
			return SubscriptionErrorCode.SESSION_RESUME_FAILED
		if "authentication" in lowered or "auth login" in lowered or "logged in" in lowered:
			return SubscriptionErrorCode.AUTH_REQUIRED
		return SubscriptionErrorCode.CLI_PROCESS_FAILED

	@staticmethod
	def _sanitize(text: str | None, *, max_len: int = 2000) -> str | None:
		"""Bound and lightly redact CLI error text before it leaves the adapter."""
		if not text:
			return None
		text = text.strip()
		if not text:
			return None
		# Redact anything that looks like a home-directory path.
		text = re.sub(r"/(Users|home)/[^/\s]+", r"/\1/<redacted>", text)
		# Redact anything that looks like a credential/token value (e.g. a
		# Bearer header, an `sk-`/`ya29.`-style provider token, or an
		# `api_key=...`/`access_token: ...` assignment). CLI stderr can echo
		# these back verbatim (e.g. from a proxy or curl error), and this
		# text is surfaced in SubscriptionTurnResult.events[]/auth_reason,
		# which downstream code treats as safe to log/display. Security
		# fix, Track-Item: T-T6 -- see test_security.py.
		text = _SECRET_VALUE_RE.sub("<redacted>", text)
		if len(text) > max_len:
			text = text[:max_len] + "...(truncated)"
		return text

	def _parse_turn_output(self, argv: list[str], result: Any) -> SubscriptionTurnResult:
		"""Parse CLI output into a SubscriptionTurnResult; never raises on bad output.

		This is the CRITICAL non-JSON-stderr path from the task: real Claude
		Code emits a PLAIN-TEXT stderr error (not JSON) on a malformed
		`--resume` id even when `--output-format json` was requested (confirmed
		by fixtures/real/claude/error_malformed_resume.txt, REAL). A JSON
		decode failure on stdout must never propagate as an exception -- it is
		mapped to a status="error" result here.
		"""
		stdout = (result.stdout or "").strip()
		data: dict[str, Any] | None = None
		if stdout:
			try:
				parsed = json.loads(stdout)
				if isinstance(parsed, dict):
					data = parsed
			except json.JSONDecodeError:
				data = None

		if data is not None:
			is_error = bool(data.get("is_error"))
			if is_error:
				return SubscriptionTurnResult(
					status="error",
					final_text=data.get("result"),
					provider_session_id=data.get("session_id"),
					usage=data.get("usage") or {},
					exit_code=result.exit_code,
					auth_reason=None,
					events=[{"source": "cli_json", "raw": data}],
				)
			return SubscriptionTurnResult(
				status="success",
				final_text=data.get("result"),
				provider_session_id=data.get("session_id"),
				usage=data.get("usage") or {},
				exit_code=result.exit_code,
				events=[{"source": "cli_json", "raw": data}],
			)

		# Non-JSON stdout: fall back to stderr as a plain-text error (the
		# malformed-resume case, and any other CLI failure that isn't
		# JSON-shaped despite --output-format json).
		stderr_text = (result.stderr or "").strip() or stdout
		code = self._classify_stderr(stderr_text)
		sanitized = self._sanitize(stderr_text)
		auth_reason = sanitized if code is SubscriptionErrorCode.AUTH_REQUIRED else None
		return SubscriptionTurnResult(
			status="error",
			final_text=None,
			provider_session_id=None,
			exit_code=result.exit_code,
			auth_reason=auth_reason,
			events=[{"source": "cli_stderr", "code": code.value, "message": sanitized}],
		)

	async def create_session(self, request: SubscriptionTurnRequest) -> ProviderSession:
		"""Create a session by running the first turn with an explicit --session-id.

		Claude's CLI has no separate "create an empty session" command -- a
		session comes into existence as the side effect of the first `-p` turn
		(help_output.txt: `--session-id <uuid>` "Use a specific session ID for
		the conversation (must be a valid UUID)"). So HUF generates the UUID up
		front for idempotency (plan §16.2) and this method executes that first
		turn.

		Command constructed (see _build_argv):
			claude -p "<text>" --session-id <uuid> --output-format json \
				--strict-mcp-config --restricted [--model <override>]
		"""
		self._reject_unsupported_images(request)

		session_id = str(uuid.uuid4())
		argv = self._build_argv(
			text=request.text,
			session_id=session_id,
			resume_id=None,
			model_override=request.model_override,
		)
		result = await self.transport.run(argv, timeout=request.timeout_seconds)
		if result.timed_out:
			raise SubscriptionCLIError(SubscriptionErrorCode.CLI_PROCESS_TIMEOUT)

		turn_result = self._parse_turn_output(argv, result)
		if turn_result.status == "error":
			event = turn_result.events[0] if turn_result.events else {}
			code_value = event.get("code", SubscriptionErrorCode.CLI_PROCESS_FAILED.value)
			try:
				code = SubscriptionErrorCode(code_value)
			except ValueError:
				code = SubscriptionErrorCode.CLI_PROCESS_FAILED
			if code is SubscriptionErrorCode.AUTH_REQUIRED:
				raise SubscriptionAuthError(code, message=event.get("message"))
			raise SubscriptionCLIError(code, message=event.get("message"))

		resolved_session_id = turn_result.provider_session_id or session_id
		return ProviderSession(session_id=resolved_session_id, created_at=_utcnow_iso())

	async def validate_session(self, runtime: Any, session_id: str) -> SessionStatus:
		"""Best-effort session-existence check.

		Claude's CLI has no dedicated "does this session exist" command distinct
		from resuming it (nothing in help_output.txt), and actually resuming
		just to check would consume a real turn (cost + side effects) which is
		disproportionate for a validity check. Chosen approach: report
		"unknown, not independently verifiable" rather than either lying
		(claiming a confirmed True) or spending a turn on every validation call.
		Callers that need a hard guarantee should attempt `run_turn` with
		`provider_session_id=session_id` and handle a SESSION_NOT_FOUND result.
		"""
		return SessionStatus(exists=True, detail="unknown, not independently verifiable without consuming a turn")

	async def delete_session(self, runtime: Any, session_id: str) -> DeleteSessionResult:
		"""Claude's CLI has no documented session-delete command.

		`claude --help` (REAL, help_output.txt) lists `rm <id>` under Commands,
		but that deletes a *background session* (`claude --bg`), a different
		concept from a `-p`/print-mode conversation session ID -- there is no
		flag/command for deleting a resumable print-mode session. Per the task
		("do not invent a flag that doesn't exist"), this is a no-op that
		reports the provider retains the data.
		"""
		return DeleteSessionResult(cleanup_status="provider_retained")

	async def run_turn(self, runtime: Any, request: SubscriptionTurnRequest) -> SubscriptionTurnResult:
		"""Execute a single turn, creating or resuming a session as needed.

		- No `provider_session_id`: builds the same "create" argv as
		  create_session (a fresh --session-id), executed directly here so the
		  result (including any error) is a normal SubscriptionTurnResult
		  instead of being mapped to a raised exception.
		- `provider_session_id` present: resumes via `--resume <id>`
		  (resume_turn.json / help_output.txt, both REAL), same
		  --output-format json / --strict-mcp-config / --restricted flags.

		Never raises on malformed CLI output -- see _parse_turn_output.
		"""
		self._reject_unsupported_images(request)

		resume_id = request.provider_session_id
		session_id = None if resume_id else str(uuid.uuid4())
		argv = self._build_argv(
			text=request.text,
			session_id=session_id,
			resume_id=resume_id,
			model_override=request.model_override,
		)

		result = await self.transport.run(argv, timeout=request.timeout_seconds)
		if result.timed_out:
			return SubscriptionTurnResult(
				status="error",
				final_text=None,
				provider_session_id=resume_id,
				exit_code=None,
				events=[{"source": "transport", "code": SubscriptionErrorCode.CLI_PROCESS_TIMEOUT.value}],
			)

		turn_result = self._parse_turn_output(argv, result)
		if turn_result.status == "success" and turn_result.provider_session_id is None and resume_id:
			# Defensive: real CLI always echoes session_id back (confirmed by
			# resume_turn.json), but keep the caller's id if the JSON ever omits it.
			turn_result = SubscriptionTurnResult(
				status=turn_result.status,
				final_text=turn_result.final_text,
				provider_session_id=resume_id,
				usage=turn_result.usage,
				reasoning_summary=turn_result.reasoning_summary,
				events=turn_result.events,
				raw_debug_ref=turn_result.raw_debug_ref,
				exit_code=turn_result.exit_code,
				auth_reason=turn_result.auth_reason,
			)
		return turn_result


def _utcnow_iso() -> str:
	return datetime.now(timezone.utc).isoformat()
