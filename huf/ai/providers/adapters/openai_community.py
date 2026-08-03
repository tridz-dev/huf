import base64
import hashlib
import json
import os
import secrets
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urlencode

import frappe
import requests

from huf.ai.providers.adapters.base import BaseSubscriptionAdapter


class OpenAICommunitySubscriptionAdapter(BaseSubscriptionAdapter):
    """
    Community OpenAI/Codex subscription adapter.

    This adapter reuses the public OAuth client credentials that OpenAI's Codex
    CLI uses, allowing individual ChatGPT Plus/Pro subscribers to authenticate
    without a partner-registered OAuth app.

    Credentials are sourced from the community plugin:
      https://github.com/numman-ali/opencode-openai-codex-auth

    Hardcoded values:
      - client_id: app_EMoamEEZ73f0CkXaXp7hrann
      - auth_url:  https://auth.openai.com/oauth/authorize
      - token_url: https://auth.openai.com/oauth/token
      - api_base:  https://chatgpt.com/backend-api
      - scope:     openid profile email offline_access

    Required site config:
      - enable_openai_community_subscription_adapter = 1

    Optional site config overrides:
      - openai_community_oauth_client_id
      - openai_community_oauth_auth_url
      - openai_community_oauth_token_url
      - openai_community_oauth_scope
      - openai_community_api_base_url
      - openai_community_redirect_uri
    """

    COMMUNITY_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
    DEFAULT_AUTH_URL = "https://auth.openai.com/oauth/authorize"
    DEFAULT_TOKEN_URL = "https://auth.openai.com/oauth/token"
    DEFAULT_API_BASE_URL = "https://chatgpt.com/backend-api"
    DEFAULT_SCOPE = "openid profile email offline_access"
    DEFAULT_REDIRECT_URI = "http://localhost:1455/auth/callback"
    JWT_ACCOUNT_CLAIM_PATH = "https://api.openai.com/auth"

    DEFAULT_MODELS = [
        {"id": "gpt-5.2", "name": "GPT-5.2", "context_window": 272000, "output_window": 128000},
        {"id": "gpt-5.2-codex", "name": "GPT-5.2 Codex", "context_window": 272000, "output_window": 128000},
        {"id": "gpt-5.1", "name": "GPT-5.1", "context_window": 272000, "output_window": 128000},
        {"id": "gpt-5.1-codex", "name": "GPT-5.1 Codex", "context_window": 272000, "output_window": 128000},
        {"id": "gpt-5.1-codex-max", "name": "GPT-5.1 Codex Max", "context_window": 272000, "output_window": 128000},
        {"id": "gpt-5.1-codex-mini", "name": "GPT-5.1 Codex Mini", "context_window": 272000, "output_window": 128000},
        {"id": "codex-mini-latest", "name": "Codex Mini Latest", "context_window": 272000, "output_window": 128000},
        {"id": "gpt-4o", "name": "GPT-4o", "context_window": 128000, "output_window": 16384},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "context_window": 128000, "output_window": 16384},
    ]

    def __init__(self):
        if not frappe.conf.get("enable_openai_community_subscription_adapter"):
            raise frappe.PermissionError(
                "OpenAI Community subscription adapter is disabled. "
                "Set 'enable_openai_community_subscription_adapter' to 1 in site config to enable. "
                "This adapter uses community-reversed OAuth credentials and carries provider ToS risk."
            )

    def _get_config(self, key: str, default: Any = None) -> Any:
        return frappe.conf.get(key, default)

    def _get_client_id(self) -> str:
        return self._get_config("openai_community_oauth_client_id") or self.COMMUNITY_CLIENT_ID

    def _get_auth_url(self) -> str:
        return self._get_config("openai_community_oauth_auth_url") or self.DEFAULT_AUTH_URL

    def _get_token_url(self) -> str:
        return self._get_config("openai_community_oauth_token_url") or self.DEFAULT_TOKEN_URL

    def _get_api_base_url(self) -> str:
        return self._get_config("openai_community_api_base_url") or self.DEFAULT_API_BASE_URL

    def _get_scope(self) -> str:
        return self._get_config("openai_community_oauth_scope") or self.DEFAULT_SCOPE

    def _get_redirect_uri(self, override: Optional[str] = None) -> str:
        return override or self._get_config("openai_community_redirect_uri") or self.DEFAULT_REDIRECT_URI

    def get_auth_methods(self) -> List[Dict[str, Any]]:
        return [
            {
                "method": "OAuth PKCE",
                "type": "pkce",
                "label": "OpenAI Community OAuth 2.0 PKCE (browser redirect)",
            },
            {
                "method": "OAuth PKCE (Manual Paste)",
                "type": "pkce_manual",
                "label": "OpenAI Community OAuth 2.0 PKCE (paste callback URL)",
            },
        ]

    def _generate_pkce(self) -> tuple:
        verifier = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8").rstrip("=")
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode("utf-8")
            .rstrip("=")
        )
        return verifier, challenge

    def _parse_pasted_url(self, value: str) -> Dict[str, Optional[str]]:
        value = (value or "").strip()
        if not value:
            return {}
        from urllib.parse import urlparse, parse_qs
        try:
            parsed = urlparse(value)
            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]
            if code:
                return {"code": code, "state": state}
        except Exception:
            pass
        if "#" in value:
            code, state = value.split("#", 1)
            return {"code": code, "state": state}
        if "code=" in value:
            params = parse_qs(value)
            return {
                "code": params.get("code", [None])[0],
                "state": params.get("state", [None])[0],
            }
        return {"code": value}

    def start_authorization(
        self,
        connection_doc: Any,
        mode: str,
        redirect_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        if mode not in ("OAuth PKCE", "OAuth PKCE (Manual Paste)"):
            raise ValueError(f"Unsupported auth mode: {mode}")

        client_id = self._get_client_id()
        verifier, challenge = self._generate_pkce()
        state = secrets.token_urlsafe(24)
        final_redirect_uri = self._get_redirect_uri(redirect_uri)

        metadata = connection_doc.get_decrypted_auth_payload() or {}
        metadata.update(
            {
                "pkce_verifier": verifier,
                "oauth_state": state,
                "redirect_uri": final_redirect_uri,
                "auth_mode": mode,
            }
        )
        connection_doc.set_auth_payload(metadata)
        connection_doc.auth_status = "Pending Authorization"

        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": final_redirect_uri,
            "scope": self._get_scope(),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": "codex_cli_rs",
        }
        auth_url = f"{self._get_auth_url()}?{urlencode(params)}"

        result = {
            "auth_url": auth_url,
            "state": state,
        }
        if mode == "OAuth PKCE (Manual Paste)":
            result["instructions"] = (
                "Open the URL in your browser, complete login, then copy the full "
                "redirect URL from the browser address bar (it will look like "
                "http://localhost:1455/auth/callback?code=...&state=...) and paste it back here."
            )
        return result

    def complete_authorization(
        self,
        connection_doc: Any,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        code = payload.get("code")
        state = payload.get("state")

        # Manual paste may pass the full callback URL instead of parsed code/state.
        if not code and payload.get("pasted_url"):
            parsed = self._parse_pasted_url(payload["pasted_url"])
            code = parsed.get("code")
            state = parsed.get("state") or state

        if not code:
            raise ValueError("Authorization code is required")

        metadata = connection_doc.get_decrypted_auth_payload() or {}
        stored_state = metadata.get("oauth_state")
        if stored_state and state != stored_state:
            raise ValueError("OAuth state mismatch")

        verifier = metadata.get("pkce_verifier")
        if not verifier:
            raise ValueError("PKCE verifier not found; restart authorization")

        redirect_uri = payload.get("redirect_uri") or metadata.get("redirect_uri") or self._get_redirect_uri()

        token_resp = requests.post(
            self._get_token_url(),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": self._get_client_id(),
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

        account_id = ""
        if access_token:
            account_id = self._extract_chatgpt_account_id(access_token) or ""

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
        if account_id:
            connection_doc.account_id = account_id

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
            "account_id": connection_doc.account_id,
            "expires_in": expires_in,
        }

    def _extract_chatgpt_account_id(self, access_token: str) -> Optional[str]:
        try:
            parts = access_token.split(".")
            if len(parts) != 3:
                return None
            payload_part = parts[1]
            padded = payload_part + "=" * (-len(payload_part) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode())
            account_data = payload.get(self.JWT_ACCOUNT_CLAIM_PATH)
            if isinstance(account_data, dict):
                return account_data.get("chatgpt_account_id")
        except Exception:
            pass
        return None

    def refresh_connection(self, connection_doc: Any) -> bool:
        refresh_token = connection_doc.get_decrypted_refresh_token()
        if not refresh_token:
            connection_doc.auth_status = "Expired"
            return False

        try:
            resp = requests.post(
                self._get_token_url(),
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self._get_client_id(),
                },
                headers={"Accept": "application/json"},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            access_token = data.get("access_token")
            account_id = self._extract_chatgpt_account_id(access_token) if access_token else connection_doc.account_id

            connection_doc.set_tokens(
                access_token=access_token,
                refresh_token=data.get("refresh_token", refresh_token),
                expires_in_seconds=int(data.get("expires_in", 3600)),
                token_type=data.get("token_type", "Bearer"),
            )
            if account_id:
                connection_doc.account_id = account_id
            connection_doc.auth_status = "Active"
            return True
        except Exception as e:
            frappe.log_error(
                f"Failed to refresh OpenAI community connection {connection_doc.name}: {str(e)}",
                "OpenAI Community Subscription Refresh Error",
            )
            connection_doc.auth_status = "Expired"
            return False

    def discover_models(self, connection_doc: Any) -> List[Dict[str, Any]]:
        return list(self.DEFAULT_MODELS)

    def _get_headers(self, connection_doc: Any) -> Dict[str, str]:
        headers = {
            "Authorization": f"{connection_doc.token_type or 'Bearer'} {connection_doc.get_decrypted_access_token()}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "responses=experimental",
            "originator": "codex_cli_rs",
            "User-Agent": "HUF-AgentSystem/1.0",
        }
        if connection_doc.account_id:
            headers["chatgpt-account-id"] = connection_doc.account_id
        return headers

    def _normalize_model(self, model: str) -> str:
        mapping = {
            "gpt-5.2-medium": "gpt-5.2",
            "gpt-5.2-codex-medium": "gpt-5.2-codex",
            "gpt-5.1-medium": "gpt-5.1",
            "gpt-5.1-codex-medium": "gpt-5.1-codex",
            "gpt-5.1-codex-max-medium": "gpt-5.1-codex-max",
            "gpt-5.1-codex-mini-medium": "gpt-5.1-codex-mini",
        }
        return mapping.get(model, model)

    def _build_input(self, enhanced_prompt: Any) -> List[Dict[str, Any]]:
        if isinstance(enhanced_prompt, str):
            return [{"role": "user", "content": enhanced_prompt}]
        if isinstance(enhanced_prompt, list):
            return [{k: v for k, v in item.items() if k != "id"} for item in enhanced_prompt]
        if isinstance(enhanced_prompt, dict):
            return [{k: v for k, v in enhanced_prompt.items() if k != "id"}]
        return [{"role": "user", "content": str(enhanced_prompt)}]

    def _build_codex_body(
        self,
        connection_doc: Any,
        enhanced_prompt: Any,
        model: str,
        stream: bool = False,
    ) -> Dict[str, Any]:
        metadata = connection_doc.get_decrypted_auth_payload() or {}
        encrypted_reasoning = metadata.get("encrypted_reasoning")

        input_items = self._build_input(enhanced_prompt)
        if encrypted_reasoning:
            # Re-inject previous reasoning context if available.
            input_items.append({
                "type": "reasoning",
                "content": encrypted_reasoning,
            })

        body: Dict[str, Any] = {
            "model": self._normalize_model(model),
            "store": False,
            "stream": stream,
            "input": input_items,
            "include": ["reasoning.encrypted_content"],
        }

        # Basic reasoning/text defaults; future improvement: make configurable.
        body["reasoning"] = {"effort": "medium", "summary": "auto"}
        body["text"] = {"verbosity": "medium"}

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

        url = f"{self._get_api_base_url()}/codex/responses"
        payload = self._build_codex_body(connection_doc, enhanced_prompt, model, stream=False)

        resp = requests.post(
            url,
            json=payload,
            headers=self._get_headers(connection_doc),
            timeout=120,
        )
        resp.raise_for_status()

        text = resp.text
        final_response = self._parse_sse_text(text)
        content = self._extract_text_from_response(final_response)
        usage = self._extract_usage(final_response)

        self._persist_encrypted_reasoning(connection_doc, final_response)

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

        url = f"{self._get_api_base_url()}/codex/responses"
        payload = self._build_codex_body(connection_doc, enhanced_prompt, model, stream=True)

        full_response = ""
        final_response = None

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
                    async for line in resp.content:
                        event = self._parse_sse_line(line)
                        if not event:
                            continue
                        event_type = event.get("type")
                        if event_type == "response.output_text.delta":
                            delta = event.get("delta", "")
                            if delta:
                                full_response += delta
                                yield {
                                    "type": "delta",
                                    "content": delta,
                                    "full_response": full_response,
                                }
                        elif event_type in ("response.done", "response.completed"):
                            final_response = event.get("response")
                            usage = self._extract_usage(final_response)
                            yield {
                                "type": "complete",
                                "full_response": full_response,
                                "usage": usage,
                                "cost": 0.0,
                            }
        except ImportError:
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
            for line in resp.iter_lines():
                event = self._parse_sse_line(line)
                if not event:
                    continue
                event_type = event.get("type")
                if event_type == "response.output_text.delta":
                    delta = event.get("delta", "")
                    if delta:
                        full_response += delta
                        yield {
                            "type": "delta",
                            "content": delta,
                            "full_response": full_response,
                        }
                elif event_type in ("response.done", "response.completed"):
                    final_response = event.get("response")
                    usage = self._extract_usage(final_response)
                    yield {
                        "type": "complete",
                        "full_response": full_response,
                        "usage": usage,
                        "cost": 0.0,
                    }

        if final_response:
            self._persist_encrypted_reasoning(connection_doc, final_response)

    def _parse_sse_text(self, text: str) -> Optional[Dict[str, Any]]:
        for line in text.splitlines():
            event = self._parse_sse_line(line)
            if event and event.get("type") in ("response.done", "response.completed"):
                return event.get("response")
        return None

    def _parse_sse_line(self, line: Any) -> Optional[Dict[str, Any]]:
        if not line:
            return None
        text = line.decode("utf-8") if isinstance(line, bytes) else line
        text = text.strip()
        if not text.startswith("data: "):
            return None
        data = text[6:].strip()
        if data == "[DONE]":
            return None
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return None

    def _extract_text_from_response(self, response: Optional[Dict[str, Any]]) -> str:
        if not response:
            return ""
        output = response.get("output", [])
        parts = []
        for item in output:
            if item.get("type") == "message" and item.get("role") == "assistant":
                content = item.get("content", [])
                for part in content:
                    if part.get("type") == "output_text":
                        parts.append(part.get("text", ""))
        return "".join(parts)

    def _extract_usage(self, response: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not response:
            return {}
        return response.get("usage") or {}

    def _persist_encrypted_reasoning(self, connection_doc: Any, response: Optional[Dict[str, Any]]):
        if not response:
            return
        output = response.get("output", [])
        for item in output:
            if item.get("type") == "reasoning":
                encrypted = item.get("encrypted_content")
                if encrypted:
                    metadata = connection_doc.get_decrypted_auth_payload() or {}
                    metadata["encrypted_reasoning"] = encrypted
                    connection_doc.set_auth_payload(metadata)
                    break

    def revoke_connection(self, connection_doc: Any) -> bool:
        connection_doc.access_token = ""
        connection_doc.refresh_token = ""
        connection_doc.auth_payload = ""
        connection_doc.auth_status = "Revoked"
        return True
