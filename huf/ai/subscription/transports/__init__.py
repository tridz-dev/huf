"""Execution transports for subscription provider runtime.

Transport abstraction allows subscription CLI providers to execute commands
through different execution contexts: local subprocess, Docker container, or SSH.
"""

from __future__ import annotations

from huf.ai.subscription.transports.base import ExecutionTransport

__all__ = [
	"ExecutionTransport",
]
