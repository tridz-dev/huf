"""Frappe integration tests for huf.ai.decision.api (T2A.12, PLAN.md §4.8).

Covers the acceptance criteria: every function is capability-checked (decision.run /
decision.author / decision.admin); list/get enforce D5 (origin visibility, raw
payload/state_snapshot admin-only); an ad-hoc `run_decision` definition needs
decision.author; publishing a policy version needs decision.admin. Uses the built-in
"fake" backend (huf.ai.decision.backends.fake, zero network) end to end through
huf.ai.decision.api.run_decision, matching the fixture shape of
huf.ai.decision.tests.test_service.TestRunPolicy.

Fixtures (Decision Model/Deployment/Policy, the three capability-tier users) are built
once per class in setUpClass, not per test: FrappeTestCase only rolls the DB back at
*class* teardown (`frappe/tests/utils.py`'s `addClassCleanup(_rollback_db)`), so creating
them in `setUp` re-creates a fresh `User` for every single test method and quickly trips
`frappe.core.doctype.user.user.throttle_user_creation` (default: 60 new Users per 60s).
"""

from __future__ import annotations

import json
import uuid

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.decision import api
from huf.ai.tests.factories import make_user


def _make_user_unthrottled(*args, **kwargs):
	"""``make_user`` with ``User.before_insert``'s ``throttle_user_creation`` bypassed.

	This module alone creates a handful of throwaway Users per test class (three
	capability tiers plus a couple of one-off users for D5/role-mismatch cases); running
	the whole decision test package back to back trips the default 60-Users-per-60s site
	limit (`frappe.core.doctype.user.user.throttle_user_creation`) well before any of that
	is actually abusive. ``frappe.flags.in_import`` is the one condition that function
	already checks to skip itself (bulk-import tooling hits the same limit legitimately),
	so tests borrow that flag rather than mutating site config.
	"""
	previous = frappe.flags.in_import
	frappe.flags.in_import = True
	try:
		return make_user(*args, **kwargs)
	finally:
		frappe.flags.in_import = previous


