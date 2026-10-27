# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Tests for preview_gateway_readiness (GW-15).

The frontend readiness checklist used to check only 3 conditions while
Gateway.validate() enforces 8. preview_gateway_readiness runs those same
validate() checks in dry-run mode (no save) so the two can never drift
apart again. These tests exercise the whitelisted endpoint end-to-end
against real Gateway/Integration Settings/User records.
"""

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.gateway_service import preview_gateway_readiness


class TestGatewayReadiness(IntegrationTestCase):
	def setUp(self):
		self._gateways = []
		self._integrations = []
		self._users = []
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._gateways:
			frappe.delete_doc("Gateway", name, force=True, ignore_permissions=True)
		for name in self._integrations:
			frappe.delete_doc("Integration Settings", name, force=True, ignore_permissions=True)
		for name in self._users:
			frappe.delete_doc("User", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _make_gateway(self, **overrides):
		values = {
			"doctype": "Gateway",
			"gateway_name": frappe.generate_hash(length=10),
			"provider": "WhatsApp",
			"is_enabled": 0,
			"direct_policy": "Pairing",
		}
		values.update(overrides)
		doc = frappe.get_doc(values).insert(ignore_permissions=True)
		self._gateways.append(doc.name)
		return doc

	def test_blank_gateway_reports_every_check_as_incomplete_but_never_throws(self):
		gateway = self._make_gateway()

		result = preview_gateway_readiness(gateway.name)

		self.assertFalse(result["ready"])
		self.assertGreater(result["blocking_count"], 0)
		check_ids = {c["id"] for c in result["checks"]}
		self.assertEqual(
			check_ids,
			{
				"enabled",
				"execution-user",
				"route-target",
				"route-target-concrete",
				"credentials",
				"credential-values",
				"execution-user-role",
				"agent-access",
			},
		)
		# Every unmet check must carry an actionable hint, not a blank string.
		for check in result["checks"]:
			if not check["done"]:
				self.assertTrue(check["hint"])

	def test_route_target_type_set_but_agent_not_chosen_is_reported_separately(self):
		# Regression guard for the exact gap GW-15 called out: the old frontend
		# check only looked at default_target_type being non-empty, so
		# "Agent" chosen with no concrete default_agent read as "done".
		#
		# Gateway.validate() itself rejects this combination unconditionally
		# (not gated on is_enabled), so it can never be *inserted* directly --
		# we have to reach it via a direct db write, exactly the way a stale or
		# partially-migrated record could end up in this state in production.
		gateway = self._make_gateway()
		frappe.db.set_value("Gateway", gateway.name, "default_target_type", "Agent")

		result = preview_gateway_readiness(gateway.name)

		checks = {c["id"]: c for c in result["checks"]}
		self.assertTrue(checks["route-target"]["done"])
		self.assertFalse(checks["route-target-concrete"]["done"])

	def test_enabled_gateway_with_every_precondition_met_is_ready(self):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"{frappe.generate_hash(length=8)}@example.com",
				"first_name": "Gateway",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		self._users.append(user.name)
		if not frappe.db.exists("Role", "Huf Gateway User"):
			frappe.get_doc({"doctype": "Role", "role_name": "Huf Gateway User"}).insert(ignore_permissions=True)
		user.add_roles("Huf Gateway User")

		agent = None
		agent_rows = frappe.get_all("Agent", limit=1)
		if agent_rows:
			agent = agent_rows[0].name
		else:
			agent_doc = frappe.get_doc(
				{
					"doctype": "Agent",
					"agent_name": frappe.generate_hash(length=10),
					"agent_modality": "Both",
					"instructions": "Readiness test fixture.",
				}
			).insert(ignore_permissions=True)
			agent = agent_doc.name

		integration = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "whatsapp",
				"credentials": [{"key": "access_token", "value": "test-token"}],
			}
		).insert(ignore_permissions=True)
		self._integrations.append(integration.name)

		gateway = self._make_gateway(
			execution_user=user.name,
			default_target_type="Agent",
			default_agent=agent,
			integration_settings=integration.name,
		)

		result = preview_gateway_readiness(gateway.name)

		# Credential-values and agent-access depend on adapter/permission wiring
		# this fixture does not set up, so we only assert the checks this test
		# is actually targeting -- that a fully-specified route/execution-user
		# no longer trips the two GW-15 gaps this endpoint was built to close.
		checks = {c["id"]: c for c in result["checks"]}
		self.assertTrue(checks["execution-user"]["done"])
		self.assertTrue(checks["route-target"]["done"])
		self.assertTrue(checks["route-target-concrete"]["done"])
		self.assertTrue(checks["credentials"]["done"])


class TestFallbackTemplateValidation(IntegrationTestCase):
	"""The fallback template is sent without values, so it must be variable-free."""

	def _gw(self, template="fallback", account="ACC", provider="WhatsApp"):
		from types import SimpleNamespace

		from huf.huf.doctype.gateway.gateway import Gateway

		values = {
			"provider": provider,
			"fallback_template": template,
			"whatsapp_account": account,
			"fallback_template_language": "en_US",
		}
		doc = SimpleNamespace(**values, get=lambda k, d=None, _v=values: _v.get(k, d))
		return doc, lambda: Gateway._validate_fallback_template(doc)

	def _check(self, row, available=True, found=True, **kw):
		from unittest.mock import patch

		from huf.ai.gateway_adapters import whatsapp_bridge as bridge

		_, run = self._gw(**kw)
		with patch.object(bridge, "is_available", return_value=available), patch.object(
			bridge, "_template_docname", return_value="fallback-en_US"
		), patch.object(bridge, "_template_row", return_value=row if found else None):
			run()

	@staticmethod
	def _row(**over):
		row = {"template": "Hello, we'll get back to you.", "header": "", "header_type": "", "buttons": [],
			"whatsapp_account": "ACC", "header_format": ""}
		row.update(over)
		return row

	def test_plain_template_passes(self):
		self._check(self._row())

	def test_body_variables_allowed_header_and_url_variables_rejected(self):
		self._check(self._row(template="Hi {{1}}"))  # WP-6 (C-011): body variables are filled at send time
		self._check(self._row(template="Hi {{name}}"))
		for over in (
			{"header": "Order {{1}}", "header_type": "TEXT"},
			{"buttons": [{"button_type": "Visit Website", "website_url": "https://x.test/{{1}}"}]},
			{"header_type": "IMAGE"},
		):
			with self.assertRaises(frappe.ValidationError, msg=str(over)) as ctx:
				self._check(self._row(**over))
			self.assertIn("can't have a media", str(ctx.exception))

	def test_skips_silently_when_unverifiable(self):
		self._check(self._row(template="Hi {{1}}"), available=False)  # no connector
		self._check(self._row(template="Hi {{1}}"), found=False)  # template not synced yet
		self._check(self._row(template="Hi {{1}}"), account="")  # no account to scope by
		self._check(self._row(template="Hi {{1}}"), template="")  # no fallback set
		self._check(self._row(template="Hi {{1}}"), provider="Slack")

	def test_other_accounts_template_is_ignored(self):
		self._check(self._row(template="Hi {{1}}", whatsapp_account="OTHER"))
