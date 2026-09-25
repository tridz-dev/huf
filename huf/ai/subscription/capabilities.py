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
