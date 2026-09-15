# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import json
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, get_datetime


class AIProviderConnection(Document):
    def validate(self):
        self.validate_eligible_models_json()
        self.validate_extra_metadata_json()

    def validate_eligible_models_json(self):
        if self.eligible_models:
            try:
                parsed = json.loads(self.eligible_models)
                if not isinstance(parsed, list):
                    frappe.throw(_("Eligible Models must be a JSON array of model names."))
            except Exception as e:
                frappe.throw(_("Invalid JSON in Eligible Models: {0}").format(str(e)))

    def validate_extra_metadata_json(self):
        if self.extra_metadata:
            try:
                parsed = json.loads(self.extra_metadata)
                if not isinstance(parsed, dict):
                    frappe.throw(_("Extra Metadata must be a JSON object."))
            except Exception as e:
                frappe.throw(_("Invalid JSON in Extra Metadata: {0}").format(str(e)))

    def _get_decrypted_password(self, fieldname: str) -> str:
        """Return decrypted password value or empty string if unavailable."""
        if not getattr(self, fieldname, None):
            return ""
        try:
            return self.get_password(fieldname) or ""
        except Exception:
            return ""

    def get_decrypted_access_token(self) -> str:
        return self._get_decrypted_password("access_token")

    def get_decrypted_refresh_token(self) -> str:
        return self._get_decrypted_password("refresh_token")

    def get_decrypted_auth_payload(self) -> dict:
        """Return decrypted generic auth payload as a dict, or empty dict."""
        raw = self._get_decrypted_password("auth_payload")
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def set_tokens(
        self,
        access_token: str,
        refresh_token: str = None,
        expires_in_seconds: int = None,
        token_type: str = "Bearer"
    ):
        self.access_token = access_token
        if refresh_token is not None:
            self.refresh_token = refresh_token
        if token_type:
            self.token_type = token_type

        now = now_datetime()
        self.last_refreshed_at = now
        if expires_in_seconds is not None:
            self.expires_at = frappe.utils.add_to_date(now, seconds=int(expires_in_seconds))
        self.auth_status = "Active"

    def set_auth_payload(self, payload: dict, expires_in_seconds: int = None):
        """Store an encrypted generic credential payload (JSON)."""
        if not isinstance(payload, dict):
            frappe.throw(_("Auth payload must be a JSON object."))
        self.auth_payload = json.dumps(payload)
        self.last_refreshed_at = now_datetime()
        if expires_in_seconds is not None:
            self.expires_at = frappe.utils.add_to_date(
                self.last_refreshed_at, seconds=int(expires_in_seconds)
            )
        self.auth_status = "Active"

    def get_eligible_models(self) -> list[str]:
        """Return the list of model names allowed by this connection."""
        if not self.eligible_models:
            return []
        try:
            parsed = json.loads(self.eligible_models)
            return [str(m) for m in parsed] if isinstance(parsed, list) else []
        except Exception:
            return []

    def matches_model(self, model: str) -> bool:
        """Return True when no eligible-model allowlist is set or model is in it."""
        eligible = self.get_eligible_models()
        if not eligible:
            return True
        return model in eligible

    def is_expired(self, buffer_seconds: int = 300) -> bool:
        if not self.expires_at:
            return False
        expiry = get_datetime(self.expires_at)
        now = now_datetime()
        return (expiry.timestamp() - now.timestamp()) <= buffer_seconds

    def is_active_connection(self) -> bool:
        """True when the connection record is enabled and in an active state."""
        if not self.is_active:
            return False
        if self.auth_status in ("Revoked", "Unlinked", "Error"):
            return False
        return True

    def check_and_refresh(self) -> bool:
        """
        Checks if connection needs refresh and executes adapter refresh if required.
        Returns True if active/refreshed, False if re-authorization is required.
        """
        if not self.is_active:
            return False

        if self.auth_status in ("Revoked", "Unlinked"):
            return False

        if not self.is_expired():
            return True

        # Try refresh via adapter
        from huf.ai.providers.adapters import get_adapter
        try:
            adapter = get_adapter(self.adapter_type)
            success = adapter.refresh_connection(self)
            if success:
                self.save(ignore_permissions=True)
                return True
            else:
                self.auth_status = "Expired"
                self.save(ignore_permissions=True)
                return False
        except Exception as e:
            frappe.log_error(
                f"Failed to refresh AI Provider Connection {self.name}: {str(e)}",
                "AI Provider Connection Refresh Error"
            )
            self.auth_status = "Error"
            self.save(ignore_permissions=True)
            return False


def _can_access_connection(connection: "AIProviderConnection") -> bool:
    """Return True when the current user may read or mutate this connection."""
    if frappe.session.user == "Administrator":
        return True
    if "System Manager" in frappe.get_roles(frappe.session.user):
        return True
    return connection.user == frappe.session.user


