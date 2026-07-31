"""
Remote Agent Adapter Service.

Provides a protocol-agnostic abstraction layer (RemoteAgentAdapter) for invoking
and managing remote agents over various protocol standards (HUF-native, ACP, Agent Client Protocol).
"""

from abc import ABC, abstractmethod
import ipaddress
import json
import socket
from urllib.parse import urljoin, urlparse

import requests

MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10MB
DEFAULT_TIMEOUT = 30


# Exception Hierarchy
class RemoteAgentAdapterError(Exception):
    """Base exception for remote agent adapter errors."""

    pass


class RemoteAgentConnectionError(RemoteAgentAdapterError):
    """Raised when connecting to a remote endpoint fails or URL validation fails."""

    pass


class RemoteAgentAuthError(RemoteAgentAdapterError):
    """Raised when authentication with the remote endpoint fails (401/403)."""

    pass


class RemoteAgentTimeoutError(RemoteAgentAdapterError):
    """Raised when a request to a remote endpoint times out."""

    pass


class RemoteAgentResponseError(RemoteAgentAdapterError):
    """Raised when a remote agent endpoint returns an error status or invalid payload."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class RemoteAgentNotImplementedError(RemoteAgentAdapterError, NotImplementedError):
    """Raised when an adapter action or protocol is not yet implemented."""

    pass


def _is_public_ip(ip_str: str) -> bool:
    """Return True if ip_str is a routable public address."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None:
        addr = mapped

    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def validate_remote_url(url: str, allow_local_network: bool = False) -> tuple[bool, str | None]:
    """
    Validate remote URL to prevent SSRF while allowing optional local/satellite setups.
    Returns (is_valid, error_message).
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return False, "Only HTTP and HTTPS schemes are allowed"

    if not parsed.hostname:
        return False, "Invalid URL: missing hostname"

    if not allow_local_network:
        try:
            addr_info = socket.getaddrinfo(parsed.hostname, None)
            ips = {info[4][0] for info in addr_info}
        except socket.gaierror:
            return False, f"Cannot resolve hostname: {parsed.hostname}"

        for ip in ips:
            if not _is_public_ip(ip):
                return False, "Requests to private/internal addresses are not allowed"

    return True, None


class RemoteAgentAdapter(ABC):
    """Abstract base class for all remote agent adapters."""

    @abstractmethod
    def fetch_manifest(self) -> dict:
        """
        Fetch and normalize remote agent manifest.

        Returns:
            dict: Normalized manifest containing server_name, protocol_version, and agents list.
        """
        pass

    @abstractmethod
    def create_run(self, agent_id: str, payload: dict) -> dict:
        """
        Initiate a run on the remote agent.

        Args:
            agent_id (str): Remote agent identifier.
            payload (dict): Run payload (prompt, inputs, context).

        Returns:
            dict: Normalized run details (run_id, status, response, etc.).
        """
        pass

    @abstractmethod
    def get_run(self, run_id: str) -> dict:
        """
        Fetch details and status of an existing remote run.

        Args:
            run_id (str): Remote run identifier.

        Returns:
            dict: Normalized run details.
        """
        pass

    @abstractmethod
    def get_events(self, run_id: str, cursor: str | None = None) -> dict:
        """
        Fetch execution events for a remote run.

        Args:
            run_id (str): Remote run identifier.
            cursor (str | None): Optional event cursor for pagination/resume.

        Returns:
            dict: Normalized events list and pagination cursor.
        """
        pass

    @abstractmethod
    def cancel_run(self, run_id: str) -> dict:
        """
        Cancel an ongoing remote run.

        Args:
            run_id (str): Remote run identifier.

        Returns:
            dict: Normalized cancellation confirmation.
        """
        pass


class HufNativeAdapter(RemoteAgentAdapter):
    """
    Adapter implementation for HUF-native federation.

    Interacts with another HUF instance using Frappe RPC endpoints and standard
    HUF remote agent endpoints.
    """

    def __init__(
        self,
        base_url: str,
        auth_type: str = "none",
        auth_secret: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        allow_local_network: bool = False,
        headers: dict | None = None,
    ):
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.auth_type = auth_type or "none"
        self.auth_secret = auth_secret
        self.timeout = timeout
        self.allow_local_network = allow_local_network
        self.custom_headers = headers or {}

    @classmethod
    def from_config(cls, config: dict | object) -> "HufNativeAdapter":
        """Construct adapter instance from a dict or DocType/namespace object."""
        def get_val(key: str, default=None):
            if isinstance(config, dict):
                return config.get(key, default)
            return getattr(config, key, default)

        base_url = get_val("base_url", "")
        auth_type = get_val("auth_type", "none")
        auth_secret = get_val("auth_secret") or get_val("api_key") or get_val("token")
        timeout = get_val("timeout", DEFAULT_TIMEOUT)
        allow_local_network = get_val("allow_local_network", False) or get_val("allow_local_ips", False)
        headers = get_val("headers", None)

        return cls(
            base_url=base_url,
            auth_type=auth_type,
            auth_secret=auth_secret,
            timeout=timeout,
            allow_local_network=allow_local_network,
            headers=headers,
        )

    def _get_headers(self) -> dict:
        headers = dict(self.custom_headers)
        if self.auth_type == "bearer_token" and self.auth_secret:
            headers["Authorization"] = f"Bearer {self.auth_secret}"
        elif self.auth_type == "site_token" and self.auth_secret:
            headers["X-Site-Token"] = self.auth_secret
        elif self.auth_type == "api_key" and self.auth_secret:
            headers["Authorization"] = f"token {self.auth_secret}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_data: dict | None = None,
        allow_404: bool = False,
    ) -> dict:
        if not self.base_url:
            raise RemoteAgentConnectionError("Remote connection base_url is not configured")

        full_url = urljoin(self.base_url + "/", path.lstrip("/"))

        is_valid, error_msg = validate_remote_url(full_url, allow_local_network=self.allow_local_network)
        if not is_valid:
            raise RemoteAgentConnectionError(f"URL validation failed: {error_msg}")

        req_headers = self._get_headers()

        try:
            response = requests.request(
                method=method.upper(),
                url=full_url,
                headers=req_headers,
                params=params,
                json=json_data,
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            raise RemoteAgentTimeoutError(f"Request to {full_url} timed out after {self.timeout}s")
        except requests.exceptions.ConnectionError as e:
            raise RemoteAgentConnectionError(f"Failed to connect to {full_url}: {e!s}")
        except requests.exceptions.RequestException as e:
            raise RemoteAgentConnectionError(f"HTTP request error for {full_url}: {e!s}")

        if response.status_code in (401, 403):
            raise RemoteAgentAuthError(
                f"Authentication failed ({response.status_code}): {response.text}"
            )

        if response.status_code == 404 and allow_404:
            return {"_status_code": 404}

        if response.status_code >= 400:
            raise RemoteAgentResponseError(
                f"Remote endpoint error ({response.status_code}): {response.text[:500]}",
                status_code=response.status_code,
            )

        if len(response.content) > MAX_RESPONSE_SIZE:
            raise RemoteAgentResponseError(
                "Response size exceeds maximum allowed limit (10MB)",
                status_code=response.status_code,
            )

        try:
            data = response.json()
        except ValueError:
            raise RemoteAgentResponseError(
                f"Invalid JSON response from remote endpoint: {response.text[:200]}",
                status_code=response.status_code,
            )

        # Unpack standard Frappe RPC envelope {"message": ...}
        if isinstance(data, dict) and "message" in data:
            unpacked = data["message"]
            if isinstance(unpacked, (dict, list)):
                return unpacked

        return data if isinstance(data, dict) else {"data": data}

    def fetch_manifest(self) -> dict:
        path = "/api/method/huf.api.remote_agents.get_agent_manifest"
        res = self._request("GET", path, allow_404=True)

        # Fallback to standard well-known location if method endpoint is 404
        if res.get("_status_code") == 404:
            res = self._request("GET", "/.well-known/huf-agent.json")

        agents_list = res.get("agents", []) if isinstance(res, dict) else []

        return {
            "server_name": res.get("server_name", "Remote HUF"),
            "protocol_version": res.get("protocol_version") or "huf-native-v1",
            "agents": agents_list,
            "raw_manifest": res,
        }

    def create_run(self, agent_id: str, payload: dict) -> dict:
        path = "/api/method/huf.api.remote_agents.create_run"
        body = {
            "agent_id": agent_id,
            "payload": payload,
        }
        res = self._request("POST", path, json_data=body)

        run_id = res.get("run_id") or res.get("name") or res.get("id") or ""
        status = res.get("status", "queued")
        response_text = res.get("response") or res.get("content") or ""
        error = res.get("error") or res.get("error_message")

        return {
            "run_id": run_id,
            "status": status,
            "response": response_text,
            "error": error,
            "raw_response": res,
        }

    def get_run(self, run_id: str) -> dict:
        path = "/api/method/huf.api.remote_agents.get_run"
        res = self._request("GET", path, params={"run_id": run_id})

        status = res.get("status", "unknown")
        response_text = res.get("response") or res.get("content") or ""
        error = res.get("error") or res.get("error_message")

        return {
            "run_id": run_id,
            "status": status,
            "response": response_text,
            "error": error,
            "completed_at": res.get("completed_at"),
            "raw_response": res,
        }

    def get_events(self, run_id: str, cursor: str | None = None) -> dict:
        path = "/api/method/huf.api.remote_agents.get_run_events"
        params = {"run_id": run_id}
        if cursor:
            params["cursor"] = cursor

        res = self._request("GET", path, params=params)

        events = res.get("events", []) if isinstance(res, dict) else []
        next_cursor = res.get("cursor") if isinstance(res, dict) else None
        has_more = bool(res.get("has_more", False)) if isinstance(res, dict) else False

        return {
            "run_id": run_id,
            "events": events,
            "cursor": next_cursor,
            "has_more": has_more,
            "raw_response": res,
        }

    def cancel_run(self, run_id: str) -> dict:
        path = "/api/method/huf.api.remote_agents.cancel_run"
        body = {"run_id": run_id}
        res = self._request("POST", path, json_data=body)

        status = res.get("status", "cancelled") if isinstance(res, dict) else "cancelled"
        msg = res.get("message", "Run cancelled") if isinstance(res, dict) else "Run cancelled"

        return {
            "run_id": run_id,
            "status": status,
            "message": msg,
            "raw_response": res,
        }


class AgentCommunicationProtocolAdapter(RemoteAgentAdapter):
    """
    Placeholder adapter implementation for Agent Communication Protocol (ACP).
    """

    def __init__(self, base_url: str = "", **kwargs):
        self.base_url = base_url
        self.kwargs = kwargs

    def fetch_manifest(self) -> dict:
        raise RemoteAgentNotImplementedError(
            "Agent Communication Protocol (ACP) adapter is not yet implemented."
        )

    def create_run(self, agent_id: str, payload: dict) -> dict:
        raise RemoteAgentNotImplementedError(
            "Agent Communication Protocol (ACP) adapter is not yet implemented."
        )

    def get_run(self, run_id: str) -> dict:
        raise RemoteAgentNotImplementedError(
            "Agent Communication Protocol (ACP) adapter is not yet implemented."
        )

    def get_events(self, run_id: str, cursor: str | None = None) -> dict:
        raise RemoteAgentNotImplementedError(
            "Agent Communication Protocol (ACP) adapter is not yet implemented."
        )

    def cancel_run(self, run_id: str) -> dict:
        raise RemoteAgentNotImplementedError(
            "Agent Communication Protocol (ACP) adapter is not yet implemented."
        )


class AgentClientProtocolAdapter(RemoteAgentAdapter):
    """
    Placeholder adapter implementation for Agent Client Protocol (coding agents / IDE bridge).
    """

    def __init__(self, base_url: str = "", **kwargs):
        self.base_url = base_url
        self.kwargs = kwargs

    def fetch_manifest(self) -> dict:
        raise RemoteAgentNotImplementedError(
            "Agent Client Protocol adapter is not yet implemented."
        )

    def create_run(self, agent_id: str, payload: dict) -> dict:
        raise RemoteAgentNotImplementedError(
            "Agent Client Protocol adapter is not yet implemented."
        )

    def get_run(self, run_id: str) -> dict:
        raise RemoteAgentNotImplementedError(
            "Agent Client Protocol adapter is not yet implemented."
        )

    def get_events(self, run_id: str, cursor: str | None = None) -> dict:
        raise RemoteAgentNotImplementedError(
            "Agent Client Protocol adapter is not yet implemented."
        )

    def cancel_run(self, run_id: str) -> dict:
        raise RemoteAgentNotImplementedError(
            "Agent Client Protocol adapter is not yet implemented."
        )


def get_adapter(protocol_type: str, **kwargs) -> RemoteAgentAdapter:
    """
    Factory function to obtain a RemoteAgentAdapter instance by protocol name.

    Supported protocol_types:
      - 'huf_native'
      - 'agent_communication_protocol'
      - 'agent_client_protocol'
    """
    if protocol_type == "huf_native":
        if len(kwargs) == 1 and ("config" in kwargs or "connection" in kwargs):
            cfg = kwargs.get("config") or kwargs.get("connection")
            return HufNativeAdapter.from_config(cfg)
        return HufNativeAdapter(**kwargs)
    elif protocol_type == "agent_communication_protocol":
        return AgentCommunicationProtocolAdapter(**kwargs)
    elif protocol_type == "agent_client_protocol":
        return AgentClientProtocolAdapter(**kwargs)
    else:
        raise ValueError(f"Unsupported protocol type: '{protocol_type}'")