class DecisionAPITestBase(FrappeTestCase):
	"""Shared fixtures: one Decision Model/Deployment/Policy plus three capability tiers."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")

		cls._prev_kill_switch = frappe.db.get_single_value("Agent Settings", "decision_runtime_enabled")
		frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", 1)

		suffix = uuid.uuid4().hex[:8]

		cls.provider = frappe.get_doc({
			"doctype": "AI Provider",
			"provider_name": f"TestApiProvider{suffix}",
			"provider_brand": "other",
			"api_base_url": "https://example.test",
			"api_key": "test-secret-key",
		}).insert(ignore_permissions=True)

		cls.ai_model = frappe.get_doc({
			"doctype": "AI Model",
			"model_name": f"test-api-model-{suffix}",
			"provider": cls.provider.name,
			"modalities": "Decision",
		}).insert(ignore_permissions=True)

		cls.model_class = frappe.get_doc({
			"doctype": "Decision Model Class",
			"class_key": f"test_api_class_{suffix}",
			"class_name": "Test Api Class",
			"enabled": 1,
		}).insert(ignore_permissions=True)

		cls.family = frappe.get_doc({
			"doctype": "Decision Model Family",
			"family_key": f"test_api_family_{suffix}",
			"family_name": "Test Api Family",
			"adapter_id": "fake",
			"model_class": cls.model_class.name,
			"enabled": 1,
		}).insert(ignore_permissions=True)

		cls.decision_model = frappe.get_doc({
			"doctype": "Decision Model",
			"model_key": f"test-api-model-key-{suffix}",
			"model_name": "Test Api Model",
			"family": cls.family.name,
			"canonical_version": "1.0",
			"enabled": 1,
		}).insert(ignore_permissions=True)

		cls.deployment = frappe.get_doc({
			"doctype": "Decision Deployment",
			"deployment_key": f"dep-api-{suffix}",
			"deployment_name": "Test Api Deployment",
			"decision_model": cls.decision_model.name,
			"ai_model": cls.ai_model.name,
			"provider": cls.provider.name,
			"provider_model_id": cls.ai_model.name,
			"wire_protocol": "systemone",
			"priority": 100,
			"enabled": 1,
			"is_default_for_model": 1,
		}).insert(ignore_permissions=True)

		cls.policy = frappe.get_doc({
			"doctype": "Decision Policy",
			"policy_name": f"Test Api Policy {suffix}",
			"purpose": "Tool Selection",
			"default_model": cls.decision_model.name,
			"enabled": 1,
			"definition_json": frappe.as_json(cls._definition()),
		}).insert(ignore_permissions=True)
		cls.published_version = cls.policy.publish_version()

		# Three capability tiers (PLAN.md §3.17): Huf User = decision.run only, Huf Manager
		# = all three, plus a bare user with no Huf role at all (no capabilities). Created
		# once for the whole class -- see the module docstring for why.
		cls.run_only_user = _make_user_unthrottled(roles=("Huf User",)).email
		cls.admin_user = _make_user_unthrottled(roles=("Huf Manager",)).email
		cls.no_role_user = _make_user_unthrottled(roles=()).email

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for name in frappe.get_all("Decision Call", filters={"decision_model": cls.decision_model.name}, pluck="name"):
			frappe.delete_doc("Decision Call", name, ignore_permissions=True, ignore_missing=True, force=True)
		frappe.db.set_value("Decision Policy", cls.policy.name, "current_version", None, update_modified=False)
		for version in frappe.get_all("Decision Policy Version", filters={"policy": cls.policy.name}, pluck="name"):
			frappe.delete_doc("Decision Policy Version", version, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Policy", cls.policy.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Deployment", cls.deployment.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model", cls.decision_model.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model Family", cls.family.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model Class", cls.model_class.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("AI Model", cls.ai_model.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("AI Provider", cls.provider.name, ignore_permissions=True, ignore_missing=True)
		frappe.db.set_single_value("Agent Settings", "decision_runtime_enabled", cls._prev_kill_switch)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		self._decision_call_names: list[str] = []
		self._cleanup_users: list[str] = []
		self._cleanup_huf_roles: list[str] = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._decision_call_names:
			frappe.delete_doc("Decision Call", name, ignore_permissions=True, ignore_missing=True, force=True)
		for role_name in self._cleanup_huf_roles:
			frappe.delete_doc("Huf Role", role_name, ignore_permissions=True, ignore_missing=True, force=True)
		for user in self._cleanup_users:
			frappe.delete_doc("User", user, ignore_permissions=True, ignore_missing=True, force=True)
		frappe.set_user("Administrator")

	def _make_run_only_user(self) -> str:
		"""A throwaway Huf User (decision.run only), tracked for per-test cleanup."""
		user = _make_user_unthrottled(roles=("Huf User",)).email
		self._cleanup_users.append(user)
		return user

	def _make_author_only_user(self) -> str:
		"""A user with decision.author but explicitly not decision.admin.

		Mirrors `huf.ai.tests.test_permissions_api._make_huf_role` /
		`_make_huf_user_role` -- the built-in Huf Roles don't give a caller who holds
		decision.author without decision.admin (Huf Manager has both), so a test that
		needs exactly that combination builds a bespoke Huf Role instead.
		"""
		role = frappe.get_doc({
			"doctype": "Huf Role",
			"role_name": f"Test Decision Author Only {frappe.generate_hash(length=8)}",
			"frappe_role": "Huf User",
			"permissions": [{"capability": "decision.run"}, {"capability": "decision.author"}],
		})
		role.insert(ignore_permissions=True)
		self._cleanup_huf_roles.append(role.name)

		user = _make_user_unthrottled(roles=("Huf User",)).email
		self._cleanup_users.append(user)

		# make_user() -> User.on_update triggers HufUserRole.sync_from_frappe_user, which
		# auto-provisions a Huf User Role for the "Huf User" Frappe Role before this point
		# -- upsert rather than blind-insert (same idempotency as
		# huf.ai.tests.test_permissions_api._make_huf_user_role).
		existing_name = frappe.db.get_value("Huf User Role", {"user": user}, "name")
		if existing_name:
			doc = frappe.get_doc("Huf User Role", existing_name)
			doc.huf_role = role.name
			doc.enabled = 1
			doc.invited_by = "Administrator"
			doc.save(ignore_permissions=True)
		else:
			frappe.get_doc({
				"doctype": "Huf User Role",
				"user": user,
				"huf_role": role.name,
				"enabled": 1,
				"invited_by": "Administrator",
			}).insert(ignore_permissions=True)
		return user

	@staticmethod
	def _definition(policy_id: str = "test-api-policy") -> dict:
		return {
			"policy_id": policy_id,
			"fallback_action": "fallback_default",
			"state_bindings": [{"name": "state", "path": "$"}],
			"questions": [
				{
					"id": "q1",
					"kind": "judge",
					"instructions": "Is this state acceptable?",
					"positive_criteria": "state looks fine",
				}
			],
		}

	def _run_a_call(self, *, user: str, origin_type: str = "Playground") -> dict:
		"""Run one Manual decision as `user`, tracked for teardown, returning the dict result."""
		frappe.set_user(user)
		result = api.run_decision(
			policy=self.policy.name,
			state=json.dumps({"x": 1}),
			origin_type=origin_type,
		)
		frappe.set_user("Administrator")
		if result.get("decision_call"):
			self._decision_call_names.append(result["decision_call"])
		return result


class TestRunDecision(DecisionAPITestBase):
	def test_requires_decision_run(self):
		frappe.set_user(self.no_role_user)
		with self.assertRaises(frappe.PermissionError):
			api.run_decision(policy=self.policy.name, state={"x": 1})

	def test_published_policy_succeeds_for_run_only_user(self):
		result = self._run_a_call(user=self.run_only_user)

		self.assertEqual(result["status"], "success")
		self.assertIsNotNone(result["decision_call"])
		self.assertIn("response", result)
		self.assertIn("q1", result["response"]["answers"])

		call = frappe.get_doc("Decision Call", result["decision_call"])
		self.assertEqual(call.mode, "Manual")
		self.assertEqual(call.origin_type, "Playground")
		self.assertEqual(call.owner_user, self.run_only_user)

	def test_ad_hoc_definition_requires_decision_author(self):
		frappe.set_user(self.run_only_user)  # decision.run only, no decision.author
		with self.assertRaises(frappe.PermissionError):
			api.run_decision(
				definition=self._definition("ad-hoc-run-only"),
				decision_model=self.decision_model.name,
				state={"x": 1},
			)

	def test_ad_hoc_definition_succeeds_for_admin(self):
		frappe.set_user(self.admin_user)  # Huf Manager: decision.run + decision.author
		result = api.run_decision(
			definition=self._definition("ad-hoc-admin"),
			decision_model=self.decision_model.name,
			state={"x": 1},
		)
		self.assertEqual(result["status"], "success")
		if result.get("decision_call"):
			self._decision_call_names.append(result["decision_call"])

	def test_pinned_deployment_requires_decision_admin(self):
		frappe.set_user(self.run_only_user)
		with self.assertRaises(frappe.PermissionError):
			api.run_decision(
				policy=self.policy.name,
				state={"x": 1},
				pinned_deployment=self.deployment.name,
			)

	def test_pinned_deployment_succeeds_for_admin(self):
		frappe.set_user(self.admin_user)
		result = api.run_decision(
			policy=self.policy.name,
			state={"x": 1},
			pinned_deployment=self.deployment.name,
		)
		self.assertEqual(result["status"], "success")
		if result.get("decision_call"):
			self._decision_call_names.append(result["decision_call"])

	def test_bad_origin_type_rejected(self):
		frappe.set_user(self.run_only_user)
		with self.assertRaises(frappe.ValidationError):
			api.run_decision(policy=self.policy.name, state={"x": 1}, origin_type="Bogus")

	def test_candidates_and_state_accept_json_strings(self):
		# The fixture policy's only question is a judge, not a select, so candidates are
		# not otherwise required here -- this only exercises _json_arg decoding both
		# `state` and `candidates` from JSON strings. A non-empty `candidates` list still
		# needs a non-POLICY_OPTIONS `candidate_source` plus `candidate_resolver_id`
		# (huf.ai.decision.runtime.DecisionRuntime._validate_request_candidates), matching
		# what a real caller declaring provenance for runtime candidates would send.
		frappe.set_user(self.run_only_user)
		result = api.run_decision(
			policy=self.policy.name,
			state=json.dumps({"x": 1}),
			candidates=json.dumps([{"id": "opt1", "description": "Option 1"}]),
			candidate_source="routeable_models",
			candidate_resolver_id="test-resolver",
		)
		self.assertEqual(result["status"], "success")
		if result.get("decision_call"):
			self._decision_call_names.append(result["decision_call"])


class TestListDecisionModels(DecisionAPITestBase):
	def test_requires_decision_run(self):
		frappe.set_user(self.no_role_user)
		with self.assertRaises(frappe.PermissionError):
			api.list_decision_models()

	def test_run_only_user_sees_enabled_models_without_deployments(self):
		frappe.set_user(self.run_only_user)
		models = api.list_decision_models()

		names = {m["name"] for m in models}
		self.assertIn(self.decision_model.name, names)
		for model in models:
			self.assertTrue(model["enabled"])
			self.assertNotIn("deployments", model)

	def test_admin_sees_deployments(self):
		frappe.set_user(self.admin_user)
		models = api.list_decision_models()

		by_name = {m["name"]: m for m in models}
		self.assertIn(self.decision_model.name, by_name)
		deployments = by_name[self.decision_model.name]["deployments"]
		self.assertTrue(any(d["name"] == self.deployment.name for d in deployments))

	def test_admin_sees_disabled_models_too(self):
		frappe.db.set_value("Decision Model", self.decision_model.name, "enabled", 0)
		try:
			frappe.set_user(self.admin_user)
			models = api.list_decision_models()
			self.assertIn(self.decision_model.name, {m["name"] for m in models})

			frappe.set_user(self.run_only_user)
			models = api.list_decision_models()
			self.assertNotIn(self.decision_model.name, {m["name"] for m in models})
		finally:
			frappe.set_user("Administrator")
			frappe.db.set_value("Decision Model", self.decision_model.name, "enabled", 1)


class TestDecisionCallReadAPIs(DecisionAPITestBase):
	def setUp(self):
		super().setUp()
		self.owned_call = self._run_a_call(user=self.run_only_user)["decision_call"]

	def test_get_decision_call_requires_decision_run(self):
		frappe.set_user(self.no_role_user)
		with self.assertRaises(frappe.PermissionError):
			api.get_decision_call(self.owned_call)

	def test_owner_can_read_own_call(self):
		frappe.set_user(self.run_only_user)
		data = api.get_decision_call(self.owned_call)
		self.assertEqual(data["name"], self.owned_call)
		self.assertEqual(data["status"], "success")

	def test_owner_without_admin_does_not_see_raw_fields(self):
		frappe.set_user(self.run_only_user)
		data = api.get_decision_call(self.owned_call)
		for field in ("answer_json", "state_snapshot", "question_snapshot", "state_hash"):
			self.assertNotIn(field, data)

	def test_admin_sees_raw_fields(self):
		frappe.set_user(self.admin_user)
		data = api.get_decision_call(self.owned_call)
		for field in ("answer_json", "state_snapshot", "question_snapshot", "state_hash"):
			self.assertIn(field, data)

	def test_other_run_only_user_cannot_read_someone_elses_call(self):
		frappe.set_user(self._make_run_only_user())
		with self.assertRaises(frappe.PermissionError):
			api.get_decision_call(self.owned_call)

	def test_admin_can_read_any_call(self):
		frappe.set_user(self.admin_user)
		data = api.get_decision_call(self.owned_call)
		self.assertEqual(data["name"], self.owned_call)

	def test_list_decision_calls_requires_decision_run(self):
		frappe.set_user(self.no_role_user)
		with self.assertRaises(frappe.PermissionError):
			api.list_decision_calls()

	def test_owner_sees_own_call_in_list(self):
		frappe.set_user(self.run_only_user)
		page = api.list_decision_calls(filters={"decision_model": self.decision_model.name})
		self.assertIn(self.owned_call, {row["name"] for row in page["rows"]})

	def test_other_run_only_user_does_not_see_the_call_in_list(self):
		frappe.set_user(self._make_run_only_user())
		page = api.list_decision_calls(filters={"decision_model": self.decision_model.name})
		self.assertNotIn(self.owned_call, {row["name"] for row in page["rows"]})

	def test_admin_sees_the_call_in_list(self):
		frappe.set_user(self.admin_user)
		page = api.list_decision_calls(filters={"decision_model": self.decision_model.name})
		self.assertIn(self.owned_call, {row["name"] for row in page["rows"]})

	def test_list_rejects_unknown_filter_field(self):
		frappe.set_user(self.admin_user)
		with self.assertRaises(frappe.ValidationError):
			api.list_decision_calls(filters={"not_a_real_field": "x"})


class TestValidatePolicyDefinition(DecisionAPITestBase):
	def test_requires_decision_author(self):
		frappe.set_user(self.run_only_user)
		with self.assertRaises(frappe.PermissionError):
			api.validate_policy_definition(self._definition())

	def test_valid_definition(self):
		frappe.set_user(self.admin_user)
		result = api.validate_policy_definition(self._definition("valid-def"))
		self.assertTrue(result["valid"])
		self.assertEqual(result["policy_id"], "valid-def")
		self.assertEqual(result["question_ids"], ["q1"])
		self.assertTrue(result["fingerprint"])

	def test_invalid_definition_returns_valid_false(self):
		frappe.set_user(self.admin_user)
		bad = self._definition("bad-def")
		bad["questions"][0]["kind"] = "not_a_real_kind"
		result = api.validate_policy_definition(bad)
		self.assertFalse(result["valid"])
		self.assertIn("error_code", result)

	def test_accepts_json_string(self):
		frappe.set_user(self.admin_user)
		result = api.validate_policy_definition(json.dumps(self._definition("json-str-def")))
		self.assertTrue(result["valid"])


class TestPublishPolicyVersion(DecisionAPITestBase):
	def setUp(self):
		super().setUp()
		# A fresh Draft-worthy policy: mutate definition_json so publishing creates a
		# genuinely new version distinct from the class-setUp one, then restore it so
		# other test methods in this class see the original definition/version again.
		self._prev_definition_json = self.policy.definition_json
		frappe.db.set_value(
			"Decision Policy", self.policy.name, "definition_json",
			frappe.as_json(self._definition("republished")), update_modified=False,
		)
		self._new_versions: list[str] = []

	def tearDown(self):
		frappe.db.set_value("Decision Policy", self.policy.name, "definition_json", self._prev_definition_json, update_modified=False)
		frappe.db.set_value("Decision Policy", self.policy.name, "current_version", self.published_version, update_modified=False)
		for version in self._new_versions:
			frappe.delete_doc("Decision Policy Version", version, ignore_permissions=True, ignore_missing=True)
		super().tearDown()

	def test_requires_decision_admin(self):
		frappe.set_user(self.run_only_user)
		with self.assertRaises(frappe.PermissionError):
			api.publish_policy_version(self.policy.name)

	def test_author_without_admin_is_rejected(self):
		# decision.author alone (no decision.admin) must not be able to publish (§5.2:
		# publish/retire is decision.admin, stricter than decision.author's create/edit).
		frappe.set_user(self._make_author_only_user())
		with self.assertRaises(frappe.PermissionError):
			api.publish_policy_version(self.policy.name)

	def test_admin_can_publish(self):
		frappe.set_user(self.admin_user)
		result = api.publish_policy_version(self.policy.name)
		self._new_versions.append(result["version"])

		self.assertEqual(result["policy"], self.policy.name)
		self.assertTrue(result["version"])
		self.assertNotEqual(result["version"], self.published_version)

		frappe.set_user("Administrator")
		policy_doc = frappe.get_doc("Decision Policy", self.policy.name)
		self.assertEqual(policy_doc.current_version, result["version"])
