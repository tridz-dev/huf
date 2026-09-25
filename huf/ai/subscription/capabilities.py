"""Runtime capability declarations for subscription CLI providers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeCapabilities:
	"""Declares which features a subscription runtime supports."""

	supports_noninteractive: bool = True
	supports_session_id: bool = True
	supports_session_resume: bool = True
	supports_session_delete: bool = True
	supports_json: bool = True
	supports_stream_json: bool = False
	supports_images: bool = False
	supports_usage: bool = False
	supports_cached_usage: bool = False
	supports_reasoning_summary: bool = False
	supports_mcp: bool = False
	supports_model_selection: bool = False
	supports_tool_restriction: bool = False
	requires_stable_cwd: bool = False
	automation_supported: bool = True
	# Whether this runtime's sandbox/permission model has been empirically
	# verified to confine *filesystem reads* (not just writes) to the
	# configured working directory. Most CLI "read-only" sandbox modes only
	# block writes/shell execution side effects and still allow reading any
	# path on disk the OS user can read -- which lets a prompt/tool-call ask
	# the model to read and echo back an unrelated credential file (e.g. the
	# runtime's own OAuth token store). Default True preserves prior adapter
	# behavior for runtimes that have not been specifically audited for this
	# gap; an adapter that empirically confirms unrestricted reads (see
	# adapters/codex.py's probe() docstring for a live-verified example)
	# must set this to False so the runtime-tenancy/UI layer can warn admins
	# before recommending that CLI for shared/multi-tenant deployments.
	filesystem_isolation_verified: bool = True
