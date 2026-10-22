"""FIX-F: least-privilege gateway Run-as user.

Covers
1. the five runtime has_permission hooks (Frappe 16 treats a falsy hook result,
   including None, as DENY) for a create/read/write/delete matrix,
2. the first-class ``Huf Gateway User`` role (capabilities, role resolution),
3. a REAL end-to-end gateway run (``process_gateway_event`` -> ``run_agent_sync``)
   as a user holding only ``Huf Gateway User``. Only the LLM provider boundary
   (the HUF Test Provider) and the outbound channel send are faked.

Run with: bench --site <site> run-tests --module huf.ai.tests.test_gateway_runas_user
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from huf.ai import hooks as ai_hooks
from huf.permissions import (
	DEFAULT_ROLE_CAPABILITIES,
	HUF_ROLE_FRAPPE_ROLE_MAP,
	get_user_capabilities,
	get_user_huf_role,
	has_capability,
)

GATEWAY_ROLE = "Huf Gateway User"
PREFIX = "fixf"


def _email(tag):
	return f"{PREFIX}-{tag}-{frappe.generate_hash(length=6)}@example.com"


def _make_user(tag, roles):
	user = frappe.get_doc(
		{"doctype": "User", "email": _email(tag), "first_name": tag, "send_welcome_email": 0}
	)
	for role in roles:
		user.append("roles", {"role": role})
	user.insert(ignore_permissions=True)
	return user.name


class TestRuntimeHooksPermissionMatrix(unittest.TestCase):
	"""All five hooks: create must never be denied by the hook itself."""

	HOOKS = {
		"Agent Run": (ai_hooks.has_permission_agent_run, "owner"),
		"Agent Message": (ai_hooks.has_permission_agent_message, "conversation"),
		"Agent Conversation": (ai_hooks.has_permission_agent_conversation, "owner"),
		"Agent Tool Call": (ai_hooks.has_permission_agent_tool_call, "agent_run"),
		"Agent Context Artifact": (ai_hooks.has_permission_agent_context_artifact, "conversation"),
	}

	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.owner = _make_user("owner", ["Huf User"])
		cls.other = _make_user("other", ["Huf User"])
		cls.sysmgr = _make_user("sm", ["System Manager"])
		cls.gateway = _make_user("gw", [GATEWAY_ROLE])
		cls._users = [cls.owner, cls.other, cls.sysmgr, cls.gateway]

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _doc(self, doctype):
		_, link = self.HOOKS[doctype]
		if link == "owner":
			return SimpleNamespace(doctype=doctype, owner=self.owner)
		# child-of-parent doctypes resolve the owner via the parent's owner lookup
		return SimpleNamespace(doctype=doctype, owner=self.owner, **{link: "PARENT-1"})

	def _call(self, doctype, ptype, user):
		fn, _ = self.HOOKS[doctype]
		real_get_value = frappe.db.get_value

		def get_value(dt, name=None, *args, **kwargs):
			if dt in ("Agent Conversation", "Agent Run") and name == "PARENT-1":
				return self.owner
			return real_get_value(dt, name, *args, **kwargs)

		with patch.object(frappe.db, "get_value", side_effect=get_value):
			return fn(self._doc(doctype), ptype=ptype, user=user)

	def test_create_is_not_denied_for_anyone(self):
		for doctype in self.HOOKS:
			for user in self._users:
				with self.subTest(doctype=doctype, user=user):
					# True, not None: Frappe 16 denies on any falsy hook result.
					self.assertIs(self._call(doctype, "create", user), True)

	def test_unrestricted_ptypes_return_true_not_none(self):
		for doctype in self.HOOKS:
			for ptype in ("create", "submit", "cancel", "print", "email", "export", "share", None):
				with self.subTest(doctype=doctype, ptype=ptype):
					self.assertIs(self._call(doctype, ptype, self.other), True)

	def test_read_write_delete_unchanged(self):
		for doctype in self.HOOKS:
			for ptype in ("read", "select", "write", "save", "delete"):
				with self.subTest(doctype=doctype, ptype=ptype):
					self.assertTrue(self._call(doctype, ptype, self.owner))
					self.assertTrue(self._call(doctype, ptype, self.sysmgr))
					self.assertFalse(self._call(doctype, ptype, self.other))
					self.assertFalse(self._call(doctype, ptype, self.gateway))

	def test_hooks_via_frappe_controller_check_create_is_allowed(self):
		"""The real framework path: has_controller_permissions must not deny create."""
		from frappe.permissions import has_controller_permissions

		doc = frappe.new_doc("Agent Conversation")
		for user in self._users:
			with self.subTest(user=user):
				self.assertTrue(has_controller_permissions(doc, "create", user=user))


class TestGatewayUserRole(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)

	def test_role_is_seeded_with_only_agent_use(self):
		self.assertTrue(frappe.db.exists("Role", GATEWAY_ROLE))
		self.assertTrue(frappe.db.exists("Huf Role", GATEWAY_ROLE))
		self.assertEqual(DEFAULT_ROLE_CAPABILITIES[GATEWAY_ROLE], ["agent.use"])
		self.assertEqual(HUF_ROLE_FRAPPE_ROLE_MAP[GATEWAY_ROLE], GATEWAY_ROLE)
		rows = frappe.get_all("Huf Role Permission", filters={"parent": GATEWAY_ROLE}, pluck="capability")
		self.assertEqual(rows, ["agent.use"])

	def test_gateway_role_only_user_has_only_agent_use(self):
		user = _make_user("gwcap", [GATEWAY_ROLE])
		frappe.cache().delete_value(f"huf_user_capabilities::{user}")
		self.assertEqual(get_user_huf_role(user), GATEWAY_ROLE)
		self.assertEqual(get_user_capabilities(user), ["agent.use"])
		for cap in ("agent.create", "developer.keys.manage", "ssh.run", "code_execution.run", "chat.view_all"):
			self.assertFalse(has_capability(user, cap), cap)

	def test_higher_huf_role_wins_and_gateway_adds_nothing(self):
		viewer = _make_user("gwviewer", ["Huf Viewer", GATEWAY_ROLE])
		user = _make_user("gwuser", ["Huf User", GATEWAY_ROLE])
		self.assertEqual(get_user_huf_role(viewer), "Huf Viewer")
		self.assertEqual(get_user_huf_role(user), "Huf User")
		self.assertCountEqual(
			get_user_capabilities(viewer), DEFAULT_ROLE_CAPABILITIES["Huf Viewer"]
		)

	def test_install_seeding_is_idempotent(self):
		from huf.install import create_huf_roles

		with patch.object(frappe.db, "commit"):
			create_huf_roles()
			create_huf_roles()
		rows = frappe.get_all("Huf Role Permission", filters={"parent": GATEWAY_ROLE}, pluck="capability")
		self.assertEqual(rows, ["agent.use"])


class TestGatewayRunAsUserEndToEnd(unittest.TestCase):
	"""Real run as a least-privilege user. Only the provider/LLM and channel send are faked."""

	def setUp(self):
		frappe.set_user("Administrator")
		self._cleanup = []
		suffix = frappe.generate_hash(length=6)
		self.exec_user = _make_user("e2e", [GATEWAY_ROLE])
		self.assertEqual(frappe.get_roles(self.exec_user).count("System Manager"), 0)

		from huf.testing.factories import make_agent, make_ai_model, make_ai_provider

		if frappe.db.exists("AI Provider", "Test_Provider"):
			provider = frappe.get_doc("AI Provider", "Test_Provider")
		else:
			provider = make_ai_provider(provider_name="Test_Provider")
		model = make_ai_model(provider=provider.name, model_name=f"fixf-model-{suffix}")
		self.agent = make_agent(
			agent_name=f"FixF Agent {suffix}",
			provider=provider.name,
			model=model.name,
			allowed_users=[{"user": self.exec_user}],
		)
		self.integration = frappe.get_doc(
			{
				"doctype": "Integration Settings",
				"service": "whatsapp",
				"credentials": [
					{"key": "phone_number_id", "value": f"55{suffix}"},
					{"key": "access_token", "value": "fixf-token"},
					{"key": "webhook_verify_token", "value": "fixf-verify"},
					{"key": "app_secret", "value": "fixf-secret"},
				],
			}
		).insert(ignore_permissions=True)
		self.gateway = frappe.get_doc(
			{
				"doctype": "Gateway",
				"gateway_name": f"FixF WhatsApp {suffix}",
				"provider": "WhatsApp",
				"is_enabled": 1,
				"execution_user": self.exec_user,
				"direct_policy": "Allow list",
				"default_target_type": "Agent",
				"default_agent": self.agent.name,
				"integration_settings": self.integration.name,
			}
		).insert(ignore_permissions=True)
		self.event = frappe.get_doc(
			{
				"doctype": "Gateway Event",
				"gateway": self.gateway.name,
				"idempotency_key": f"fixf-{suffix}",
				"provider_event_id": f"wamid.fixf{suffix}",
				"status": "Queued",
				"target_type": "Agent",
				"target_agent": self.agent.name,
				"sender_id": "15559870000",
				"conversation_id": "15559870000",
				"message_text": "__TEST_SCENARIO__:TEST_TEXT hello",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		self.addCleanup(self._teardown, suffix)

	def _teardown(self, suffix):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for dt, filters in (
			("Agent Message", {"agent": self.agent.name}),
			("Agent Run", {"agent": self.agent.name}),
			("Agent Conversation", {"agent": self.agent.name}),
			("Gateway Event", {"gateway": self.gateway.name}),
		):
			try:
				for name in frappe.get_all(dt, filters=filters, pluck="name"):
					frappe.delete_doc(dt, name, ignore_permissions=True, force=True)
			except Exception:
				pass
		for dt, name in (
			("Gateway", self.gateway.name),
			("Integration Settings", self.integration.name),
			("Agent", self.agent.name),
			("User", self.exec_user),
		):
			try:
				frappe.delete_doc(dt, name, ignore_permissions=True, force=True)
			except Exception:
				pass
		frappe.db.commit()

	def _process(self):
		from huf.ai.gateway_service import process_gateway_event

		sent = []

		def fake_send(gateway, event, parts, quote=True):
			sent.append("\n".join(parts))
			return SimpleNamespace(provider_message_id="wamid.OUT1", provider_response={})

		with (
			patch("huf.ai.gateway_webhook.send_gateway_parts", side_effect=fake_send),
			patch("huf.ai.gateway_service._throttle_outbound_send", lambda *a, **k: None),
		):
			try:
				result = process_gateway_event(self.event.name)
			finally:
				frappe.set_user("Administrator")
		return result, sent

	def test_least_privilege_user_completes_real_run(self):
		result, sent = self._process()
		event = frappe.get_doc("Gateway Event", self.event.name)
		self.assertEqual(event.status, "Succeeded", event.error_message)
		self.assertEqual(result["status"], "Succeeded")
		self.assertEqual(len(sent), 1)
		self.assertTrue(sent[0].strip())
		run = frappe.get_doc("Agent Run", event.agent_run)
		self.assertEqual(run.owner, self.exec_user)
		conv = frappe.get_doc("Agent Conversation", run.conversation)
		self.assertEqual(conv.owner, self.exec_user)

	def test_gateway_user_boundaries(self):
		# Seed a conversation owned by someone else.
		other = _make_user("victim", ["Huf User"])
		frappe.set_user(other)
		conv = frappe.get_doc(
			{"doctype": "Agent Conversation", "agent": self.agent.name, "session_id": f"s-{frappe.generate_hash(length=8)}"}
		).insert()
		frappe.set_user(self.exec_user)
		try:
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc("Agent Conversation", conv.name).check_permission("read")
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc("Agent Conversation", conv.name).check_permission("write")
			self.assertFalse(frappe.has_permission("Agent", "create", user=self.exec_user))
			self.assertFalse(frappe.has_permission("Agent", "write", user=self.exec_user))
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc({"doctype": "Agent", "agent_name": f"nope-{frappe.generate_hash(length=5)}"}).insert()
			from huf.huf.doctype.huf_api_key.huf_api_key import create_api_key

			with self.assertRaises(frappe.PermissionError):
				create_api_key(label="x", scopes=["agent.run"])
			for cap in ("agent.create", "developer.keys.manage", "ssh.run", "code_execution.run"):
				self.assertFalse(has_capability(self.exec_user, cap), cap)
			# can read the agent it is allowed to run
			self.assertTrue(frappe.has_permission("Agent", "read", user=self.exec_user))
		finally:
			frappe.set_user("Administrator")

	def test_unauthorized_exec_user_fails_clearly_in_gateway_validate(self):
		plain = _make_user("plain", [])
		frappe.get_doc("User", plain).add_roles(GATEWAY_ROLE)
		# Role present but make the capability resolution fail.
		with patch("huf.permissions.has_capability", return_value=False):
			self.gateway.execution_user = plain
			with self.assertRaises(frappe.ValidationError) as ctx:
				self.gateway.save(ignore_permissions=True)
		self.assertIn("lacks the agent.use capability", str(ctx.exception))
		self.assertIn("Huf Gateway User", str(ctx.exception))


class TestExecutionUserNotAuthorizedHealth(unittest.TestCase):
	def test_reason_reported_from_permission_error_events(self):
		from huf.ai.whatsapp import health

		gateway = "GW-FIXF-HEALTH"
		self.addCleanup(frappe.db.rollback)
		frappe.set_user("Administrator")
		with patch.object(frappe.db, "count", side_effect=lambda dt, f=None, *a, **k: 2 if "like" in str(f) and "authorized" in str(f) else 0), \
			patch.object(frappe, "get_all", return_value=[]), \
			patch.object(frappe.db, "exists", return_value=False):
			events = health.read_events(gateway, frappe.utils.now_datetime())
		self.assertEqual(events["execution_unauthorized"], 2)

		result = health.evaluate(
			{"enabled": True, "execution_unauthorized": 2, "events_24h": {}},
			frappe.utils.now_datetime(),
		)
		codes = [r["code"] for r in result["reasons"]]
		self.assertIn("execution_user_not_authorized", codes)
		quiet = health.evaluate({"enabled": True, "events_24h": {}}, frappe.utils.now_datetime())
		self.assertNotIn("execution_user_not_authorized", [r["code"] for r in quiet["reasons"]])
