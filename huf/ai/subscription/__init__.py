"""HUF subscription CLI provider integration."""

from __future__ import annotations

from huf.ai.subscription.capabilities import RuntimeCapabilities
from huf.ai.subscription.errors import (
	SubscriptionAuthError,
	SubscriptionCLIError,
	SubscriptionError,
	SubscriptionErrorCode,
	SubscriptionRuntimeError,
)
from huf.ai.subscription.types import (
	AuthChallenge,
	AuthStatus,
	SubscriptionTurnRequest,
	SubscriptionTurnResult,
)

__all__ = [
	"SubscriptionTurnRequest",
	"SubscriptionTurnResult",
	"AuthStatus",
	"AuthChallenge",
	"RuntimeCapabilities",
	"SubscriptionError",
	"SubscriptionErrorCode",
	"SubscriptionCLIError",
	"SubscriptionAuthError",
	"SubscriptionRuntimeError",
]
