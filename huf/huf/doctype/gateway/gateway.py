import json

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
        hours = self.get("telegram_web_session_hours")
        if hours is not None and hours != 0 and not 1 <= int(hours) <= 720:
            frappe.throw(_("Telegram session length must be between 1 and 720 hours."))

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

        # WhatsApp: derive the indexed phone_number_id and enforce number uniqueness / account linking
        self._validate_whatsapp()
        self._validate_fallback_template()
        self._validate_consent_settings()
        self._validate_reply_settings()
        self._validate_send_scope()
        self._validate_telegram_settings()

        # ST-04.4: Validate required credentials are set
        if self.is_enabled and self.provider:
            self._validate_required_credentials()

        # ST-04.4: Constrain execution_user to allowed role
        if self.is_enabled and self.execution_user:
            self._validate_execution_user_role()

        # ST-04.4: Verify execution_user has access to default_agent if set
        if self.is_enabled and self.execution_user and self.default_agent:
            self._validate_agent_access()

    def _validate_telegram_settings(self):
        """Telegram-only checks; other providers are untouched."""
        if self.provider != "Telegram":
            return
        if self.get("telegram_join_policy") == "Agent" and not self.default_agent:
            frappe.throw(_("Group join requests handled by an agent need a default agent. Choose one first."))
        if self.get("telegram_business_policy") in ("Draft", "Reply") and not (
            (self.default_target_type == "Agent" and self.default_agent)
            or (self.default_target_type == "Flow" and self.default_flow)
        ):
            frappe.throw(
                _("Business chats set to {0} need a default agent or flow to write the replies.").format(
                    self.telegram_business_policy
                )
            )
        cooldown = self.get("telegram_welcome_cooldown_seconds")
        if cooldown not in (None, "") and int(cooldown) < 0:
            frappe.throw(_("Welcome cooldown cannot be negative."))
        captcha = self.get("telegram_guard_captcha") or "Off"
        if captcha != "Off" and (self.get("telegram_join_policy") or "Queue") == "Decline":
            frappe.throw(_("Join verification cannot be used while group join requests are set to Decline."))
        raw = (self.get("telegram_bot_allowlist") or "").strip()
        if raw:
            parts = [p.strip() for p in raw.replace("\n", ",").split(",") if p.strip()]
            bad = [p for p in parts if not p.isdigit()]
            if bad:
                frappe.throw(
                    _("Allowed bots must be numeric Telegram bot IDs separated by commas. Not valid: {0}").format(
                        ", ".join(bad[:5])
                    )
                )
            self.telegram_bot_allowlist = ", ".join(parts)
        for fieldname, label, low, high in (
            ("telegram_bot_max_hops", _("Bot messages in a row"), 1, 20),
            ("telegram_bot_rate_cap", _("Bot messages per minute"), 1, 1000),
        ):
            value = self.get(fieldname)
            if value is not None and not low <= int(value) <= high:
                frappe.throw(_("{0} must be between {1} and {2}.").format(label, low, high))

    def _validate_whatsapp(self):
        """Derive ``phone_number_id`` and enforce the one-enabled-gateway-per-number rule.

        The number is stored (read-only, indexed) from the connected Integration Settings
        credential row. Two ENABLED WhatsApp gateways may not share one; a disabled gateway
        may keep a duplicate. When frappe_whatsapp is installed and a WhatsApp Account is
        linked, the account must exist and carry the same phone id.
        """
        if self.provider != "WhatsApp":
            self.phone_number_id = ""
            return
        credentials = self._load_integration_credentials()
        self.phone_number_id = str(credentials.get("phone_number_id") or "").strip()
        if not self.is_enabled:
            return

        if self.phone_number_id:
            other = frappe.db.get_value(
                "Gateway",
                {
                    "provider": "WhatsApp",
                    "is_enabled": 1,
                    "phone_number_id": self.phone_number_id,
                    "name": ["!=", self.name or ""],
                },
                "name",
            )
            if other:
                frappe.throw(
                    _(
                        "WhatsApp phone number ID {0} is already used by the enabled gateway {1}. "
                        "Each enabled WhatsApp gateway needs its own phone number; disable {1} first or use a different number."
                    ).format(self.phone_number_id, other)
                )

        account = (self.get("whatsapp_account") or "").strip()
        if not account:
            return
        from huf.ai.gateway_adapters import whatsapp_bridge as bridge

        if not bridge.is_available():
            return  # frappe_whatsapp absent: the link is inert, nothing to validate against
        if not frappe.db.exists("WhatsApp Account", account):
            frappe.throw(_("WhatsApp Account {0} does not exist.").format(account))

        # One account (and so one token) per enabled gateway: gateway B must not send with A's token.
        shared = frappe.db.get_value(
            "Gateway",
            {
                "provider": "WhatsApp",
                "is_enabled": 1,
                "whatsapp_account": account,
                "name": ["!=", self.name or ""],
            },
            "name",
        )
        if shared:
            frappe.throw(
                _("WhatsApp Account {0} is already linked to the enabled gateway {1}. Each enabled gateway needs its own account.").format(
                    account, shared
                )
            )

        account_phone = str(frappe.db.get_value("WhatsApp Account", account, "phone_id") or "").strip()
        if not self.phone_number_id:
            frappe.throw(
                _("Add the phone_number_id credential to this gateway's integration before linking WhatsApp Account {0}.").format(
                    account
                )
            )
        if account_phone != self.phone_number_id:
            frappe.throw(
                _(
                    "WhatsApp Account {0} uses phone number ID {1}, but this gateway's integration uses {2}. "
                    "Link the account that belongs to this number."
                ).format(account, account_phone or _("(none)"), self.phone_number_id)
            )

    def _validate_fallback_template(self):
        """The fallback template may have body variables but no media/location header.

        Body variables are filled from ``fallback_template_params`` (or the contact name by default); when
        params are configured their count must match the template's variables. Checked only when
        frappe_whatsapp is installed, an account is linked and the template row is already known;
        otherwise it cannot be verified here (health warns about it instead).
        """
        if self.provider != "WhatsApp":
            return
        template = (self.get("fallback_template") or "").strip()
        account = (self.get("whatsapp_account") or "").strip()
        if not template or not account:
            return
        from huf.ai.gateway_adapters import whatsapp_bridge as bridge
        from huf.ai.gateway_adapters.whatsapp_templates import variables

        if not bridge.is_available():
            return
        try:
            language = (self.get("fallback_template_language") or "").strip() or None
            docname = bridge._template_docname(account, template, language)
            row = bridge._template_row(docname)
        except Exception:
            return  # not found yet / ambiguous language: nothing to verify
        if not row or row.get("whatsapp_account") != account:
            return
        media_header = str(row.get("header_format") or row.get("header_type") or "").upper() in {
            "IMAGE",
            "VIDEO",
            "DOCUMENT",
            "LOCATION",
        }
        header_vars = variables(row.get("header") or "")
        url_vars = any(variables(b.get("website_url") or "") for b in row.get("buttons") or [])
        if media_header or header_vars or url_vars:
            frappe.throw(
                _(
                    "The fallback template can't have a media, location or variable header, or a button URL "
                    "variable (only body variables are filled). Pick a template with a plain header."
                )
            )
        params = (self.get("fallback_template_params") or "").strip()
        if params:
            try:
                parsed = json.loads(params)
            except ValueError:
                parsed = None
            if not isinstance(parsed, (list, dict)):
                frappe.throw(_("Fallback template params must be a JSON list or a {name: value} map."))
            expected = len(variables(row.get("template") or ""))
            if len(parsed) != expected:
                frappe.throw(
                    _("The fallback template has {0} body variable(s) but {1} param(s) are configured.").format(
                        expected, len(parsed)
                    )
                )

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

        from huf.permissions import has_capability

        if not has_capability(self.execution_user, "agent.use"):
            frappe.throw(
                _(
                    "Execution user {0} lacks the agent.use capability; give the user the Huf Gateway User role."
                ).format(self.execution_user)
            )

    def _validate_agent_access(self):
        """Verify execution_user has access to the default_agent."""
        from huf.ai.agent.access import check_agent_access

        agent = frappe.get_doc("Agent", self.default_agent)
        if not check_agent_access(agent, self.execution_user, for_execution=True):
            frappe.throw(
                _("Gateway {0}: execution_user '{1}' does not have access to agent '{2}'.").format(
                    self.name, self.execution_user, self.default_agent
                )
            )

    def _validate_reply_settings(self):
        attempts = self.get("retry_max_attempts")
        if attempts is not None and not 0 <= int(attempts) <= 10:
            frappe.throw(_("Reply send attempts must be between 1 and 10 (0 uses the default of 4)."))
        text = (self.get("error_reply_text") or "").strip()
        if len(text) > 1000:
            frappe.throw(_("Error reply text must be 1000 characters or fewer."))
        if self.get("voice_reply_mode") not in (None, "", "Off", "Voice only", "Text and voice"):
            frappe.throw(_("Voice note replies must be Off, Voice only or Text and voice."))
        if self.get("voice_reply_mode") in ("Voice only", "Text and voice") and self.provider not in (
            "WhatsApp",
            "Telegram",
        ):
            frappe.throw(_("Voice note replies are only available for WhatsApp and Telegram gateways."))
        self._warn_voice_ffmpeg()
        if self.get("preview_url") not in (None, "", "Default (off)", "On", "Off"):
            frappe.throw(_("Link previews must be Default (off), On or Off."))

    def _warn_voice_ffmpeg(self):
        """Warn (never block: the worker host may differ from this one) when ffmpeg/libopus is missing here."""
        if self.get("voice_reply_mode") not in ("Voice only", "Text and voice"):
            return
        from huf.ai.whatsapp.send_file import ffmpeg_status

        status = ffmpeg_status()
        if not (status.get("available") and status.get("has_libopus")):
            frappe.msgprint(
                _(
                    "Voice replies need ffmpeg with Opus support, and it was not found on this server. "
                    "Install it on every worker host, or replies will be sent as text."
                ),
                indicator="orange",
                alert=True,
            )

    def _validate_send_scope(self):
        """Agent send scope (WhatsApp): a known scope, a real allow-list when chosen, non-negative caps."""
        if self.provider != "WhatsApp":
            return
        from huf.ai.whatsapp import send_scope as send_scope

        scope = self.get("agent_recipient_scope") or send_scope.DEFAULT_SCOPE
        if scope not in send_scope.SCOPES:
            frappe.throw(_("Agent recipient scope must be one of: {0}.").format(", ".join(send_scope.SCOPES)))
        raw = self.get("agent_recipient_allowlist") or ""
        if str(raw).strip():
            bad = send_scope.invalid_allowlist_entries(raw)
            if bad:
                frappe.throw(_("Not a phone number in the allowed recipients: {0}").format(", ".join(bad)))
        if scope == "Allow-list" and not send_scope.parse_allowlist(raw):
            frappe.throw(_("Add at least one number to the allowed recipients, or choose another recipient scope."))
        for field, label in (("agent_send_cap_per_run", _("Agent sends per run")), ("agent_send_cap_per_day", _("Agent sends per day"))):
            value = self.get(field)
            if value is not None and int(value) < 0:
                frappe.throw(_("{0} must be 0 (no limit) or more.").format(label))

    def _validate_consent_settings(self):
        limit = self.get("inbound_sender_limit")
        if limit is not None and int(limit) < 0:
            frappe.throw(_("Inbound messages per sender must be 0 (off) or more."))

        from huf.ai.gateway_service import _keyword_set

        opt_out = _keyword_set(self, "opt_out_keywords", "")
        opt_in = _keyword_set(self, "opt_in_keywords", "")
        overlap = opt_out & opt_in
        if overlap:
            frappe.throw(
                _("A keyword cannot be both an opt-out and an opt-in keyword: {0}").format(", ".join(sorted(overlap)))
            )
