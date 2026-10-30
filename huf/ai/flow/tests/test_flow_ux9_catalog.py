"""The data catalog behind the "Use data" picker (UX-9): fields, samples, list wording, predecessor rules, document fields."""

import json
import unittest
from types import SimpleNamespace

from huf.ai.flow.support import catalog as cat
from huf.ai.flow.support import doc_fields as df

ORDER = {
	"customer": {"name": "Ada Lovelace", "email": "ada@example.com", "credit": {"limit": 5000}},
	"total": 450,
	"paid": True,
	"placed_on": "2026-10-29T10:42:00Z",
	"note": "",
	"items": [{"sku": "A-1", "qty": 2, "price": 10}, {"sku": "B-2", "qty": 1, "price": 30}, {"sku": "C-3", "qty": 5, "price": 1}],
	"tags": ["red", "blue"],
	"order-total": 12,
	"_trigger": {"event": "x"},
	"password": "hunter2",
}


def by_path(fields):
	return {f["path"]: f for f in fields if f.get("path")}


class TestInferFields(unittest.TestCase):
	def setUp(self):
		from huf.ai.flow.support.trigger_sample import redact_sample

		self.fields = cat.infer_fields(redact_sample(ORDER), "input")
		self.p = by_path(self.fields)

	def test_scalar_fields_have_labels_types_and_samples(self):
		self.assertEqual(self.p["input.total"]["type"], "number")
		self.assertEqual(self.p["input.total"]["sample"], 450)
		self.assertEqual(self.p["input.paid"]["type"], "yes_no")
		self.assertEqual(self.p["input.placed_on"]["type"], "date")
		self.assertEqual(self.p["input.customer.email"]["label"], "Customer > Email")

	def test_nested_objects_are_followed_to_depth_three(self):
		self.assertIn("input.customer.credit.limit", self.p)
		self.assertEqual(self.p["input.customer.credit.limit"]["label"], "Customer > Credit > Limit")

	def test_object_and_list_samples_are_sentences_never_json(self):
		self.assertEqual(self.p["input.customer"]["type"], "object")
		self.assertEqual(self.p["input.customer"]["sample"], "Ada Lovelace")
		self.assertEqual(self.p["input.items"]["type"], "list")
		for f in self.fields:
			s = f.get("sample")
			if isinstance(s, str):
				self.assertNotRegex(s, r'[{}\[\]"]')

	def test_lists_carry_count_and_item_fields_relative_to_one_item(self):
		items = self.p["input.items"]["list"]
		self.assertEqual(items["count"], 3)
		rel = {f["path"]: f for f in items["item_fields"]}
		self.assertEqual(set(rel), {"sku", "qty", "price"})
		self.assertEqual(rel["sku"]["sample"], "A-1")
		self.assertEqual(self.p["input.tags"]["list"]["item_type"], "text")

	def test_secrets_internal_keys_and_empty_text_are_handled(self):
		self.assertEqual(self.p["input.password"]["sample"], "(hidden)")
		self.assertNotIn("input._trigger", self.p)
		self.assertIsNone(self.p["input.note"]["sample"])

	def test_odd_keys_are_advanced_only_with_no_path(self):
		odd = [f for f in self.fields if f.get("advanced_only")]
		self.assertEqual([f["label"] for f in odd], ["Order total"])
		self.assertIsNone(odd[0]["path"])

	def test_every_offered_path_is_in_the_reference_grammar(self):
		for f in self.fields:
			if f.get("path"):
				self.assertTrue(cat.is_valid_path(f["path"]), f["path"])
			for item in (f.get("list") or {}).get("item_fields", []):
				self.assertTrue(cat.is_valid_path(f"x[0].{item['path']}"), item["path"])

	def test_field_budget_and_scalar_outputs(self):
		many = {f"k{i}": i for i in range(200)}
		self.assertEqual(len(cat.infer_fields(many, "n1")), cat.MAX_FIELDS)
		self.assertEqual(cat.infer_fields("Hello", "n1")[0]["path"], "n1")
		self.assertEqual(cat.infer_fields(None, "n1"), [])
		self.assertEqual(cat.infer_fields([1, 2], "n1")[0]["list"]["count"], 2)

	def test_trim_to_budget_keeps_the_answer_small(self):
		steps = [{"id": "a", "fields": [{"path": f"a.k{i}", "label": "x" * 200, "type": "text", "sample": "y" * 80} for i in range(40)]}]
		cat.trim_to_budget(steps, 4000)
		self.assertLessEqual(len(json.dumps(steps).encode()), 4000)
		self.assertGreater(len(steps[0]["fields"]), 0)


def graph(*nodes, entry="t"):
	return {"entry": entry, "nodes": list(nodes)}


