import frappe
from frappe import _
from frappe.model.document import Document

from huf.ai.gateway_adapters.provider_ids import provider_to_service_id
from huf.ai.gateway_adapters.registered import get_adapter_class


class Gateway(Document):
    """A configured inbound/outbound messaging account.

    Credentials remain in the provider integration. A Gateway owns the
    inbound trust boundary, routing policy, and execution principal.
    """

    def validate(self):
        if self.is_enabled and not self.execution_user:
            frappe.throw(_("Enabled gateways need a Run as user. Use a least-privileged service user."))

        if self.default_target_type == "Agent" and not self.default_agent:
            frappe.throw(_("Choose a default agent or clear the default route."))
        if self.default_target_type == "Flow" and not self.default_flow:
            frappe.throw(_("Choose a default flow or clear the default route."))
        if self.direct_policy == "Open":
            frappe.throw(_("Public direct-message gateways are not available in this release."))

        # Every provider gets the same "linked Integration Settings must match
        # this provider's service" check now, via the one canonical
        # provider -> service_name transform (see provider_to_service_id).
        # This used to only cover 4 of 12 providers (VK, WeCom, WhatsApp,
        # Telegram); the other 8 previously had no such validation at all.
        # Gated on is_enabled, same as before, so a disabled gateway with a
        # stale/mismatched linked integration still saves.
        expected_service = provider_to_service_id(self.provider) if self.provider else None
        if expected_service and self.is_enabled:
            if not self.integration_settings:
                frappe.throw(_("Enabled {0} gateways need a connected integration.").format(self.provider))
            integration = frappe.get_doc("Integration Settings", self.integration_settings)
            if integration.service != expected_service:
                frappe.throw(
                    _("The connected integration must use the {0} service.").format(expected_service)
                )

        # ST-04.4: Validate required credentials are set
        if self.is_enabled and self.provider:
            self._validate_required_credentials()

        # ST-04.4: Constrain execution_user to allowed role
        if self.is_enabled and self.execution_user:
            self._validate_execution_user_role()

        # ST-04.4: Verify execution_user has access to default_agent if set
        if self.is_enabled and self.execution_user and self.default_agent:
            self._validate_agent_access()

    def _validate_required_credentials(self):
        """Verify that required credentials per the adapter schema are configured.

        Required credentials are looked up in Integration Settings.credentials
        child table by their 'key' field (verbatim match).
        Special case: Slack provider uses signing_secret key (not in adapter schema).
        """
        # Special case for Slack: requires signing_secret (in slack_events.py, not adapter)
        if self.provider == "Slack":
            self._validate_slack_signing_secret()
            return

        # For other providers, use the adapter's credential_schema
        try:
            adapter_cls = get_adapter_class(self._provider_id_for_adapter())
        except KeyError:
            # Unknown provider, skip credential check
            return

        if not hasattr(adapter_cls, "credential_schema"):
            return

        # Load credentials from Integration Settings
        credentials = self._load_integration_credentials()

        # Check each required field in the adapter's credential_schema
        for field in adapter_cls.credential_schema.fields:
            if not field.required:
                continue

            key = field.key
            value = credentials.get(key, "")
            if not value or not str(value).strip():
                frappe.throw(
                    _("Gateway {0} ({1}) requires '{2}' to be configured in Integration Settings.").format(
                        self.name, self.provider, field.label
                    )
                )

    def _validate_slack_signing_secret(self):
        """Special validation for Slack's signing_secret (not in adapter schema)."""
        if not self.integration_settings:
            frappe.throw(_("Slack gateways need a connected integration with signing_secret configured."))

        credentials = self._load_integration_credentials()
        if not credentials.get("signing_secret"):
            frappe.throw(
                _("Slack Gateway {0} requires 'signing_secret' in Integration Settings credentials.").format(
                    self.name
                )
            )

    def _load_integration_credentials(self) -> dict:
        """Load credentials from Integration Settings.credentials child table."""
        if not self.integration_settings:
            return {}

        try:
            settings = frappe.get_doc("Integration Settings", self.integration_settings)
            credentials = {}
            for row in settings.credentials or []:
                if row.key:
                    credentials[row.key] = row.get_password("value") or ""
            return credentials
        except frappe.DoesNotExistError:
            return {}

    def _provider_id_for_adapter(self) -> str:
        """Map provider name to adapter provider_id.

        Most providers map directly, but some differ (e.g., "Microsoft Teams" -> "microsoft_teams").
        """
        from huf.ai.gateway_adapters.provider_ids import provider_to_service_id
        service_id = provider_to_service_id(self.provider)
        return service_id or self.provider.lower().replace(" ", "_")

    def _validate_execution_user_role(self):
        """Ensure execution_user is in an allowed role.

        Allowed roles (configurable via frappe.conf, defaults to "Huf Gateway User").
        """
        user_doc = frappe.get_doc("User", self.execution_user)
        allowed_roles = frappe.get_hooks("huf_gateway_execution_roles") or ["Huf Gateway User"]

        user_roles = set(role.role for role in user_doc.get("roles", []))
        if not user_roles.intersection(set(allowed_roles)):
            frappe.throw(
                _("Gateway {0}: execution_user '{1}' must have one of these roles: {2}").format(
                    self.name, self.execution_user, ", ".join(allowed_roles)
                )
            )

    def _validate_agent_access(self):
        """Verify execution_user has access to the default_agent."""
        from huf.ai.agent_access import check_agent_access

        agent = frappe.get_doc("Agent", self.default_agent)
        if not check_agent_access(agent, self.execution_user, for_execution=True):
            frappe.throw(
                _("Gateway {0}: execution_user '{1}' does not have access to agent '{2}'.").format(
                    self.name, self.execution_user, self.default_agent
                )
            )
