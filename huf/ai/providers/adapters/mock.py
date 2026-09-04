import asyncio
from types import SimpleNamespace
from typing import Any, AsyncGenerator, Dict, List, Optional
from huf.ai.providers.adapters.base import BaseSubscriptionAdapter


class MockSubscriptionAdapter(BaseSubscriptionAdapter):
    """
    Mock Subscription Adapter for testing native subscription execution,
    token refresh, authorization flows, and streaming/non-streaming runs.
    """

    def get_auth_methods(self) -> List[Dict[str, Any]]:
        return [
            {"method": "OAuth PKCE", "type": "pkce", "label": "Mock OAuth 2.0 PKCE"},
            {"method": "Device Code", "type": "device_code", "label": "Mock Device Code"},
        ]

    def start_authorization(
        self,
        connection_doc: Any,
        mode: str,
        redirect_uri: Optional[str] = None
    ) -> Dict[str, Any]:
        if mode == "OAuth PKCE":
            return {
                "auth_url": "https://mock.provider.com/oauth/authorize?client_id=mock_client",
                "state": "mock_state_123",
            }
        elif mode == "Device Code":
            return {
                "user_code": "MOCK-1234",
                "verification_uri": "https://mock.provider.com/device",
                "device_code": "mock_device_code_567",
                "expires_in": 1800,
                "interval": 5,
            }
        else:
            raise ValueError(f"Unsupported auth mode: {mode}")

    def complete_authorization(
        self,
        connection_doc: Any,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        code = payload.get("code") or payload.get("device_code")
        if not code:
            raise ValueError("Code is required to complete authorization")

        connection_doc.set_tokens(
            access_token="mock_access_token_abc123",
            refresh_token="mock_refresh_token_xyz789",
            expires_in_seconds=3600,
            token_type="Bearer",
        )
        connection_doc.account_id = "acc_mock_user_1"
        connection_doc.account_email = "user@mocksubscription.com"
        connection_doc.plan_type = "mock_pro_plan"
        connection_doc.auth_status = "Active"

        return {
            "status": "success",
            "account_id": connection_doc.account_id,
            "account_email": connection_doc.account_email,
            "plan_type": connection_doc.plan_type,
        }

    def refresh_connection(self, connection_doc: Any) -> bool:
        refresh_token = connection_doc.get_decrypted_refresh_token()
        if not refresh_token or refresh_token == "invalid_refresh_token":
            connection_doc.auth_status = "Expired"
            return False

        connection_doc.set_tokens(
            access_token="refreshed_mock_access_token_999",
            refresh_token="refreshed_mock_refresh_token_888",
            expires_in_seconds=3600,
        )
        connection_doc.auth_status = "Active"
        return True

    def discover_models(self, connection_doc: Any) -> List[Dict[str, Any]]:
        return [
            {"id": "mock-sub-gpt-4o", "name": "Mock Sub GPT-4o", "context_window": 128000},
            {"id": "mock-sub-gemini-2", "name": "Mock Sub Gemini 2.0", "context_window": 1000000},
        ]

    def run(
        self,
        connection_doc: Any,
        agent: Any,
        enhanced_prompt: Any,
        model: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if connection_doc.auth_status != "Active":
            raise PermissionError(
                f"Subscription connection {connection_doc.name} is not active ({connection_doc.auth_status})"
            )

        return {
            "response": (
                f"[Mock Subscription Output for model {model}]: "
                "Completed prompt successfully via mock adapter."
            ),
            "usage": {
                "prompt_tokens": 15,
                "completion_tokens": 25,
                "total_tokens": 40,
            },
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
        context: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if connection_doc.auth_status != "Active":
            raise PermissionError(
                f"Subscription connection {connection_doc.name} is not active ({connection_doc.auth_status})"
            )

        chunks = ["[Mock ", "Subscription ", "Stream ", "Chunk] ", f"for model {model}."]
        full_response = ""
        for chunk in chunks:
            await asyncio.sleep(0.01)
            full_response += chunk
            yield {
                "type": "delta",
                "content": chunk,
                "full_response": full_response,
            }

        yield {
            "type": "complete",
            "full_response": full_response,
            "usage": {
                "prompt_tokens": 15,
                "completion_tokens": 25,
                "total_tokens": 40,
            },
            "cost": 0.0,
        }

    def revoke_connection(self, connection_doc: Any) -> bool:
        connection_doc.access_token = ""
        connection_doc.refresh_token = ""
        connection_doc.auth_payload = ""
        connection_doc.auth_status = "Revoked"
        return True
