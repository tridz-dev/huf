"""The (status, resume_at) index behind the wait sweeper (``park.wake_due_waits``)."""

from datetime import datetime, timedelta
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.flow.runs import park
from huf.patches.v1 import add_agent_flow_run_status_resume_index as index_patch

INDEX = "idx_agent_flow_run_status_resume_at"
NOW = datetime(2030, 1, 1)


def index_columns() -> list[str]:
	rows = frappe.db.sql("SHOW INDEX FROM `tabAgent Flow Run` WHERE Key_name = %s", INDEX, as_dict=True)
	return [row.Column_name for row in sorted(rows, key=lambda row: row.Seq_in_index)]


def sweeper_sql() -> str:
	"""The SQL the sweeper really runs, so the EXPLAIN cannot drift from the code."""
	captured = []
	real_get_all = frappe.get_all

	def capture(doctype, *args, **kwargs):
		if doctype != "Agent Flow Run":  # meta loading goes through get_all too
			return real_get_all(doctype, *args, **kwargs)
		captured.append(real_get_all(doctype, *args, **kwargs, run=False))
		return []

	with patch.object(park.frappe, "get_all", side_effect=capture):
		park.wake_due_waits(now=NOW)
	return str(captured[0])


class TestFlowSweeperIndex(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_index_covers_status_then_resume_at(self):
		self.assertEqual(index_columns(), ["status", "resume_at"])

	def test_patch_creates_a_missing_index_and_can_run_again(self):
		frappe.db.commit()
		self.addCleanup(index_patch.execute)
		frappe.db.sql_ddl(f"ALTER TABLE `tabAgent Flow Run` DROP INDEX `{INDEX}`")
		self.assertEqual(index_columns(), [])
		index_patch.execute()
		index_patch.execute()
		self.assertEqual(index_columns(), ["status", "resume_at"])

	def test_sweeper_query_uses_the_composite_index(self):
		# mostly finished runs with a past resume_at: only status + resume_at together is selective
		past = NOW - timedelta(days=1)
		rows = [(f"_test-sweep-{i}", "Waiting Timer" if i % 50 == 0 else "Success", past) for i in range(500)]
		frappe.db.bulk_insert("Agent Flow Run", ["name", "status", "resume_at"], rows)
		plan = frappe.db.sql(f"EXPLAIN {sweeper_sql()}", as_dict=True)
		self.assertEqual([row.key for row in plan], [INDEX], plan)
