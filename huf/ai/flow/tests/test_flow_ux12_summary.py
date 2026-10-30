"""UX-12: "Show as summary table" reads well wherever the text is written (an email body, an approval message)."""

from frappe.tests import IntegrationTestCase

from huf.ai.flow.support.router_text import render_text_refs, text_ref_warnings
from huf.ai.graph.executor import GraphContext
from huf.ai.graph.templates import render_marked, render_template

ORDER = {
	"customer": {"name": "Ada Lovelace", "email": "ada@example.com"},
	"total": 450,
	"paid": True,
	"items": [{"name": "Tea", "qty": 2}, {"name": "Cake", "qty": 1}, {"name": "Jam", "qty": 5}],
	"doctype": "Order",
}


class TestSummaryTableAtRunTime(IntegrationTestCase):
	def ctx(self):
		return GraphContext({"order": ORDER, "total": 450})

	def test_email_body_template_with_a_table_marker(self):
		"""The shape the chip input stores for a whole-object pick written into an email body."""
		body = {
			"$template": "Hi,\n\n{table_order}\n\nThanks",
			"vars": {"table_order": {"$from": "input.order"}},
		}
		text = self.ctx().resolve(body)
		self.assertIn("Customer: Ada Lovelace", text)
		self.assertIn("Total: 450", text)
		self.assertIn("Paid: Yes", text)
		self.assertNotIn("{", text)  # no JSON, no braces
		self.assertNotIn("doctype", text.lower())
		# one row per line
		self.assertGreaterEqual(len(text.splitlines()), 6)

	def test_list_markers(self):
		out = self.ctx().resolve(
			{
				"$template": "{count_items} items: {joined_items}",
				"vars": {"count_items": {"$from": "input.order.items"}, "joined_items": {"$from": "input.order.items"}},
			}
		)
		self.assertTrue(out.startswith("3 items: "))
		self.assertIn("Tea", out)
		self.assertNotIn("[", out)

	def test_a_plain_object_variable_is_a_short_summary_not_json(self):
		self.assertNotIn("{", render_template("{o}", {"o": ORDER}))

	def test_approval_message_placeholders_with_the_same_wordings(self):
		ctx = self.ctx()
		text = render_text_refs("Approve? {table:input.order} Items: {joined:input.order.items} ({count:input.order.items}) {input.total}", ctx)
		self.assertIn("Customer: Ada Lovelace", text)
		self.assertIn("(3)", text)
		self.assertIn("450", text)
		self.assertNotIn("{", text)

	def test_plain_placeholder_is_still_a_short_summary(self):
		self.assertEqual(render_text_refs("{input.order.customer}", self.ctx()), "Ada Lovelace")

	def test_unknown_step_renders_empty_and_warns(self):
		self.assertEqual(render_text_refs("x{table:gone.thing}y", self.ctx()), "xy")
		warnings = text_ref_warnings(
			{"nodes": [{"id": "a", "type": "human.approval", "config": {"message": "ok", "title": "Pay {table:gone.thing}"}}]}
		)
		self.assertEqual(len(warnings), 1)
		self.assertIn("title", warnings[0])

	def test_marker_helper(self):
		self.assertEqual(render_marked("count", [1, 2]), "2")
		self.assertIsNone(render_marked("count", {"a": 1}))
		self.assertIn("Total: 450", render_marked("table", ORDER))
