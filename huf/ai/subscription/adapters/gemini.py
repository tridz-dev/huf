"""Gemini CLI subscription adapter.

IMPORTANT PROVENANCE NOTE (read before touching this file)
============================================================

The Gemini CLI was NOT installed or authenticated in the environment that ran the
Stage 0 fixture-capture spike (see
`huf/ai/tests/subscription/fixtures/real/gemini/*.meta.md` and
`STAGE0_SPIKE_SUMMARY.md` at the workspace track root). Every fixture in that
directory is DOC-DERIVED or an explicit SYNTHETIC placeholder, not a captured live
run. Unlike the sibling `claude`/`codex` fixtures, none of the Gemini fixtures are
real stdout.

Every behavioral claim below is annotated as either:
  - "per docs" / "documented" — traceable to the fetched Gemini CLI documentation
    pages cited in the fixtures (cli-reference.md, session-management.md,
    authentication.mdx), but NOT independently confirmed against a live binary, or
  - "NOT LIVE-VERIFIED" — inferred/best-effort, with no doc or live source, and must
    be re-checked in Stage 12 (a later manual live-testing pass; not part of this
    task) before this adapter is trusted in production.

Do not upgrade any of these comments to "confirmed" without an actual live capture.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
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
	SubscriptionCLIError,
	SubscriptionError,
	SubscriptionErrorCode,
)
from huf.ai.subscription.transports.base import ExecutionTransport
from huf.ai.subscription.types import AuthChallenge, AuthStatus, SubscriptionTurnRequest, SubscriptionTurnResult

_UUID_RE = re.compile(
	r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Matches common credential/token shapes that a CLI's stderr/stdout might
# echo back verbatim (e.g. from an underlying HTTP client's error message):
# `Authorization: Bearer <token>`, an Anthropic/OpenAI-style `sk-...` secret
# key, a Google OAuth `ya29....` access token, or an `api_key=`/
# `access_token:`-style assignment. Kept identical to claude.py's
# `_SECRET_VALUE_RE` (Track-Item: T-T6) so both adapters redact the same
# secret shapes before CLI error text is surfaced via `auth_reason`/`events`.
_SECRET_VALUE_RE = re.compile(
	r"(?i)"
	r"bearer\s+[a-z0-9._\-]{10,}"
	r"|sk-[a-z0-9_\-]{10,}"
	r"|ya29\.[a-z0-9._\-]{10,}"
	r"|(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret)\s*[=:]\s*[\"']?[a-z0-9._\-]{8,}[\"']?"
)


def _now_iso() -> str:
	return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True, slots=True)
class _ParsedTurnOutput:
	"""Defensively-extracted fields from a Gemini `--output-format json` payload.

	See `_parse_turn_output` for why this exists: the Stage 0 spike found no worked
	example of the actual response schema anywhere in the fetched docs
	(`create_session.meta.md`, `resume_turn.meta.md` both flag this as the single
	highest-priority unresolved gap). This shape is a best-effort guess, not a
	confirmed contract.
	"""

	final_text: str | None
	session_id: str | None
	usage: dict[str, Any]
	reasoning_summary: str | None


class GeminiAdapter(SubscriptionCLIAdapter):
	"""Adapter for the Gemini CLI subscription (Google OAuth) provider.

	Passthrough constraint (inherited from SubscriptionCLIAdapter): this adapter
	must never construct system-prompt content from HUF Agent instructions, never
	attach HUF conversation history, and never expose HUF tool schemas/MCP config to
	the Gemini CLI. Only the current turn's `text`/`files` from SubscriptionTurnRequest
	are ever placed into the CLI invocation.
	"""

	# Per plan §15.5: "The runtime should ship/use a HUF-specific noninteractive
	# policy that denies native shell/editing tools by default and permits only
	# explicitly approved HUF MCP tools where enabled." The fixtures
	# (help_output.txt) document `--allowed-mcp-server-names` and `gemini mcp *`
	# subcommands for MCP allow-listing, but do NOT document a specific flag/file
	# format for a *deny* policy targeting native shell/edit tools.
	#
	# NOT LIVE-VERIFIED: confirm the exact deny-policy flag/file format (e.g. a
	# `--allowed-tools`/`--core-tools`/settings.json `tools.exclude` style key) against
	# a real Gemini CLI before shipping. `--allowed-mcp-server-names ""` (empty list)
	# is used here as the best-effort default-deny posture for MCP servers, since it
	# is the one allow/deny-shaped flag actually documented in the fixtures; it does
	# not address native shell/edit tools at all, which remains an open gap.
	_DEFAULT_DENY_MCP_SERVERS_FLAG = "--allowed-mcp-server-names"
	_DEFAULT_DENY_MCP_SERVERS_VALUE = ""

	def __init__(self, transport: ExecutionTransport) -> None:
		super().__init__(transport)

	# ------------------------------------------------------------------
	# Working directory (plan §17.1)
	# ------------------------------------------------------------------

	def _stable_cwd(self, runtime: Any) -> str:
		"""Return the runtime's stable working directory.

		CORRECTNESS REQUIREMENT, not a nice-to-have (plan §17.1): Gemini CLI stores
		sessions keyed by a hash of the project/working directory
		(`docs/cli/session-management.md`, per fixtures). This adapter MUST always
		invoke `gemini` with the exact same `cwd` for a given runtime, taken from
		`runtime.working_directory`. Any change to that value is a runtime-identity
		change from Gemini's point of view — a session created under one cwd cannot
		reliably be resumed from another, so callers must never vary this per-call.
		"""
		cwd = getattr(runtime, "working_directory", None)
		if not cwd or not str(cwd).strip():
			raise SubscriptionError(
				SubscriptionErrorCode.RUNTIME_PERMISSION_DENIED,
				"Gemini runtime requires a stable working_directory (plan §17.1); none configured",
			)
		return str(cwd)

	def _executable(self, runtime: Any) -> str:
		executable = getattr(runtime, "cli_path", None)
		return str(executable) if executable else "gemini"

	def _policy_argv(self) -> list[str]:
		"""Best-effort HUF noninteractive deny-policy flags (plan §15.5).

		NOT LIVE-VERIFIED — see class docstring comment above `_DEFAULT_DENY_MCP_SERVERS_FLAG`.
		"""
		return [self._DEFAULT_DENY_MCP_SERVERS_FLAG, self._DEFAULT_DENY_MCP_SERVERS_VALUE]

	# ------------------------------------------------------------------
	# probe()
	# ------------------------------------------------------------------

	async def probe(self, runtime: Any) -> RuntimeCapabilities:
		"""Probe via `gemini --version` (documented flag pattern; exact --version
		output was not captured live — help_output.txt is doc-reconstructed, not a
		verbatim --help/--version transcript).
		"""
		executable = self._executable(runtime)
		cwd = self._stable_cwd(runtime)
		result = await self.transport.run([executable, "--version"], cwd=cwd, timeout=30)
		if result.exit_code != 0:
			raise SubscriptionError(
				SubscriptionErrorCode.CLI_NOT_INSTALLED,
				f"gemini --version failed (exit_code={result.exit_code})",
			)

		# Per plan §58.2/§68.3: cached-token reporting is documented as available for
		# API-key/Vertex auth paths but NOT for Google OAuth (subscription) users —
		# "/stats can still show total token usage" but not cache breakdown. This
		# adapter targets the subscription (Google OAuth) auth path specifically, so
		# supports_cached_usage is hardcoded False here for THAT path, not as a
		# blanket assumption about Gemini usage in general (an API-key-mode adapter
		# variant could set this True). This is capability detection based on the
		# documented auth-path distinction, not a live-verified measurement.
		return RuntimeCapabilities(
			supports_noninteractive=True,
			supports_session_id=True,  # documented explicit --session-id support (plan §17 verified list)
			supports_session_resume=True,  # documented -r/--resume (help_output.txt)
			supports_session_delete=True,  # documented --delete-session (help_output.txt)
			supports_json=True,  # documented --output-format json
			supports_stream_json=True,  # documented --output-format stream-json (plan §17 verified list)
			supports_images=False,  # NOT DOCUMENTED in fetched docs; see run_turn()
			supports_usage=True,  # plan §17 lists "token usage" as verified-documented
			supports_cached_usage=False,  # Google OAuth/subscription path only; see comment above
			supports_reasoning_summary=True,  # plan §17: "assistant thoughts/reasoning summaries when available"
			supports_mcp=True,  # documented `gemini mcp add/list/remove`, --allowed-mcp-server-names
			supports_model_selection=False,  # NOT confirmed in fetched docs/fixtures for this adapter; leave conservative
			supports_tool_restriction=True,  # documented deny-rule policy engine (plan §15.5), exact flag NOT LIVE-VERIFIED
			requires_stable_cwd=True,  # plan §17.1 — mandatory
			automation_supported=True,
		)

	# ------------------------------------------------------------------
	# check_auth()
	# ------------------------------------------------------------------

	async def check_auth(self, runtime: Any) -> AuthStatus:
		"""Check auth status.

		Per `auth_status.meta.md`/`auth_status.txt` (SYNTHETIC, doc-derived): the
		fetched Gemini CLI docs do not describe a dedicated machine-readable
		"auth status" command distinct from a full CLI run (unlike `claude auth
		status` or `codex login status`, which are both real, documented, and
		distinct commands per the sibling Claude/Codex fixtures). Documented text
		states headless mode "will use your existing authentication method, if an
		existing authentication credential is cached" — implying there is no
		separate status probe endpoint.

		Honest gap, not invented: this method therefore performs a trivial
		non-interactive call and infers authentication from its outcome, rather than
		querying a dedicated status flag. This is a documented-absence workaround,
		not a confirmed API. NOT LIVE-VERIFIED: the exact exit code / stderr text
		Gemini emits for "not authenticated" in headless mode.
		"""
		executable = self._executable(runtime)
		cwd = self._stable_cwd(runtime)
		try:
			result = await self.transport.run(
				[executable, "-p", "hi", "--output-format", "json", *self._policy_argv()],
				cwd=cwd,
				timeout=30,
			)
		except Exception as exc:  # noqa: BLE001 - transport-level failure, not an auth signal
			raise SubscriptionError(
				SubscriptionErrorCode.RUNTIME_UNREACHABLE,
				f"transport error while probing gemini auth: {exc}",
			) from exc

		checked_at = _now_iso()
		if result.exit_code == 0:
			return AuthStatus(
				state="ready",
				account_hint=None,  # not exposed by any documented non-interactive output
				method=None,  # cannot distinguish OAuth vs API key vs Vertex without a dedicated status call
				message="Non-interactive probe call succeeded (no dedicated auth-status command is documented)",
				checked_at=checked_at,
			)

		return AuthStatus(
			state="required",
			account_hint=None,
			method=None,
			message=(
				"Non-interactive probe call failed; treating as unauthenticated because no dedicated "
				f"auth-status command is documented for gemini (exit_code={result.exit_code}). "
				"NOT LIVE-VERIFIED: exact failure signature for a logged-out gemini CLI."
			),
			checked_at=checked_at,
		)

	# ------------------------------------------------------------------
	# Auth challenge flow
	# ------------------------------------------------------------------

	async def begin_auth(self, runtime: Any) -> AuthChallenge:
		"""Gemini's documented auth flow is interactive browser OAuth ("Sign in with
		Google") launched from an interactive `gemini` invocation, per
		authentication.mdx (see auth_status.txt). Per plan §68.3, HUF must not assume
		a fresh Google OAuth login can always be initiated from a totally
		non-interactive headless process; there is also a documented user-code/manual
		authorization path when browser launch is suppressed in an interactive
		terminal.

		NOT LIVE-VERIFIED: this adapter cannot currently drive that interactive flow
		programmatically (no PTY/TUI automation is wired here — see plan §19, deferred).
		Surface this as a requires_huf_input challenge describing the manual steps
		rather than inventing a device-code polling protocol that isn't documented.
		"""
		return AuthChallenge(
			challenge_id=f"gemini-manual-{runtime.name if hasattr(runtime, 'name') else 'unknown'}",
			provider="gemini",
			mode="manual",
			verification_url=None,
			user_code=None,
			requires_huf_input=True,
			prompt=(
				"Gemini CLI requires an interactive Google OAuth sign-in (or GEMINI_API_KEY / Vertex "
				"credentials). Run `gemini` interactively on the runtime host and complete 'Sign in with "
				"Google', or configure GEMINI_API_KEY / Vertex Application Default Credentials. HUF cannot "
				"drive this flow non-interactively; NOT LIVE-VERIFIED whether a headless device-code path exists."
			),
			expires_at=None,
			poll_supported=False,
		)

	async def submit_auth_input(self, runtime: Any, challenge_id: str, value: str) -> AuthStatus:
		raise SubscriptionError(
			SubscriptionErrorCode.AUTH_CHALLENGE_FAILED,
			"Gemini adapter does not support submitting auth input non-interactively; "
			"no documented mechanism exists for this (see begin_auth)",
		)

	async def poll_auth(self, runtime: Any, challenge_id: str) -> AuthStatus:
		raise SubscriptionError(
			SubscriptionErrorCode.AUTH_CHALLENGE_FAILED,
			"Gemini adapter does not support polling auth challenges; poll_supported is False",
		)

	# ------------------------------------------------------------------
	# Session lifecycle
	# ------------------------------------------------------------------

	async def create_session(self, request: SubscriptionTurnRequest) -> ProviderSession:
		"""Gemini sessions are auto-created/auto-saved on first turn (plan §17,
		"sessions auto-save"), and `--session-id` is documented as available for
		explicit session-id assignment (plan §17 verified list; help_output.meta.md
		item 1 flags exact flag spelling as unconfirmed). This adapter generates a
		UUID up front (matching the idempotency pattern noted for Claude in
		STAGE0_SPIKE_SUMMARY.md for `--session-id`) so callers have a stable
        provider_session_id before the first turn runs.

		NOT LIVE-VERIFIED: whether `--session-id <uuid>` on first invocation actually
		pins that UUID as the session identifier for Gemini specifically, since no
		worked example of the JSON response body was found (create_session.meta.md).
		The identifier is still returned here as the best-effort session handle; the
		actual first `run_turn` call is responsible for reconciling it against
		whatever the CLI reports back (see `_parse_turn_output`).
		"""
		import uuid

		session_id = str(uuid.uuid4())
		return ProviderSession(session_id=session_id, created_at=_now_iso())

	async def validate_session(self, runtime: Any, session_id: str) -> SessionStatus:
		"""No dedicated single-session lookup command is documented; `--list-sessions`
		is documented as a text-mode listing (help_output.txt), not JSON, and no
		worked example of its output being machine-parseable beyond the display
		format `1. Fix bug in auth (2 days ago) [a1b2c3d4]` was found.

		Best-effort: run `--list-sessions` and substring-match the session id's
		short form against the output. NOT LIVE-VERIFIED: exact list-sessions text
		format, whether short ids collide, or whether this command requires the
		same stable cwd as everything else (assumed yes, per plan §17.1).
		"""
		executable = self._executable(runtime)
		cwd = self._stable_cwd(runtime)
		try:
			result = await self.transport.run([executable, "--list-sessions"], cwd=cwd, timeout=30)
		except Exception as exc:  # noqa: BLE001
			raise SubscriptionError(
				SubscriptionErrorCode.RUNTIME_UNREACHABLE,
				f"transport error while listing gemini sessions: {exc}",
			) from exc

		if result.exit_code != 0:
			return SessionStatus(exists=False, detail=f"--list-sessions failed (exit_code={result.exit_code})")

		short_id = session_id[:8] if len(session_id) >= 8 else session_id
		exists = short_id.lower() in result.stdout.lower() or session_id.lower() in result.stdout.lower()
		return SessionStatus(
			exists=exists,
			detail="matched via --list-sessions text output (NOT LIVE-VERIFIED format)" if exists else None,
		)

	async def delete_session(self, runtime: Any, session_id: str) -> DeleteSessionResult:
		"""Delete a session via `--delete-session` (plan §17.2, help_output.txt).

		Discrepancy note: help_output.txt documents `--delete-session <INDEX>`
		(an index number from --list-sessions), while plan §17.2 describes deletion
		by `<id>`. NOT LIVE-VERIFIED which form the real CLI accepts (an index, a
		UUID, or both) — this passes `session_id` through as-is and treats any
		non-zero exit as a soft cleanup failure rather than guessing a translation.

		Per plan §17.2: "If deletion fails, HUF should still finish the run but
		record cleanup failure for operational visibility." This method therefore
		NEVER raises on cleanup failure — it logs (via the returned detail-bearing
		result upstream) and returns cleanup_status="cleanup_failed" instead.
		"""
		executable = self._executable(runtime)
		try:
			cwd = self._stable_cwd(runtime)
		except SubscriptionError:
			# Even a missing stable cwd must not fail the overall run per §17.2 -
			# treat as a cleanup failure, not a raised exception.
			return DeleteSessionResult(cleanup_status="cleanup_failed")

		try:
			result = await self.transport.run(
				[executable, "--delete-session", session_id], cwd=cwd, timeout=30
			)
		except Exception:  # noqa: BLE001 - never raise on cleanup failure, per plan §17.2
			return DeleteSessionResult(cleanup_status="cleanup_failed")

		if result.exit_code == 0:
			return DeleteSessionResult(cleanup_status="deleted")
		return DeleteSessionResult(cleanup_status="cleanup_failed")

	# ------------------------------------------------------------------
	# Best-effort error classification (H9, Track-Item: fix-gemini-h3-h9)
	# ------------------------------------------------------------------

	# NOT LIVE-VERIFIED: Gemini's exact logout/auth-failure stderr text and exit
	# code were never captured (Stage 0 spike had no installed/authenticated
	# Gemini CLI — see class docstring). No fixture documents what a logged-out
	# `gemini -p ... --output-format json` invocation actually prints. This is a
	# best-effort keyword classifier only, modeled on the sibling claude.py
	# adapter's `_classify_stderr` (which IS confirmed-working per the review),
	# not a verified Gemini-specific contract. Re-check against a live capture
	# in Stage 12 before trusting the exact keyword list.
	_AUTH_FAILURE_MARKERS = ("auth", "login", "unauthorized", "credential")

	def _classify_stderr(self, stderr_text: str) -> SubscriptionErrorCode:
		"""Best-effort classification of a Gemini CLI stderr failure.

		NOT LIVE-VERIFIED (see `_AUTH_FAILURE_MARKERS` above): checks stderr text
		case-insensitively for auth/login/unauthorized/credential-shaped keywords
		and classifies a match as AUTH_REQUIRED so `executor.py::_extract_error_code`
		can park the run for re-authentication instead of failing it outright
		(matching the working pattern in claude.py's `_classify_stderr` ->
		AUTH_REQUIRED path). Anything else is classified as a generic CLI failure.
		"""
		lowered = (stderr_text or "").lower()
		if any(marker in lowered for marker in self._AUTH_FAILURE_MARKERS):
			return SubscriptionErrorCode.AUTH_REQUIRED
		return SubscriptionErrorCode.CLI_PROCESS_FAILED

	@staticmethod
	def _sanitize(text: str | None, *, max_len: int = 2000) -> str | None:
		"""Bound CLI error text before it is surfaced via `auth_reason`/`events`."""
		if not text:
			return None
		text = text.strip()
		if not text:
			return None
		text = _SECRET_VALUE_RE.sub("<redacted>", text)
		if len(text) > max_len:
			text = text[:max_len] + "...(truncated)"
		return text

	# ------------------------------------------------------------------
	# run_turn()
	# ------------------------------------------------------------------

	async def run_turn(self, runtime: Any, request: SubscriptionTurnRequest) -> SubscriptionTurnResult:
		"""Execute one turn via `gemini -p ... --output-format json [-r <id>]`.

		Flags cited from help_output.txt (doc-reconstructed, NOT a verbatim --help
		transcript per help_output.meta.md item 1):
		  - `-p, --prompt <TEXT>`               non-interactive prompt text
		  - `-o, --output-format <json>`        JSON output mode
		  - `-r, --resume <latest|INDEX|UUID>`  session resume, used with request.provider_session_id
		  - `--session-id` for explicit session id assignment on first turn (plan §17
		    verified-list item; exact flag spelling per help_output.meta.md item 1 is
		    NOT LIVE-VERIFIED)

		Passthrough constraint: argv below carries ONLY request.text and staged
		request.files — no HUF system prompt, conversation history, tool schema, or
		MCP config derived from HUF's Agent system is ever added.
		"""
		if request.files and not (await self.probe(runtime)).supports_images:
			raise SubscriptionError(
				SubscriptionErrorCode.VISION_UNSUPPORTED,
				"Gemini adapter: no documented image/multimodal flag was found in the fetched CLI docs "
				"(help_output.meta.md item 4); files were supplied but cannot be passed through",
			)

		executable = self._executable(runtime)
		cwd = self._stable_cwd(runtime)

		argv = [executable]
		if request.provider_session_id:
			argv += ["-r", request.provider_session_id]
		else:
			# H3 fix (review finding, Track-Item: fix-gemini-h3-h9): help_output.txt
			# (fixtures/real/gemini/help_output.txt) documents `--session-id` NOWHERE --
			# the only session-management flags it lists are `-r/--resume
			# <latest|INDEX|SESSION_UUID>`, `--list-sessions`, and `--delete-session
			# <INDEX>`. There is no documented way to pre-assign a session id for a
			# brand-new session (unlike Claude, where `--session-id` on first
			# invocation is confirmed-documented). Passing `--session-id ""` here was
			# the bug: it sent an EMPTY STRING as the flag value on every new-session
			# turn instead of either omitting the flag or generating a real id.
			#
			# Fix: omit any session-id flag entirely for a new session and let Gemini
			# generate its own session id. The resulting id is recovered from the
			# turn's JSON response by `_parse_turn_output` (which already tries
			# several plausible key names: `session_id`/`sessionId`/`session`/
			# `session_uuid`) and returned as `SubscriptionTurnResult.provider_session_id`.
			pass
		if request.model_override:
			# NOT LIVE-VERIFIED: no documented model-selection flag was found in the
			# fetched docs/fixtures for this adapter; supports_model_selection is
			# False in probe(). Fail loudly rather than silently ignoring an
			# explicit override.
			raise SubscriptionError(
				SubscriptionErrorCode.MODEL_UNAVAILABLE,
				"Gemini adapter: model_override requested but no model-selection flag is documented/verified",
			)
		argv += ["-p", request.text, "-o", "json"]
		argv += self._policy_argv()

		try:
			result = await self.transport.run(argv, cwd=cwd, timeout=request.timeout_seconds)
		except Exception as exc:  # noqa: BLE001
			raise SubscriptionCLIError(
				SubscriptionErrorCode.RUNTIME_UNREACHABLE,
				f"transport error while running gemini turn: {exc}",
			) from exc

		if result.timed_out:
			raise SubscriptionCLIError(
				SubscriptionErrorCode.CLI_PROCESS_TIMEOUT,
				"gemini turn timed out",
			)

		if result.exit_code != 0:
			# Per error_malformed_resume.meta.md: neither JSON-shaped nor plain-text
			# error format is confirmed for Gemini specifically (unlike Claude/Codex,
			# both of which are confirmed to emit plain-text stderr even when JSON
			# output was requested). Surface stderr verbatim rather than guessing a
			# structured shape.
			#
			# H9 fix (review finding, Track-Item: fix-gemini-h3-h9): a logout/auth
			# failure must be classified as AUTH_REQUIRED and surfaced via
			# `events`, matching the pattern in claude.py's `_parse_turn_output`
			# (`_classify_stderr` -> `events=[{"source": "cli_stderr", "code": ...}]`).
			# Without this, executor.py::_extract_error_code() sees no `code` on
			# any event, never recognizes AUTH_REQUIRED, and fails the run outright
			# instead of parking it for re-authentication (plan §26.4/§62.4).
			code = self._classify_stderr(result.stderr or "")
			auth_reason = self._sanitize(result.stderr) if code is SubscriptionErrorCode.AUTH_REQUIRED else None
			return SubscriptionTurnResult(
				status="failed",
				final_text=None,
				provider_session_id=request.provider_session_id,
				exit_code=result.exit_code,
				raw_debug_ref=result.stderr[:4000] if result.stderr else None,
				auth_reason=auth_reason,
				events=[{"source": "cli_stderr", "code": code.value}],
			)

		parsed = self._parse_turn_output(result.stdout)

		return SubscriptionTurnResult(
			status="success",
			final_text=parsed.final_text,
			provider_session_id=parsed.session_id or request.provider_session_id,
			usage=parsed.usage,
			reasoning_summary=parsed.reasoning_summary,
			exit_code=result.exit_code,
		)

	# ------------------------------------------------------------------
	# Defensive JSON parsing
	# ------------------------------------------------------------------

	def _parse_turn_output(self, stdout: str) -> _ParsedTurnOutput:
		"""Best-effort, defensive parse of a Gemini `--output-format json` payload.

		THIS MUST BE TIGHTENED AFTER A REAL LIVE CAPTURE (Stage 12). Per
		`create_session.meta.md`/`resume_turn.meta.md`, no worked example of the
		actual response schema was found anywhere in the fetched Gemini CLI docs —
		this is the single highest-priority unresolved gap the Stage 0 spike flagged.
		Field names below (`result`/`response`/`text`, `session_id`/`sessionId`/
		`session`, `usage`/`tokenUsage`/`stats`) are guesses based on the shapes used
		by the sibling Claude (`session_id`/`result`/`usage`) and Codex
		(`thread_id`/`usage` in `turn.completed`) adapters, chosen only because
		Gemini's docs describe conceptually similar data (session id, usage,
		reasoning/thoughts) without giving field names. None of these guesses are
		confirmed.

		Strategy: try several plausible top-level key names for each field; if the
		payload cannot even be parsed as JSON, or none of the expected top-level keys
		are present in a dict, raise CLI_OUTPUT_PARSE_FAILED cleanly instead of
		crashing with a raw KeyError/JSONDecodeError.
		"""
		text = stdout.strip()
		if not text:
			raise SubscriptionCLIError(
				SubscriptionErrorCode.CLI_OUTPUT_PARSE_FAILED,
				"gemini --output-format json produced empty stdout",
			)

		try:
			data = json.loads(text)
		except json.JSONDecodeError as exc:
			raise SubscriptionCLIError(
				SubscriptionErrorCode.CLI_OUTPUT_PARSE_FAILED,
				f"gemini stdout was not valid JSON: {exc}",
			) from exc

		if not isinstance(data, dict):
			raise SubscriptionCLIError(
				SubscriptionErrorCode.CLI_OUTPUT_PARSE_FAILED,
				f"gemini JSON output was not a top-level object (got {type(data).__name__})",
			)

		final_text = _first_str(data, ("result", "response", "text", "output", "message"))
		session_id = _first_str(data, ("session_id", "sessionId", "session", "session_uuid"))
		# 'usage' block: try common key names, default to {} rather than failing the
		# whole parse - usage is informational (plan §58.2), never load-bearing.
		usage = _first_dict(data, ("usage", "tokenUsage", "stats", "token_usage")) or {}
		reasoning_summary = _first_str(data, ("reasoning_summary", "thoughts", "reasoning", "thought_summary"))

		if final_text is None:
			# We got parseable JSON but couldn't find anything resembling the answer
			# text under any plausible key — this is exactly the "plausible
			# malformed/unexpected-shape" case the task calls out. Raise cleanly.
			raise SubscriptionCLIError(
				SubscriptionErrorCode.CLI_OUTPUT_PARSE_FAILED,
				"gemini JSON output did not contain a recognizable result/response/text field "
				f"(top-level keys: {sorted(data.keys())!r}); schema is unconfirmed, see _parse_turn_output",
			)

		return _ParsedTurnOutput(
			final_text=final_text,
			session_id=session_id,
			usage=usage,
			reasoning_summary=reasoning_summary,
		)


def _first_str(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
	for key in keys:
		value = data.get(key)
		if isinstance(value, str) and value:
			return value
	return None


def _first_dict(data: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any] | None:
	for key in keys:
		value = data.get(key)
		if isinstance(value, dict):
			return value
	return None
