"""
HUF Remote Agent Integration Package.
Provides protocol adapter interfaces and implementations for remote agent federation.
"""

from huf.ai.remote_agents.adapter import (
    AgentClientProtocolAdapter,
    AgentCommunicationProtocolAdapter,
    HufNativeAdapter,
    RemoteAgentAdapter,
    RemoteAgentAdapterError,
    RemoteAgentAuthError,
    RemoteAgentConnectionError,
    RemoteAgentNotImplementedError,
    RemoteAgentResponseError,
    RemoteAgentTimeoutError,
    get_adapter,
)

__all__ = [
    "RemoteAgentAdapter",
    "HufNativeAdapter",
    "AgentCommunicationProtocolAdapter",
    "AgentClientProtocolAdapter",
    "RemoteAgentAdapterError",
    "RemoteAgentConnectionError",
    "RemoteAgentAuthError",
    "RemoteAgentTimeoutError",
    "RemoteAgentResponseError",
    "RemoteAgentNotImplementedError",
    "get_adapter",
]
