"""Migration patch: Disable existing Gateways with unset required credentials (ST-04.6).

Per WP-04, signature verification is now mandatory and fail-closed. This patch
disables any Gateway whose required credentials are not configured, logs remediation
steps, and marks it disabled in the description field.

Affected credentials per provider (see WP-04 credential-discovery mapping):
- SMS: auth_token (when using Twilio, not frappe_sms)
- Email: webhook_secret
- Telegram: webhook_secret
- WhatsApp: app_secret
- Google Chat: verification_token
- Messenger: app_secret
- Instagram: app_secret
- Slack: signing_secret (special case, not in adapter schema)

Teams, Discord, VK, WeCom: already had these credentials required, no change.
"""

import frappe
from datetime import datetime


def execute():
    """Disable Gateways with missing required credentials."""
    gateways = frappe.get_all("Gateway", pluck="name")
    if not gateways:
        return

    disabled_count = 0
    disabled_list = []

    for gateway_name in gateways:
        try:
            gateway = frappe.get_doc("Gateway", gateway_name)
        except frappe.DoesNotExistError:
            continue

        missing_credentials = _check_required_credentials(gateway)
        if missing_credentials:
            _disable_gateway(gateway, missing_credentials)
            disabled_count += 1
            disabled_list.append(f"{gateway_name} ({gateway.provider}): {', '.join(missing_credentials)}")

    if disabled_count > 0:
        frappe.logger("huf.patches").warning(
            f"Disabled {disabled_count} Gateways with missing required credentials:\n"
            + "\n".join(f"  - {item}" for item in disabled_list)
            + "\nSee patch huf.patches.v1.disable_gateway_without_credentials for details."
        )


def _check_required_credentials(gateway) -> list[str]:
    """Return list of missing required credential field names for this gateway.

    Looks up credentials in Integration Settings.credentials child table.
    Special case for Slack: checks for signing_secret key directly.
    """
    missing = []

    # Load credentials from Integration Settings
    credentials = _load_integration_credentials(gateway.integration_settings)

    # Per credential-discovery mapping (WP-04 before ST-04.4)
    required_by_provider = {
        "sms": [("auth_token", "Twilio Auth Token (required when using Twilio mode)", lambda v: v and gateway.name)],
        "email": [("webhook_secret", "Email Webhook Secret")],
        "telegram": [("webhook_secret", "Telegram Webhook Secret")],
        "whatsapp": [("app_secret", "WhatsApp App Secret")],
        "google_chat": [("verification_token", "Google Chat Verification Token")],
        "messenger": [("app_secret", "Messenger App Secret")],
        "instagram": [("app_secret", "Instagram App Secret")],
        "slack": [("signing_secret", "Slack Signing Secret")],
    }

    # Check SMS: special case for frappe_sms mode (doesn't need auth_token)
    if gateway.provider == "SMS":
        account_sid = credentials.get("account_sid", "").strip()
        if account_sid != "frappe_sms":
            # Twilio mode: auth_token is required
            if not credentials.get("auth_token"):
                missing.append("auth_token")

    # Check other providers
    provider_lower = gateway.provider.lower().replace(" ", "_")

    if provider_lower in required_by_provider:
        for key, label in required_by_provider[provider_lower]:
            if not credentials.get(key):
                missing.append(f"{key} ({label})")

    return missing


def _load_integration_credentials(integration_settings_name: str) -> dict:
    """Load credentials from Integration Settings.credentials child table."""
    if not integration_settings_name:
        return {}

    try:
        settings = frappe.get_doc("Integration Settings", integration_settings_name)
        credentials = {}
        for row in settings.credentials or []:
            if row.key:
                credentials[row.key] = row.get_password("value") or ""
        return credentials
    except (frappe.DoesNotExistError, AttributeError):
        return {}


def _disable_gateway(gateway, missing_credentials: list[str]):
    """Mark gateway as disabled and add note to description."""
    today = datetime.now().strftime("%Y-%m-%d")
    note = (
        f"[DISABLED on {today}] Missing required credentials: {', '.join(missing_credentials)}. "
        f"Re-enable after configuring {gateway.provider} in Integration Settings. "
        "See WP-04 (fail-closed gateway verification) for details."
    )

    try:
        # Append note to description
        existing_desc = (gateway.description or "").strip()
        if existing_desc and not existing_desc.endswith("\n"):
            existing_desc += "\n"
        new_desc = existing_desc + note

        # Update database directly to avoid validation
        frappe.db.set_value(
            "Gateway",
            gateway.name,
            {
                "is_enabled": 0,
                "description": new_desc,
            },
            update_modified=False,
        )

        frappe.db.commit()
    except Exception as e:
        frappe.logger("huf.patches").error(
            f"Could not disable gateway {gateway.name}: {e}"
        )
