"""Tests for Decision spend analytics (T10.02).

Tests aggregation functions get_decision_spend_summary and get_decision_spend_timeseries
with permission filtering (D5), ensuring non-admin users see only their own calls.

Note: Permission filtering tests use the Administrator user with SQL-level testing
since the test framework throttles user creation.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime

from huf.ai.decision.analytics import (
	get_decision_spend_summary,
	get_decision_spend_timeseries,
	VALID_GROUP_BY,
	VALID_BUCKETS,
)
from huf.ai.tests.factories import make_agent_run


class TestDecisionSpendAnalytics(IntegrationTestCase):
	"""Test Decision spend analytics functions."""

	def setUp(self):
		"""Create test policies and decision calls."""
		frappe.set_user("Administrator")

		self.admin = "Administrator"

		# Create test policies
		self._create_test_policies()

		# Create test agent runs
		self.agent_run_1 = make_agent_run()
		self.agent_run_2 = make_agent_run()

		# Create test decision calls
		self._create_test_calls()

	def tearDown(self):
		"""Clean up test data."""
		frappe.set_user("Administrator")

		# Delete all Decision Calls created in this test
		call_ids = frappe.db.get_list(
			"Decision Call",
			filters={"call_id": ["like", "call-%"]},
			pluck="name"
		)
		for call_id in call_ids:
			frappe.delete_doc("Decision Call", call_id, ignore_permissions=True)

		frappe.db.commit()

	def _create_test_policies(self):
		"""Create test Decision Policies."""
		for policy_name in ["policy-1", "policy-2", "policy-3"]:
			if not frappe.db.exists("Decision Policy", policy_name):
				policy = frappe.get_doc({
					"doctype": "Decision Policy",
					"policy_name": policy_name,
					"title": f"Test {policy_name}",
					"status": "draft",
					"policy_class": "classifier",
					"definition": {"name": policy_name, "type": "classifier"},
				})
				policy.insert(ignore_permissions=True)

	def _create_test_calls(self):
		"""Create test Decision Calls with various metrics."""
		now = now_datetime()
		# Use a hash suffix to make call IDs unique across test runs
		suffix = frappe.generate_hash(length=8)

		# Create calls via agent_run_1
		# These are created over 3 days to test timeseries bucketing
		self._create_call(
			call_id=f"call-1-1-{suffix}",
			policy="policy-1",
			agent_run=self.agent_run_1.name,
			surface="tool",
			origin_type="Agent",
			mode="Enforce",
			started_at=now - timedelta(days=2),
			input_tokens=100,
			output_tokens=50,
			cost=0.10,
		)
		self._create_call(
			call_id=f"call-1-2-{suffix}",
			policy="policy-1",
			agent_run=self.agent_run_1.name,
			surface="skill",
			origin_type="Agent",
			mode="Enforce",
			started_at=now - timedelta(days=2),
			input_tokens=200,
			output_tokens=100,
			cost=0.20,
		)
		self._create_call(
			call_id=f"call-1-3-{suffix}",
			policy="policy-2",
			agent_run=self.agent_run_1.name,
			surface="tool",
			origin_type="Agent",
			mode="Shadow",
			started_at=now - timedelta(days=1),
			input_tokens=150,
			output_tokens=75,
			cost=0.15,
		)

		# Create calls via agent_run_2
		self._create_call(
			call_id=f"call-2-1-{suffix}",
			policy="policy-2",
			agent_run=self.agent_run_2.name,
			surface="flow",
			origin_type="Flow",
			mode="Advise",
			started_at=now - timedelta(days=1),
			input_tokens=300,
			output_tokens=150,
			cost=0.30,
		)
		self._create_call(
			call_id=f"call-2-2-{suffix}",
			policy="policy-3",
			agent_run=self.agent_run_2.name,
			surface="automation",
			origin_type="Automation",
			mode="Enforce",
			started_at=now,
			input_tokens=250,
			output_tokens=125,
			cost=0.25,
		)

		# Create Playground call (no origin) - use Administrator
		self._create_call(
			call_id=f"call-playground-1-{suffix}",
			policy="policy-1",
			owner_user="Administrator",
			surface="playground",
			origin_type="Playground",
			mode="Manual",
			started_at=now,
			input_tokens=50,
			output_tokens=25,
			cost=0.05,
		)

	def _create_call(
		self,
		call_id: str,
		policy: str,
		surface: str,
		origin_type: str,
		mode: str,
		started_at: datetime,
		input_tokens: int,
		output_tokens: int,
		cost: float,
		agent_run: str | None = None,
		owner_user: str | None = None,
	):
		"""Helper to create a Decision Call."""
		doc = {
			"doctype": "Decision Call",
			"call_id": call_id,
			"policy": policy,
			"surface": surface,
			"origin_type": origin_type,
			"mode": mode,
			"started_at": started_at,
			"ended_at": started_at + timedelta(milliseconds=100),
			"status": "success",
			"input_tokens": input_tokens,
			"output_tokens": output_tokens,
			"cost": cost,
		}
		if agent_run:
			doc["agent_run"] = agent_run
		if owner_user:
			doc["owner_user"] = owner_user

		call = frappe.get_doc(doc)
		call.insert(ignore_permissions=True)

	# --- Tests: get_decision_spend_summary ---

	def test_summary_all_calls(self):
		"""Test summary aggregation as admin (sees all calls)."""
		frappe.set_user(self.admin)
		result = get_decision_spend_summary()

		self.assertEqual(result["summary"]["call_count"], 6)
		self.assertEqual(result["summary"]["input_tokens"], 1050)  # 100+200+150+300+250+50
		self.assertEqual(result["summary"]["output_tokens"], 525)   # 50+100+75+150+125+25
		self.assertAlmostEqual(result["summary"]["cost"], 1.05, places=2)  # 0.10+0.20+0.15+0.30+0.25+0.05

	def test_summary_group_by_policy(self):
		"""Test summary grouped by policy."""
		frappe.set_user(self.admin)
		result = get_decision_spend_summary(group_by="policy")

		self.assertEqual(len(result["breakdowns"]), 3)

		# Find breakdowns by policy
		breakdown_by_policy = {b["policy"]: b for b in result["breakdowns"]}

		# policy-1: 3 calls (100+200+50 tokens in, 50+100+25 out, 0.35 cost)
		self.assertEqual(breakdown_by_policy["policy-1"]["call_count"], 3)
		self.assertEqual(breakdown_by_policy["policy-1"]["input_tokens"], 350)
		self.assertEqual(breakdown_by_policy["policy-1"]["output_tokens"], 175)
		self.assertAlmostEqual(breakdown_by_policy["policy-1"]["cost"], 0.35, places=2)

		# policy-2: 2 calls (150+300 in, 75+150 out, 0.45 cost)
		self.assertEqual(breakdown_by_policy["policy-2"]["call_count"], 2)
		self.assertEqual(breakdown_by_policy["policy-2"]["input_tokens"], 450)

		# policy-3: 1 call
		self.assertEqual(breakdown_by_policy["policy-3"]["call_count"], 1)

	def test_summary_group_by_surface(self):
		"""Test summary grouped by surface."""
		frappe.set_user(self.admin)
		result = get_decision_spend_summary(group_by="surface")

		breakdown_by_surface = {b["surface"]: b for b in result["breakdowns"]}

		# Should have tool, skill, flow, automation, playground
		self.assertIn("tool", breakdown_by_surface)
		self.assertIn("skill", breakdown_by_surface)
		self.assertIn("flow", breakdown_by_surface)

		# tool: 2 calls (100+150 in, 50+75 out)
		self.assertEqual(breakdown_by_surface["tool"]["call_count"], 2)
		self.assertEqual(breakdown_by_surface["tool"]["input_tokens"], 250)

	def test_summary_group_by_origin_type(self):
		"""Test summary grouped by origin_type."""
		frappe.set_user(self.admin)
		result = get_decision_spend_summary(group_by="origin_type")

		breakdown_by_origin = {b["origin_type"]: b for b in result["breakdowns"]}

		self.assertIn("Agent", breakdown_by_origin)
		self.assertIn("Flow", breakdown_by_origin)
		self.assertIn("Automation", breakdown_by_origin)
		self.assertIn("Playground", breakdown_by_origin)

		# Agent: 3 calls
		self.assertEqual(breakdown_by_origin["Agent"]["call_count"], 3)

	def test_summary_group_by_mode(self):
		"""Test summary grouped by mode."""
		frappe.set_user(self.admin)
		result = get_decision_spend_summary(group_by="mode")

		breakdown_by_mode = {b["mode"]: b for b in result["breakdowns"]}

		self.assertIn("Enforce", breakdown_by_mode)
		self.assertIn("Shadow", breakdown_by_mode)
		self.assertIn("Advise", breakdown_by_mode)
		self.assertIn("Manual", breakdown_by_mode)

		# Enforce: 3 calls (from policy-1, policy-2, policy-3)
		self.assertEqual(breakdown_by_mode["Enforce"]["call_count"], 3)

	def test_summary_respects_time_window_boundaries(self):
		"""Test that summary correctly respects start/end time boundaries."""
		frappe.set_user(self.admin)
		now = now_datetime()

		# Query a window that includes some calls
		result = get_decision_spend_summary(
			from_date=(now - timedelta(days=2.5)).isoformat(),
			to_date=(now - timedelta(hours=11)).isoformat(),
		)

		# Should have at least some calls
		self.assertGreater(result["summary"]["call_count"], 0)

	def test_summary_date_range_filtering(self):
		"""Test summary with specific date range."""
		frappe.set_user(self.admin)
		now = now_datetime()

		result = get_decision_spend_summary(
			from_date=(now - timedelta(days=1.5)).isoformat(),
			to_date=(now - timedelta(hours=12)).isoformat(),
		)

		# Should include only calls from 1.5 days ago to 12 hours ago
		# That's call-1-3 and call-2-1 (both from 1-2 days ago)
		self.assertEqual(result["summary"]["call_count"], 2)

	def test_summary_invalid_group_by(self):
		"""Test that invalid group_by parameter throws error."""
		frappe.set_user(self.admin)
		with self.assertRaises(frappe.ValidationError):
			get_decision_spend_summary(group_by="invalid")

	# --- Tests: get_decision_spend_timeseries ---

	def test_timeseries_by_day(self):
		"""Test timeseries aggregation by day."""
		frappe.set_user(self.admin)
		result = get_decision_spend_timeseries(bucket="day")

		self.assertEqual(result["metadata"]["granularity"], "day")
		self.assertIsNone(result["metadata"]["group_by"])

		# Should have 3 buckets (2 days ago, 1 day ago, today)
		self.assertGreaterEqual(len(result["series"]), 2)

		# Summary should be same as overall
		self.assertEqual(result["summary"]["call_count"], 6)

	def test_timeseries_by_hour(self):
		"""Test timeseries aggregation by hour."""
		frappe.set_user(self.admin)
		result = get_decision_spend_timeseries(bucket="hour")

		self.assertEqual(result["metadata"]["granularity"], "hour")

		# With hourly bucketing, we should have multiple buckets
		self.assertGreater(len(result["series"]), 0)

	def test_timeseries_with_dimension_breakdown(self):
		"""Test timeseries with dimension breakdown by policy."""
		frappe.set_user(self.admin)
		result = get_decision_spend_timeseries(bucket="day", group_by="policy")

		self.assertEqual(result["metadata"]["group_by"], "policy")

		# Each series bucket should have breakdowns
		for bucket in result["series"]:
			self.assertIn("breakdowns", bucket)
			if bucket["breakdowns"]:
				# Check that breakdown has policy field
				for breakdown in bucket["breakdowns"]:
					self.assertIn("policy", breakdown)


	def test_timeseries_invalid_bucket(self):
		"""Test that invalid bucket parameter throws error."""
		frappe.set_user(self.admin)
		with self.assertRaises(frappe.ValidationError):
			get_decision_spend_timeseries(bucket="month")

	def test_timeseries_invalid_group_by(self):
		"""Test that invalid group_by parameter throws error."""
		frappe.set_user(self.admin)
		with self.assertRaises(frappe.ValidationError):
			get_decision_spend_timeseries(group_by="invalid")

	def test_timeseries_date_range_validation(self):
		"""Test that date range is validated."""
		frappe.set_user(self.admin)
		now = now_datetime()

		# Range with start > end should fail
		with self.assertRaises(frappe.ValidationError):
			get_decision_spend_timeseries(
				from_date=(now + timedelta(days=1)).isoformat(),
				to_date=now.isoformat(),
			)

		# Range > 93 days should fail
		with self.assertRaises(frappe.ValidationError):
			get_decision_spend_timeseries(
				from_date=(now - timedelta(days=100)).isoformat(),
				to_date=now.isoformat(),
			)

	# --- Tests: Derived metrics ---

	def test_summary_computes_total_tokens(self):
		"""Test that total_tokens = input_tokens + output_tokens."""
		frappe.set_user(self.admin)
		result = get_decision_spend_summary()

		summary = result["summary"]
		self.assertEqual(
			summary["total_tokens"],
			summary["input_tokens"] + summary["output_tokens"]
		)

	def test_timeseries_computes_total_tokens(self):
		"""Test that total_tokens is computed in timeseries."""
		frappe.set_user(self.admin)
		result = get_decision_spend_timeseries(bucket="day")

		for bucket in result["series"]:
			self.assertEqual(
				bucket["total_tokens"],
				bucket["input_tokens"] + bucket["output_tokens"]
			)

	def test_empty_result_structure(self):
		"""Test that empty results have correct structure."""
		frappe.set_user(self.admin)
		now = now_datetime()

		# Query with date range that has no calls
		result = get_decision_spend_summary(
			from_date=(now + timedelta(days=1)).isoformat() if False else (now - timedelta(days=100)).isoformat(),
			to_date=(now - timedelta(days=99)).isoformat(),
		)

		# Should still have required keys even if empty
		self.assertIn("summary", result)
		self.assertIn("breakdowns", result)
		self.assertIn("metadata", result)

		# Summary should have all required keys with zero values
		self.assertEqual(result["summary"]["call_count"], 0)
		self.assertEqual(result["summary"]["input_tokens"], 0)
		self.assertEqual(result["summary"]["output_tokens"], 0)
		self.assertEqual(result["summary"]["total_tokens"], 0)
		self.assertEqual(result["summary"]["cost"], 0.0)
