from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional


class BaseSubscriptionAdapter(ABC):
    """
    Abstract base contract for HUF native subscription provider adapters.

    Adapters translate between HUF's agent runtime and a subscription-backed
    provider (e.g. a provider that uses per-user OAuth tokens instead of a
    shared API key).  The runtime routes to an adapter when an active
    ``AI Provider Connection`` exists for the provider/user/model.

    Result contract:

    - ``run()`` must return either a ``SimpleResult``-like object with
      ``final_output``, ``usage``, ``new_items`` and ``cost`` attributes, or a
      dict containing at least ``response`` (str) and optionally ``usage``,
      ``cost`` and ``new_items``.  The router in ``huf.ai.run`` normalizes the
      dict form to a ``SimpleResult`` before returning to the agent runtime.

    - ``stream_response()`` must yield dicts matching the HUF streaming chunk
      contract used by ``huf.ai.providers.litellm``:

      * ``{"type": "delta", "content": str, "full_response": str}``
      * ``{"type": "reasoning", "content": str, "full_reasoning": str}``
      * ``{"type": "tool_call", "tool_call": dict}``
      * ``{"type": "complete", "full_response": str, "usage": dict, "cost": float}``
      * ``{"type": "error", "error": str}``
    """

    @abstractmethod
    def get_auth_methods(self) -> List[Dict[str, Any]]:
        """
        Returns supported authentication methods (e.g. OAuth PKCE, Device Code).
        """
        pass

    @abstractmethod
    def start_authorization(
        self,
        connection_doc: Any,
        mode: str,
        redirect_uri: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Initiates auth flow. Returns authorization URL or device code instructions.
        """
        pass

    @abstractmethod
    def complete_authorization(
        self,
        connection_doc: Any,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Exchanges callback authorization code or polls device code, updating connection_doc with tokens.
        """
        pass

    @abstractmethod
    def refresh_connection(self, connection_doc: Any) -> bool:
        """
        Refreshes access token if expired or near expiry (e.g. 5 min buffer).
        Returns True if active/refreshed, False if re-auth is required.
        """
        pass

    @abstractmethod
    def discover_models(self, connection_doc: Any) -> List[Dict[str, Any]]:
        """
        Queries vendor endpoint or returns strict allowlist of subscription-supported models.
        """
        pass

    @abstractmethod
    def run(
        self,
        connection_doc: Any,
        agent: Any,
        enhanced_prompt: Any,
        model: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Synchronous/non-streaming response generation for subadapter.
        Returns a HUF-compatible result (SimpleResult-like object or dict).
        """
        pass

    @abstractmethod
    async def stream_response(
        self,
        connection_doc: Any,
        agent: Any,
        enhanced_prompt: Any,
        model: str,
        context: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Translates HUF agent/prompt/tools payload, sends to subscription backend,
        and yields normalized HUF stream chunks.
        """
        pass

    @abstractmethod
    def revoke_connection(self, connection_doc: Any) -> bool:
        """
        Revokes tokens with upstream provider and marks connection as Revoked.
        """
        pass
