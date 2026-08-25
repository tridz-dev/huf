"""Backward-compatible re-export of the ACP stdio adapter.

The canonical implementation now lives in ``huf.ai.remote_agents.adapter``.
This module keeps the historical import path working and preserves the
optional PR #661 factory patching logic so existing tests do not break.
"""

from __future__ import annotations

import logging
from typing import Any

from huf.ai.remote_agents.adapter import (
	DEFAULT_AUTH_ENV_KEY,
	AcpStdioAdapter,
	RemoteAgentAdapter,
	get_adapter,
)

LOGGER = logging.getLogger("huf.ai.acp.adapter")

__all__ = [
	"DEFAULT_AUTH_ENV_KEY",
	"AcpStdioAdapter",
	"RemoteAgentAdapter",
	"get_adapter",
]


# Optional factory registration when PR #661's factory exists.
try:
	from huf.ai.remote_agents.adapter import get_adapter as _remote_get_adapter

	def _make_acp_stdio_adapter(**kwargs: Any) -> AcpStdioAdapter:
		return AcpStdioAdapter(**kwargs)

	_original_get_adapter = _remote_get_adapter

	def _patched_get_adapter(protocol_type: str, **kwargs: Any) -> RemoteAgentAdapter:
		if protocol_type == "acp_stdio":
			return _make_acp_stdio_adapter(**kwargs)
		return _original_get_adapter(protocol_type, **kwargs)

	import huf.ai.remote_agents.adapter as _ra_adapter

	_ra_adapter.get_adapter = _patched_get_adapter
except Exception:  # noqa: BLE001
	LOGGER.debug("Could not register ACP adapter with remote_agents factory")
