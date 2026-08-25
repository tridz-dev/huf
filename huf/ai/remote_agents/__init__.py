"""Huf remote-agent integration package.

Provides the protocol-agnostic ``RemoteAgentAdapter`` seam, the ACP stdio
implementation, ``Remote Agent Policy`` resolution, and the outbound tool-call
handler used by Huf's tool registry.
"""

from __future__ import annotations

from huf.ai.remote_agents.adapter import (
	AcpStdioAdapter,
	RemoteAgentAdapter,
	get_adapter,
)
from huf.ai.remote_agents.exceptions import (
	RemoteAgentError,
	RemoteAgentNotImplementedError,
	RemoteAgentPolicyError,
	RemoteAgentRecursionError,
)
from huf.ai.remote_agents.policy import resolve_policy
from huf.ai.remote_agents.recursion_guard import (
	MAX_HOPS,
	CallChain,
	check_and_extend,
)
from huf.ai.remote_agents.tool_handler import execute_remote_tool

__all__ = [
	"MAX_HOPS",
	"AcpStdioAdapter",
	"CallChain",
	"RemoteAgentAdapter",
	"RemoteAgentError",
	"RemoteAgentNotImplementedError",
	"RemoteAgentPolicyError",
	"RemoteAgentRecursionError",
	"check_and_extend",
	"execute_remote_tool",
	"get_adapter",
	"resolve_policy",
]