def node(id_, type_="tool.call", nxt=None, **config):
	n = {"id": id_, "type": type_, "config": config}
	if nxt:
		n["next"] = nxt
	return n


class TestGraphRules(unittest.TestCase):
	def test_only_steps_on_every_path_are_offered(self):
		g = graph(
			node("t", "trigger.webhook", "a"),
			node("a", nxt="c"),
			node("c", "condition", on_true="yes", on_false="no"),
			node("yes", nxt="join"),
			node("no", nxt="join"),
			node("join", nxt="after"),
			node("after"),
		)
		self.assertEqual(cat.guaranteed_predecessors(g, "after"), {"t", "a", "c", "join"})
		self.assertEqual(cat.guaranteed_predecessors(g, "yes"), {"t", "a", "c"})
		self.assertNotIn("after", cat.guaranteed_predecessors(g, "a"))

	def test_newest_first_is_longest_distance_from_the_trigger(self):
		g = graph(node("t", "trigger.webhook", "a"), node("a", nxt="b"), node("b", nxt="c"), node("c"))
		d = cat.depth_from_entry(g)
		self.assertEqual([k for k, _ in sorted(d.items(), key=lambda kv: -kv[1])], ["c", "b", "a", "t"])

	def test_loop_body_and_its_item_fields(self):
		g = graph(
			node("t", "trigger.webhook", "loop"),
			{"id": "loop", "type": "foreach", "config": {"items": {"$from": "input.items"}, "body": ["send"]}, "next": "done"},
			node("send"),
			node("done"),
		)
		self.assertEqual(cat.enclosing_loop(g, "send")["id"], "loop")
		self.assertIsNone(cat.enclosing_loop(g, "done"))
		fields = cat.infer_fields(ORDER, "input")
		item_fields = cat.loop_item_fields("input.items", [{"fields": fields}])
		self.assertIn("foreach.item.sku", [f["path"] for f in item_fields])
		self.assertEqual(cat.loop_item_fields("input.nothing", [{"fields": fields}]), [])


def field(name, fieldtype, label=None, options=None, hidden=0):
	return SimpleNamespace(fieldname=name, fieldtype=fieldtype, label=label or name.title(), options=options, hidden=hidden)


class TestDocumentFields(unittest.TestCase):
	fields = [
		field("section", "Section Break"),
		field("customer", "Link", "Customer", "Customer"),
		field("grand_total", "Currency", "Grand Total"),
		field("secret", "Password"),
		field("items", "Table", "Items", "Order Item"),
		field("done", "Check", "Done"),
		field("hidden_one", "Data", "Hidden", hidden=1),
	]

	def test_layout_secret_and_hidden_fields_are_left_out(self):
		out = df.doctype_fields(self.fields)
		paths = [f["path"] for f in out]
		self.assertIn("input.grand_total", paths)
		self.assertNotIn("input.secret", paths)
		self.assertNotIn("input.section", paths)
		self.assertNotIn("input.hidden_one", paths)
		self.assertEqual(out[0]["label"], "ID")

	def test_link_fields_are_followed_with_a_path_the_trigger_fills(self):
		customer = [field("credit_limit", "Currency", "Credit limit"), field("tax_id", "Data", "Tax ID"), field("secret", "Password")]
		rec = {"grand_total": 450, df.LINK_KEY: {"customer": {"credit_limit": 5000}}}
		out = df.doctype_fields(self.fields, rec, link_meta=lambda dt: customer)
		linked = by_path(out)["input._links.customer.credit_limit"]
		self.assertEqual(linked["label"], "Customer > Credit limit")
		self.assertEqual(linked["sample"], 5000)
		self.assertNotIn("input._links.customer.secret", by_path(out))
		self.assertTrue(cat.is_valid_path(linked["path"]))

	def test_table_fields_list_their_columns(self):
		rows = [field("item_code", "Data", "Item code"), field("qty", "Float", "Quantity")]
		rec = {"items": [{"item_code": "TEA", "qty": 2}, {"item_code": "JAM", "qty": 1}]}
		out = by_path(df.doctype_fields(self.fields, rec, child_fields=lambda dt: rows))
		items = out["input.items"]
		self.assertEqual(items["list"]["count"], 2)
		self.assertEqual([f["label"] for f in items["list"]["item_fields"]], ["Item code", "Quantity"])
		self.assertEqual(items["list"]["item_fields"][0]["sample"], "TEA")

	def test_link_targets_are_capped(self):
		many = [field(f"l{i}", "Link", options="X") for i in range(20)]
		self.assertEqual(len(df.link_targets(many)), df.MAX_LINKS)


if __name__ == "__main__":
	unittest.main()
