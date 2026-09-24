"""Frappe integration tests for huf.ai.decision.deployment_loader.load_chain.

Covers PLAN.md §4.6 / task T2A.09 acceptance: default-first-then-priority ordering,
disabled/unhealthy/cool-down exclusion, adapter_override vs family adapter_id, pinned
selection, and 30s row-list caching invalidated by the Decision Deployment / AI Model /
AI Provider doc_events wired in huf/hooks.py.
"""

from __future__ import annotations

import uuid

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.decision.deployment_loader import invalidate_deployment_chain_cache, load_chain


class TestDeploymentLoader(FrappeTestCase):
	def setUp(self):
		# Bump the cache epoch first so no row list cached by an earlier test (possibly for
		# the same model docname, since names are deterministic per test method) leaks in.
		invalidate_deployment_chain_cache()

		self.suffix = uuid.uuid4().hex[:8]
		self.provider_name = f"TestDRProvider{self.suffix}"
		self.ai_model_name = f"test-dr-model-{self.suffix}"
		self.class_key = f"test_dr_class_{self.suffix}"
		self.family_key = f"test_dr_family_{self.suffix}"
		self.model_key = f"test-dr-model-key-{self.suffix}"

		self.deployment_names: list[str] = []

		self.provider = frappe.get_doc({
			"doctype": "AI Provider",
			"provider_name": self.provider_name,
			"provider_brand": "other",
			"api_base_url": "https://example.test",
			"api_key": "test-secret-key",
		}).insert(ignore_permissions=True)

		self.ai_model = frappe.get_doc({
			"doctype": "AI Model",
			"model_name": self.ai_model_name,
			"provider": self.provider.name,
			"modalities": "Decision",
		}).insert(ignore_permissions=True)

		self.model_class = frappe.get_doc({
			"doctype": "Decision Model Class",
			"class_key": self.class_key,
			"class_name": "Test DR Class",
			"enabled": 1,
		}).insert(ignore_permissions=True)

		self.family = frappe.get_doc({
			"doctype": "Decision Model Family",
			"family_key": self.family_key,
			"family_name": "Test DR Family",
			"adapter_id": "fake",
			"model_class": self.model_class.name,
			"enabled": 1,
		}).insert(ignore_permissions=True)

		self.decision_model = frappe.get_doc({
			"doctype": "Decision Model",
			"model_key": self.model_key,
			"model_name": "Test DR Model",
			"family": self.family.name,
			"canonical_version": "1.0",
			"enabled": 1,
		}).insert(ignore_permissions=True)

	def tearDown(self):
		for name in self.deployment_names:
			frappe.delete_doc("Decision Deployment", name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model", self.decision_model.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model Family", self.family.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("Decision Model Class", self.model_class.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("AI Model", self.ai_model.name, ignore_permissions=True, ignore_missing=True)
		frappe.delete_doc("AI Provider", self.provider.name, ignore_permissions=True, ignore_missing=True)
		invalidate_deployment_chain_cache()

	def _make_deployment(self, key_suffix: str, **overrides) -> str:
		values = {
			"doctype": "Decision Deployment",
			"deployment_key": f"dep-{self.suffix}-{key_suffix}",
			"deployment_name": f"Test Deployment {key_suffix}",
			"decision_model": self.decision_model.name,
			"ai_model": self.ai_model.name,
			# provider / provider_model_id are fetch_from(ai_model.*) read-only fields that
			# only populate through form JS; set explicitly for a correct server-side insert,
			# same as huf/patches/v1/seed_decision_system_one.py does.
			"provider": self.provider.name,
			"provider_model_id": self.ai_model_name,
			"wire_protocol": "systemone",
			"priority": 100,
			"enabled": 1,
			"is_default_for_model": 0,
		}
		values.update(overrides)
		doc = frappe.get_doc(values).insert(ignore_permissions=True)
		self.deployment_names.append(doc.name)
		return doc.name

	# -- Ordering -----------------------------------------------------------------------

	def test_orders_default_first_then_priority(self):
		self._make_deployment("low-priority", priority=5)
		default_name = self._make_deployment("default", priority=50, is_default_for_model=1)
		self._make_deployment("mid-priority", priority=10)

		chain = load_chain(decision_model=self.decision_model.name)

		self.assertEqual(len(chain.candidates), 3)
		ordered_deployments = [c.identity.deployment for c in chain.candidates]
		self.assertEqual(ordered_deployments[0], f"dep-{self.suffix}-default")
		# Non-default rows follow, ordered by priority ascending.
		self.assertEqual(ordered_deployments[1], f"dep-{self.suffix}-low-priority")
		self.assertEqual(ordered_deployments[2], f"dep-{self.suffix}-mid-priority")
		self.assertEqual(chain.candidates[0].identity.deployment, f"dep-{self.suffix}-default")
		self.assertTrue(default_name)

	# -- Eligibility ----------------------------------------------------------------------

	def test_skips_disabled_deployment(self):
		self._make_deployment("enabled-one", priority=10)
		self._make_deployment("disabled-one", priority=1, enabled=0)

		chain = load_chain(decision_model=self.decision_model.name)

		self.assertEqual(chain.fallback_chain, (f"dep-{self.suffix}-enabled-one",))

	def test_skips_unhealthy_deployment(self):
		self._make_deployment("healthy-one", priority=10)
		self._make_deployment("unhealthy-one", priority=1, health_status="unhealthy")

		chain = load_chain(decision_model=self.decision_model.name)

		self.assertEqual(chain.fallback_chain, (f"dep-{self.suffix}-healthy-one",))

	def test_skips_deployment_in_cooldown(self):
		self._make_deployment("healthy-one", priority=10)
		self._make_deployment(
			"cooling-down",
			priority=1,
			health_status="degraded",
			last_healthcheck=frappe.utils.now_datetime().isoformat(),
		)
		self._make_deployment(
			"past-cooldown",
			priority=2,
			health_status="degraded",
			last_healthcheck=frappe.utils.add_to_date(frappe.utils.now_datetime(), seconds=-120).isoformat(),
		)

		chain = load_chain(decision_model=self.decision_model.name)

		self.assertNotIn(f"dep-{self.suffix}-cooling-down", chain.fallback_chain)
		self.assertIn(f"dep-{self.suffix}-healthy-one", chain.fallback_chain)
		self.assertIn(f"dep-{self.suffix}-past-cooldown", chain.fallback_chain)

	# -- Adapter resolution -----------------------------------------------------------------

	def test_adapter_override_used_when_present(self):
		from huf.ai.decision.backends.fake import FakeDecisionBackend

		name = self._make_deployment("override", priority=1, adapter_override="fake")
		chain = load_chain(decision_model=self.decision_model.name)

		self.assertEqual(len(chain.candidates), 1)
		self.assertIsInstance(chain.candidates[0].backend, FakeDecisionBackend)
		self.assertTrue(name)

	def test_family_adapter_id_used_when_no_override(self):
		self._make_deployment("no-override", priority=1)
		chain = load_chain(decision_model=self.decision_model.name)

		self.assertEqual(len(chain.candidates), 1)
		self.assertEqual(chain.candidates[0].backend.adapter_id(), "fake")

	# -- Pinning ------------------------------------------------------------------------

	def test_pinned_deployment_returns_single_candidate_with_selection_source_pinned(self):
		self._make_deployment("pin-target", priority=50)
		self._make_deployment("other", priority=1, is_default_for_model=1)

		chain = load_chain(
			decision_model=self.decision_model.name,
			pinned_deployment=f"dep-{self.suffix}-pin-target",
		)

		self.assertEqual(chain.selection_source, "pinned")
		self.assertEqual(len(chain.candidates), 1)
		self.assertEqual(chain.candidates[0].identity.deployment, f"dep-{self.suffix}-pin-target")

	def test_pinned_disabled_deployment_with_bypass_health_filter_returns_candidate(self):
		"""Verify that a disabled deployment can be probed via pinned + bypass_health_filter.

		This is the core bug fix: test_deployment() needs to probe a not-yet-enabled deployment
		by calling load_chain with pinned_deployment + bypass_health_filter=True. Before the fix,
		the disabled deployment was not in the cached (enabled-only) row set, so the pinned
		filter found nothing and returned an empty chain (DEPLOYMENT_UNAVAILABLE). After the fix,
		a fresh uncached query fetches the disabled row and allows the probe to proceed.
		"""
		# Create a disabled deployment and an enabled one for comparison
		disabled_deployment = self._make_deployment("disabled-probe", priority=1, enabled=0)
		self._make_deployment("enabled-one", priority=10)

		# Pinned + bypass_health_filter should find the disabled deployment and build a candidate
		chain = load_chain(
			decision_model=self.decision_model.name,
			pinned_deployment=f"dep-{self.suffix}-disabled-probe",
			bypass_health_filter=True,
		)

		# Assert that we got a candidate for the disabled deployment
		self.assertEqual(chain.selection_source, "pinned")
		self.assertEqual(len(chain.candidates), 1, "expected a candidate for the disabled deployment")
		self.assertEqual(chain.candidates[0].identity.deployment, f"dep-{self.suffix}-disabled-probe")

	def test_normal_load_chain_still_excludes_disabled_deployments(self):
		"""Verify that normal (non-pinned, non-bypass) calls still exclude disabled rows.

		The cached row list should exclude disabled deployments to prevent accidental serving
		of not-yet-enabled deployments. Only explicit probes (pinned + bypass_health_filter=True)
		should be able to bypass this restriction.
		"""
		self._make_deployment("disabled-one", priority=1, enabled=0)
		self._make_deployment("enabled-one", priority=10)

		# Normal call without pinning should exclude disabled deployments
		chain = load_chain(decision_model=self.decision_model.name)

		# Should only have the enabled deployment
		self.assertEqual(len(chain.candidates), 1)
		self.assertEqual(chain.candidates[0].identity.deployment, f"dep-{self.suffix}-enabled-one")

	# -- Caching / invalidation -----------------------------------------------------------

	def test_row_list_is_cached_and_invalidated_on_deployment_update(self):
		name = self._make_deployment("cache-target", priority=50)

		first = load_chain(decision_model=self.decision_model.name)
		self.assertEqual(first.candidates[0].identity.deployment, f"dep-{self.suffix}-cache-target")

		# Disable directly via db.set_value (no controller hook), then confirm the row is
		# still returned from the 30s cache before any invalidation.
		frappe.db.set_value("Decision Deployment", name, "enabled", 0, update_modified=False)
		frappe.db.commit()
		still_cached = load_chain(decision_model=self.decision_model.name)
		self.assertEqual(len(still_cached.candidates), 1, "expected the stale cached row list before invalidation")

		# Now go through save(), which fires the on_update doc_event and must invalidate.
		doc = frappe.get_doc("Decision Deployment", name)
		doc.enabled = 0
		doc.save(ignore_permissions=True)

		after_invalidation = load_chain(decision_model=self.decision_model.name)
		self.assertEqual(after_invalidation.candidates, (), "cache must be invalidated by Decision Deployment on_update")

	def test_cache_invalidated_by_ai_provider_update(self):
		self._make_deployment("provider-cache", priority=1)
		load_chain(decision_model=self.decision_model.name)

		before_epoch = _current_epoch()
		provider_doc = frappe.get_doc("AI Provider", self.provider.name)
		provider_doc.api_base_url = "https://example.test/updated"
		provider_doc.save(ignore_permissions=True)
		after_epoch = _current_epoch()

		self.assertGreater(after_epoch, before_epoch, "AI Provider on_update must bump the cache epoch")

	def test_cache_invalidated_by_ai_model_update(self):
		self._make_deployment("model-cache", priority=1)
		load_chain(decision_model=self.decision_model.name)

		before_epoch = _current_epoch()
		ai_model_doc = frappe.get_doc("AI Model", self.ai_model.name)
		ai_model_doc.save(ignore_permissions=True)
		after_epoch = _current_epoch()

		self.assertGreater(after_epoch, before_epoch, "AI Model on_update must bump the cache epoch")


def _current_epoch() -> int:
	value = frappe.cache().get_value("huf_decision_deployment_chain_epoch")
	return int(value) if value else 0
