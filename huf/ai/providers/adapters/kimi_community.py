import json
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

import frappe
import requests

from huf.ai.providers.adapters.base import BaseSubscriptionAdapter


class KimiCommunitySubscriptionAdapter(BaseSubscriptionAdapter):
    """
    Community Kimi For Coding subscription adapter.

    This adapter reuses the public OAuth device-flow client credentials that
    Kimi's official CLI uses, allowing Kimi For Coding subscribers to
    authenticate without a static API key.

    Credentials / behavior are sourced from the community plugin:
      https://github.com/lemon07r/opencode-kimi-full

    Hardcoded values:
      - client_id: 17e5f671-d194-4dfb-9706-5516cb48c098
      - device_auth_url: https://auth.kimi.com/api/oauth/device_authorization
      - token_url: https://auth.kimi.com/api/oauth/token
      - api_base: https://api.kimi.com/coding/v1

    Required site config:
      - enable_kimi_community_subscription_adapter = 1

    Optional site config overrides:
      - kimi_community_oauth_client_id
      - kimi_community_oauth_device_auth_url
      - kimi_community_oauth_token_url
      - kimi_community_api_base_url
      - kimi_community_device_id (stable hex UUID, no dashes)
    """

    COMMUNITY_CLIENT_ID = "17e5f671-d194-4dfb-9706-5516cb48c098"
    KIMI_CLI_VERSION = "1.41.0"
    DEFAULT_DEVICE_AUTH_URL = "https://auth.kimi.com/api/oauth/device_authorization"
    DEFAULT_TOKEN_URL = "https://auth.kimi.com/api/oauth/token"
    DEFAULT_API_BASE_URL = "https://api.kimi.com/coding/v1"
    DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
    REFRESH_GRANT = "refresh_token"
    REQUEST_TIMEOUT = 120

    DEFAULT_MODELS = [
        {
            "id": "kimi-for-coding",
            "name": "Kimi For Coding",
            "context_window": 200000,
            "output_window": 16384,
            "modalities": {"input": ["text", "image"], "output": ["text"]},
        },
    ]

    def __init__(self):
        if not frappe.conf.get("enable_kimi_community_subscription_adapter"):
            raise frappe.PermissionError(
                "Kimi Community subscription adapter is disabled. "
                "Set 'enable_kimi_community_subscription_adapter' to 1 in site config to enable. "
                "This adapter uses community-reversed OAuth credentials and carries provider ToS risk."
            )

    def _get_config(self, key: str, default: Any = None) -> Any:
        return frappe.conf.get(key, default)

    def _get_client_id(self) -> str:
        return self._get_config("kimi_community_oauth_client_id") or self.COMMUNITY_CLIENT_ID

    def _get_device_auth_url(self) -> str:
        return self._get_config("kimi_community_oauth_device_auth_url") or self.DEFAULT_DEVICE_AUTH_URL

    def _get_token_url(self) -> str:
        return self._get_config("kimi_community_oauth_token_url") or self.DEFAULT_TOKEN_URL

    def _get_api_base_url(self) -> str:
        return self._get_config("kimi_community_api_base_url") or self.DEFAULT_API_BASE_URL

    def _get_device_id(self, connection_doc: Any) -> str:
        """Return a stable hex UUID for this connection (mirrors ~/.kimi/device_id)."""
        metadata = connection_doc.get_decrypted_auth_payload() or {}
        device_id = metadata.get("device_id")
        if device_id:
            return device_id
        device_id = self._get_config("kimi_community_device_id")
        if device_id:
            return device_id
        return uuid.uuid4().hex

    def _get_headers(self, connection_doc: Any) -> Dict[str, str]:
        import platform

        device_id = self._get_device_id(connection_doc)
        system = platform.system()
        release = platform.release()
        machine = platform.machine() or platform.processor() or "unknown"

        if system == "Darwin":
            device_model = f"macOS {release} {machine}".strip()
        elif system == "Windows":
            device_model = f"Windows {release} {machine}".strip()
        else:
            device_model = f"{system} {release} {machine}".strip()

        return {
            "User-Agent": f"KimiCLI/{self.KIMI_CLI_VERSION}",
            "X-Msh-Platform": "kimi_cli",
            "X-Msh-Version": self.KIMI_CLI_VERSION,
            "X-Msh-Device-Name": self._ascii_header(platform.node() or "unknown"),
            "X-Msh-Device-Model": self._ascii_header(device_model),
            "X-Msh-Device-Id": device_id,
            "X-Msh-Os-Version": self._ascii_header(f"{system} {release}"),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _ascii_header(self, value: str, fallback: str = "unknown") -> str:
        sanitized = "".join(c for c in value if 0x20 <= ord(c) <= 0x7E).strip()
        return sanitized or fallback

    def get_auth_methods(self) -> List[Dict[str, Any]]:
        return [
            {
                "method": "Device Code",
                "type": "device_code",
                "label": "Kimi For Coding Device Flow",
            }
        ]

    def start_authorization(
        self,
        connection_doc: Any,
        mode: str,
        redirect_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        if mode != "Device Code":
            raise ValueError(f"Unsupported auth mode: {mode}")

        device_id = self._get_device_id(connection_doc)
        headers = self._get_headers(connection_doc)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        resp = requests.post(
            self._get_device_auth_url(),
            data={"client_id": self._get_client_id()},
            headers=headers,
            timeout=self.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        metadata = connection_doc.get_decrypted_auth_payload() or {}
        metadata.update(
            {
                "device_id": device_id,
                "device_code": data.get("device_code"),
                "auth_mode": mode,
            }
        )
        connection_doc.set_auth_payload(metadata)
        connection_doc.auth_status = "Pending Authorization"

        return {
            "user_code": data.get("user_code"),
            "verification_uri": data.get("verification_uri"),
            "verification_uri_complete": data.get("verification_uri_complete"),
            "device_code": data.get("device_code"),
            "expires_in": data.get("expires_in", 1800),
            "interval": data.get("interval", 5),
            "instructions": (
                f"Open {data.get('verification_uri')} in your browser and enter "
                f"code {data.get('user_code')}. Then return here and complete authorization."
            ),
        }

    def complete_authorization(
        self,
        connection_doc: Any,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        metadata = connection_doc.get_decrypted_auth_payload() or {}
        device_code = payload.get("device_code") or metadata.get("device_code")
        if not device_code:
            raise ValueError("device_code is required; restart authorization")

        interval = int(payload.get("interval") or metadata.get("interval") or 5)
        expires_in = int(payload.get("expires_in") or metadata.get("expires_in") or 1800)
        deadline = time.time() + expires_in

        headers = self._get_headers(connection_doc)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        while time.time() < deadline:
            time.sleep(interval)
            resp = requests.post(
                self._get_token_url(),
                data={
                    "client_id": self._get_client_id(),
                    "device_code": device_code,
                    "grant_type": self.DEVICE_GRANT,
                },
                headers=headers,
                timeout=self.REQUEST_TIMEOUT,
            )

            if resp.status_code == 200:
                data = resp.json()
                self._store_tokens(connection_doc, data)
                return {
                    "status": "success",
                    "account_email": connection_doc.account_email,
                    "expires_in": data.get("expires_in"),
                }

            try:
                error_body = resp.json()
            except Exception:
                error_body = {}
            error_code = error_body.get("error")

            if error_code == "authorization_pending":
                continue
            if error_code == "slow_down":
                interval += 5
                continue
            if error_code == "expired_token":
                raise frappe.ValidationError("Kimi device code expired — start authorization again")
            if error_code:
                raise frappe.ValidationError(
                    f"Kimi OAuth error {error_code}: {error_body.get('error_description', resp.text)}"
                )
            resp.raise_for_status()

        raise frappe.ValidationError("Kimi device code expired before approval")

    def _store_tokens(self, connection_doc: Any, token_data: Dict[str, Any]):
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        token_type = token_data.get("token_type", "Bearer")

        metadata = connection_doc.get_decrypted_auth_payload() or {}
        metadata["token_response"] = {k: v for k, v in token_data.items() if k not in ("access_token", "refresh_token")}
        connection_doc.set_auth_payload(metadata)
        connection_doc.set_tokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in_seconds=int(expires_in),
            token_type=token_type,
        )
        connection_doc.auth_status = "Active"

    def refresh_connection(self, connection_doc: Any) -> bool:
        refresh_token = connection_doc.get_decrypted_refresh_token()
        if not refresh_token:
            connection_doc.auth_status = "Expired"
            return False

        headers = self._get_headers(connection_doc)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        retryable_statuses = {429, 500, 502, 503, 504}
        last_error = None
        for attempt in range(3):
            try:
                resp = requests.post(
                    self._get_token_url(),
                    data={
                        "client_id": self._get_client_id(),
                        "refresh_token": refresh_token,
                        "grant_type": self.REFRESH_GRANT,
                    },
                    headers=headers,
                    timeout=self.REQUEST_TIMEOUT,
                )
                text = resp.text
                try:
                    data = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    if resp.status_code in retryable_statuses:
                        raise RuntimeError(f"Kimi refresh transient {resp.status_code}: non-JSON response")
                    raise RuntimeError(f"Kimi refresh non-JSON response (status {resp.status_code}): {text[:200]}")

                if resp.status_code in (401, 403):
                    raise RuntimeError(f"Kimi refresh {resp.status_code}: {data.get('error_description', text)}")
                resp.raise_for_status()

                self._store_tokens(connection_doc, data)
                return True
            except Exception as e:
                last_error = e
                status = getattr(e, "status", None)
                retryable = status is None or status in retryable_statuses
                if not retryable or attempt == 2:
                    break
                time.sleep(2 ** attempt)

        frappe.log_error(
            f"Failed to refresh Kimi community connection {connection_doc.name}: {str(last_error)}",
            "Kimi Community Subscription Refresh Error",
        )
        connection_doc.auth_status = "Expired"
        return False

    def discover_models(self, connection_doc: Any) -> List[Dict[str, Any]]:
        access_token = connection_doc.get_decrypted_access_token()
        if access_token:
            try:
                headers = self._get_headers(connection_doc)
                headers["Authorization"] = f"Bearer {access_token}"
                resp = requests.get(
                    f"{self._get_api_base_url()}/models",
                    headers=headers,
                    timeout=self.REQUEST_TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    models = []
                    for m in data.get("data", []):
                        model_id = m.get("id")
                        if not model_id:
                            continue
                        models.append({
                            "id": model_id,
                            "name": m.get("display_name") or model_id,
                            "context_window": m.get("context_length") or 200000,
                            "modalities": {
                                "input": ["text", "image"] if m.get("supports_image_in") else ["text"],
                                "output": ["text"],
                            },
                        })
                    if models:
                        return models
            except Exception as e:
                frappe.log_error(
                    f"Kimi model discovery failed for {connection_doc.name}: {str(e)}",
                    "Kimi Community Model Discovery Error",
                )
        return list(self.DEFAULT_MODELS)

    def _build_messages(self, enhanced_prompt: Any) -> List[Dict[str, str]]:
        if isinstance(enhanced_prompt, str):
            return [{"role": "user", "content": enhanced_prompt}]
        if isinstance(enhanced_prompt, list):
            return enhanced_prompt
        if isinstance(enhanced_prompt, dict):
            return [enhanced_prompt]
        return [{"role": "user", "content": str(enhanced_prompt)}]

    def _build_request_body(
        self,
        connection_doc: Any,
        enhanced_prompt: Any,
        model: str,
        stream: bool = False,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        body = {
            "model": model,
            "messages": self._build_messages(enhanced_prompt),
            "stream": stream,
        }

        # Session-scoped prompt cache key; falls back to connection name.
        session_id = (context or {}).get("session_id") or connection_doc.name
        body["prompt_cache_key"] = session_id

        # Reasoning defaults mirroring kimi-cli.
        reasoning_effort = (context or {}).get("reasoning_effort") or "medium"
        if reasoning_effort == "off":
            body["thinking"] = {"type": "disabled"}
        elif reasoning_effort in ("low", "medium", "high"):
            body["thinking"] = {"type": "enabled"}
            body["reasoning_effort"] = reasoning_effort
        # "auto" omits both fields.

        return body

    def run(
        self,
        connection_doc: Any,
        agent: Any,
        enhanced_prompt: Any,
        model: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if connection_doc.auth_status != "Active":
            raise PermissionError(
                f"Subscription connection {connection_doc.name} is not active ({connection_doc.auth_status})"
            )

        url = f"{self._get_api_base_url()}/chat/completions"
        payload = self._build_request_body(connection_doc, enhanced_prompt, model, stream=False, context=context)

        headers = self._get_headers(connection_doc)
        headers["Authorization"] = f"Bearer {connection_doc.get_decrypted_access_token()}"

        resp = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=self.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "")
        usage = data.get("usage") or {}

        return {
            "response": content,
            "usage": usage,
            "cost": 0.0,
            "new_items": [],
            "model": model,
            "provider": connection_doc.provider,
            "adapter_type": connection_doc.adapter_type,
        }

    async def stream_response(
        self,
        connection_doc: Any,
        agent: Any,
        enhanced_prompt: Any,
        model: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if connection_doc.auth_status != "Active":
            raise PermissionError(
                f"Subscription connection {connection_doc.name} is not active ({connection_doc.auth_status})"
            )

        url = f"{self._get_api_base_url()}/chat/completions"
        payload = self._build_request_body(connection_doc, enhanced_prompt, model, stream=True, context=context)

        headers = self._get_headers(connection_doc)
        headers["Authorization"] = f"Bearer {connection_doc.get_decrypted_access_token()}"

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT),
                ) as resp:
                    resp.raise_for_status()
                    full_response = ""
                    async for line in resp.content:
                        chunk = self._parse_sse_line(line, full_response)
                        if chunk:
                            if chunk.get("type") == "delta":
                                full_response = chunk.get("full_response", full_response)
                            yield chunk
        except ImportError:
            loop = __import__("asyncio").get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    stream=True,
                    timeout=self.REQUEST_TIMEOUT,
                ),
            )
            resp.raise_for_status()
            full_response = ""
            for line in resp.iter_lines():
                chunk = self._parse_sse_line(line, full_response)
                if chunk:
                    if chunk.get("type") == "delta":
                        full_response = chunk.get("full_response", full_response)
                    yield chunk

    def _parse_sse_line(self, line: bytes, full_response: str) -> Optional[Dict[str, Any]]:
        if not line:
            return None
        text = line.decode("utf-8") if isinstance(line, bytes) else line
        if not text.startswith("data: "):
            return None
        data = text[6:].strip()
        if data == "[DONE]":
            return {"type": "complete", "full_response": full_response}
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            return None

        choices = obj.get("choices", [])
        usage = obj.get("usage")
        if usage:
            return {"type": "complete", "full_response": full_response, "usage": usage, "cost": 0.0}
        if not choices:
            return None
        delta = choices[0].get("delta", {})
        content = delta.get("content", "")
        if content:
            full_response += content
            return {"type": "delta", "content": content, "full_response": full_response}
        return None

    def revoke_connection(self, connection_doc: Any) -> bool:
        connection_doc.access_token = ""
        connection_doc.refresh_token = ""
        connection_doc.auth_payload = ""
        connection_doc.auth_status = "Revoked"
        return True
