import base64
import hashlib
import json
import os
import secrets
from typing import Any, AsyncGenerator, Dict, List, Optional

import frappe
import requests

from huf.ai.providers.adapters.base import BaseSubscriptionAdapter


class OpenAISubscriptionAdapter(BaseSubscriptionAdapter):
    """
    OpenAI subscription adapter using OAuth 2.0 + PKCE.

    Reads provider-level OAuth configuration from Frappe site config:
      - openai_oauth_client_id
      - openai_oauth_client_secret
      - openai_oauth_auth_url  (default: https://platform.openai.com/oauth/authorize)
      - openai_oauth_token_url (default: https://api.openai.com/oauth/token)
      - openai_oauth_scope     (default: openid email profile)
      - openai_api_base_url    (default: https://api.openai.com/v1)

    Per-user tokens are stored in the AI Provider Connection document.
    """

    DEFAULT_AUTH_URL = "https://platform.openai.com/oauth/authorize"
    DEFAULT_TOKEN_URL = "https://api.openai.com/oauth/token"
    DEFAULT_API_BASE_URL = "https://api.openai.com/v1"
    DEFAULT_SCOPE = "openid email profile"
    DEFAULT_MODELS = [
        {"id": "gpt-4o", "name": "GPT-4o", "context_window": 128000},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "context_window": 128000},
        {"id": "o1", "name": "o1", "context_window": 128000},
        {"id": "o3-mini", "name": "o3-mini", "context_window": 128000},
    ]

    def _get_config(self, key: str, default: Any = None) -> Any:
        return frappe.conf.get(key, default)

    def _require_config(self, key: str) -> str:
        value = self._get_config(key)
        if not value:
            raise frappe.ValidationError(
                f"Missing site config '{key}'. Set it via: bench --site <site> set-config {key} <value>"
            )
        return value

    def _get_client_credentials(self) -> tuple:
        client_id = self._require_config("openai_oauth_client_id")
        client_secret = self._require_config("openai_oauth_client_secret")
        return client_id, client_secret

    def _get_token_url(self) -> str:
        return self._get_config("openai_oauth_token_url") or self.DEFAULT_TOKEN_URL

    def _get_auth_url(self) -> str:
        return self._get_config("openai_oauth_auth_url") or self.DEFAULT_AUTH_URL

    def _get_api_base_url(self) -> str:
        return self._get_config("openai_api_base_url") or self.DEFAULT_API_BASE_URL

    def _get_scope(self) -> str:
        return self._get_config("openai_oauth_scope") or self.DEFAULT_SCOPE

    def get_auth_methods(self) -> List[Dict[str, Any]]:
        return [
            {"method": "OAuth PKCE", "type": "pkce", "label": "OpenAI OAuth 2.0 PKCE"},
        ]

    def _generate_pkce(self) -> tuple:
        verifier = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8").rstrip("=")
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode("utf-8")
            .rstrip("=")
        )
        return verifier, challenge

    def start_authorization(
        self,
        connection_doc: Any,
        mode: str,
        redirect_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        if mode != "OAuth PKCE":
            raise ValueError(f"Unsupported auth mode: {mode}")

        client_id, _ = self._get_client_credentials()
        verifier, challenge = self._generate_pkce()
        state = secrets.token_urlsafe(24)

        # Persist PKCE verifier and state so the callback can validate/exchange.
        metadata = connection_doc.get_decrypted_auth_payload() or {}
        metadata.update(
            {
                "pkce_verifier": verifier,
                "oauth_state": state,
                "redirect_uri": redirect_uri,
            }
        )
        connection_doc.set_auth_payload(metadata)
        connection_doc.auth_status = "Pending Authorization"

        auth_url = (
            f"{self._get_auth_url()}?"
            f"response_type=code"
            f"&client_id={client_id}"
            f"&redirect_uri={redirect_uri or ''}"
            f"&scope={self._get_scope()}"
            f"&state={state}"
            f"&code_challenge={challenge}"
            f"&code_challenge_method=S256"
        )

        return {
            "auth_url": auth_url,
            "state": state,
        }

    def complete_authorization(
        self,
        connection_doc: Any,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        code = payload.get("code")
        state = payload.get("state")
        if not code:
            raise ValueError("Authorization code is required")

        metadata = connection_doc.get_decrypted_auth_payload() or {}
        stored_state = metadata.get("oauth_state")
        if stored_state and state != stored_state:
            raise ValueError("OAuth state mismatch")

        verifier = metadata.get("pkce_verifier")
        if not verifier:
            raise ValueError("PKCE verifier not found; restart authorization")

        client_id, client_secret = self._get_client_credentials()
        redirect_uri = payload.get("redirect_uri") or metadata.get("redirect_uri")

        token_resp = requests.post(
            self._get_token_url(),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri or "",
                "client_id": client_id,
                "client_secret": client_secret,
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
            timeout=30,
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)
        token_type = token_data.get("token_type", "Bearer")

        # Clear transient PKCE data but keep useful metadata.
        metadata.pop("pkce_verifier", None)
        metadata.pop("oauth_state", None)
        metadata.pop("redirect_uri", None)
        metadata["token_response"] = {k: v for k, v in token_data.items() if k not in ("access_token", "refresh_token")}

        connection_doc.set_auth_payload(metadata)
        connection_doc.set_tokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in_seconds=int(expires_in),
            token_type=token_type,
        )

        # Derive account email if available in token response.
        id_token = token_data.get("id_token")
        if id_token:
            try:
                payload_part = id_token.split(".")[1]
                padded = payload_part + "=" * (-len(payload_part) % 4)
                id_payload = json.loads(base64.urlsafe_b64decode(padded).decode())
                connection_doc.account_email = id_payload.get("email", "")
            except Exception:
                pass

        connection_doc.auth_status = "Active"

        return {
            "status": "success",
            "account_email": connection_doc.account_email,
            "expires_in": expires_in,
        }

    def refresh_connection(self, connection_doc: Any) -> bool:
        refresh_token = connection_doc.get_decrypted_refresh_token()
        if not refresh_token:
            connection_doc.auth_status = "Expired"
            return False

        client_id, client_secret = self._get_client_credentials()
        try:
            resp = requests.post(
                self._get_token_url(),
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
                headers={"Accept": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            connection_doc.set_tokens(
                access_token=data.get("access_token"),
                refresh_token=data.get("refresh_token", refresh_token),
                expires_in_seconds=int(data.get("expires_in", 3600)),
                token_type=data.get("token_type", "Bearer"),
            )
            connection_doc.auth_status = "Active"
            return True
        except Exception as e:
            frappe.log_error(
                f"Failed to refresh OpenAI subscription connection {connection_doc.name}: {str(e)}",
                "OpenAI Subscription Refresh Error",
            )
            connection_doc.auth_status = "Expired"
            return False

    def discover_models(self, connection_doc: Any) -> List[Dict[str, Any]]:
        return list(self.DEFAULT_MODELS)

    def _get_headers(self, connection_doc: Any) -> Dict[str, str]:
        headers = {
            "Authorization": f"{connection_doc.token_type or 'Bearer'} {connection_doc.get_decrypted_access_token()}",
            "Content-Type": "application/json",
            "User-Agent": "HUF-AgentSystem/1.0",
        }
        if connection_doc.account_id:
            headers["ChatGPT-Account-ID"] = connection_doc.account_id
        return headers

    def _build_messages(self, enhanced_prompt: Any) -> List[Dict[str, str]]:
        if isinstance(enhanced_prompt, str):
            return [{"role": "user", "content": enhanced_prompt}]
        if isinstance(enhanced_prompt, list):
            return enhanced_prompt
        if isinstance(enhanced_prompt, dict):
            return [enhanced_prompt]
        return [{"role": "user", "content": str(enhanced_prompt)}]

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
        payload = {
            "model": model,
            "messages": self._build_messages(enhanced_prompt),
        }

        resp = requests.post(
            url,
            json=payload,
            headers=self._get_headers(connection_doc),
            timeout=120,
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
        payload = {
            "model": model,
            "messages": self._build_messages(enhanced_prompt),
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        # Use aiohttp if available, otherwise fall back to requests in a thread.
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=self._get_headers(connection_doc),
                    timeout=aiohttp.ClientTimeout(total=120),
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
            # Synchronous fallback wrapped for async compatibility.
            loop = __import__("asyncio").get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    url,
                    json=payload,
                    headers=self._get_headers(connection_doc),
                    stream=True,
                    timeout=120,
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