@frappe.whitelist()
def check_connection_status(connection_name: str) -> dict:
    """Public status/refresh check for a subscription connection."""
    if not frappe.db.exists("AI Provider Connection", connection_name):
        frappe.throw(_("AI Provider Connection '{0}' not found.").format(connection_name))

    connection = frappe.get_doc("AI Provider Connection", connection_name)
    if not _can_access_connection(connection):
        frappe.throw(_("Not permitted to access this connection."), frappe.PermissionError)

    refreshed = connection.check_and_refresh()

    return {
        "name": connection.name,
        "auth_status": connection.auth_status,
        "is_active": connection.is_active,
        "expires_at": str(connection.expires_at) if connection.expires_at else None,
        "is_expired": connection.is_expired(),
        "refreshed": refreshed,
    }


@frappe.whitelist()
def get_subscription_connections(provider: str = None) -> list:
    """Return the current user's AI Provider Connections (admins see all)."""
    from huf.ai.providers.adapters import get_adapter

    filters = {}
    if not (frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles(frappe.session.user)):
        filters["user"] = frappe.session.user
    if provider:
        filters["provider"] = provider

    connections = frappe.get_all(
        "AI Provider Connection",
        filters=filters or None,
        fields=[
            "name",
            "connection_name",
            "user",
            "provider",
            "adapter_type",
            "auth_status",
            "auth_method",
            "is_active",
            "eligible_models",
            "account_email",
            "account_id",
            "expires_at",
            "modified",
        ],
        order_by="modified desc",
        limit_page_length=1000,
    )

    # Decorate with auth-method options from the adapter.
    result = []
    for conn in connections:
        conn_doc = frappe.get_doc("AI Provider Connection", conn.name)
        methods = []
        try:
            adapter = get_adapter(conn.adapter_type)
            methods = adapter.get_auth_methods()
        except Exception:
            methods = []
        conn["auth_methods"] = methods
        conn["is_expired"] = conn_doc.is_expired()
        result.append(conn)

    return result


@frappe.whitelist()
def get_subscription_auth_methods(adapter_type: str) -> list:
    """Return auth methods available for an adapter type."""
    from huf.ai.providers.adapters import get_adapter

    if not adapter_type:
        return []

    adapter = get_adapter(adapter_type)
    return adapter.get_auth_methods()


@frappe.whitelist()
def start_subscription_authorization(
    connection_name: str,
    mode: str,
    redirect_uri: str = None,
) -> dict:
    """Start authorization for a subscription connection and persist pending state."""
    from huf.ai.providers.adapters import get_adapter

    if not frappe.db.exists("AI Provider Connection", connection_name):
        frappe.throw(_("AI Provider Connection '{0}' not found.").format(connection_name))

    connection = frappe.get_doc("AI Provider Connection", connection_name)
    if not _can_access_connection(connection):
        frappe.throw(_("Not permitted to authorize this connection."), frappe.PermissionError)

    adapter = get_adapter(connection.adapter_type)
    auth_data = adapter.start_authorization(connection, mode=mode, redirect_uri=redirect_uri)
    connection.save(ignore_permissions=True)

    return auth_data


@frappe.whitelist()
def complete_subscription_authorization(
    connection_name: str,
    payload: dict = None,
) -> dict:
    """Complete authorization for a subscription connection."""
    from huf.ai.providers.adapters import get_adapter

    if not frappe.db.exists("AI Provider Connection", connection_name):
        frappe.throw(_("AI Provider Connection '{0}' not found.").format(connection_name))

    connection = frappe.get_doc("AI Provider Connection", connection_name)
    if not _can_access_connection(connection):
        frappe.throw(_("Not permitted to authorize this connection."), frappe.PermissionError)

    adapter = get_adapter(connection.adapter_type)
    result = adapter.complete_authorization(connection, payload or {})
    connection.save(ignore_permissions=True)

    return result


@frappe.whitelist()
def revoke_subscription_authorization(connection_name: str) -> dict:
    """Revoke/clear tokens for a subscription connection."""
    from huf.ai.providers.adapters import get_adapter

    if not frappe.db.exists("AI Provider Connection", connection_name):
        frappe.throw(_("AI Provider Connection '{0}' not found.").format(connection_name))

    connection = frappe.get_doc("AI Provider Connection", connection_name)
    if not _can_access_connection(connection):
        frappe.throw(_("Not permitted to revoke this connection."), frappe.PermissionError)

    adapter = get_adapter(connection.adapter_type)
    success = adapter.revoke_connection(connection)
    connection.save(ignore_permissions=True)

    return {"success": success, "auth_status": connection.auth_status}
