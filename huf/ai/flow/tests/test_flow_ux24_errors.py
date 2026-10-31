"""UX-24: failures that used to read technical now read as sentences (no field lists, no Python words, no raw provider ids)."""

import unittest

from huf.ai.flow import create_doc as cd
from huf.ai.flow import state as flow_state
from huf.ai.flow.support.plain.transform_text import plain_transform_error
from huf.ai.graph import transforms
from huf.ai.graph.error_copy import describe_exception, plain_error
from huf.ai.providers.errors import specific_message

TECHNICAL = ("requires rows", "list, key", "string", "JSON", "Traceback", "NoneType", "doc.create", "_seconds", "Error:")


def _plain(test, text):
	for word in TECHNICAL:
		test.assertNotIn(word, text)


class TestTransformErrors(unittest.TestCase):
	def test_sort_without_a_list_says_what_it_needs(self):
		result = transforms.run_transform("sort", {"rows": "not a list", "key": "age"}, transforms.Limits())
		self.assertFalse(result.ok)
		text = plain_transform_error('"Sort orders"', result.error.code, result.error.message, result.error.op)
		self.assertEqual(
			text,
			'"Sort orders" needs a list and the field to sort by, but one of them is missing or is the wrong kind of data. Open the step and check what it is given.',
		)
		_plain(self, text)

	def test_every_operation_has_plain_words(self):
		for op in ("select", "filter", "sort", "limit", "group_by", "aggregate", "join", "lookup", "batch", "distinct", "coalesce", "replace", "split_first", "regex_extract", "concat", "upper"):
			_plain(self, plain_transform_error("This step", "bad_input", f"{op} requires rows: list", op))

	def test_limits(self):
		self.assertIn("50 at a time", plain_transform_error("This step", "rows_limit_exceeded", "900 rows exceeds max_rows=50", "sort"))
		self.assertIn("too large", plain_transform_error("This step", "output_limit_exceeded", "x", "concat"))


class TestPlainErrors(unittest.TestCase):
	def test_missing_provider_key(self):
		text = plain_error("Password not found for AI Provider uiv-lane2-nokey api_key")
		self.assertEqual(text, "The AI provider uiv-lane2-nokey has no key saved. Open AI Providers to add it.")
		self.assertIn("AI Providers", text)  # the run card turns this into its "Open AI Providers" button

	def test_missing_provider_key_behind_a_class_name(self):
		text = describe_exception(type("AuthenticationError", (Exception,), {})("Password not found for AI Provider OpenAI api_key"))
		self.assertIn("The AI provider OpenAI has no key saved", text)

	def test_python_messages(self):
		self.assertNotIn("NoneType", plain_error("'NoneType' object has no attribute 'get'"))
		self.assertNotIn("index", plain_error("list index out of range").replace("an item", ""))
		self.assertNotIn("serializable", plain_error("Object of type set is not JSON serializable"))

	def test_provider_key_rejected_names_the_provider_plainly(self):
		text = specific_message("auth", "uiv-lane2-nokey")
		self.assertEqual(text, 'The AI provider "uiv-lane2-nokey" did not accept its key. Open AI Providers to check it.')
		self.assertNotIn("key was rejected", text)


class TestSavedDataAndRecordErrors(unittest.TestCase):
	def test_state_errors(self):
		for call in (lambda: flow_state.encode_value({1, 2}), lambda: flow_state.normalize_ttl(0)):
			with self.assertRaises(flow_state.FlowStateError) as cm:
				call()
			_plain(self, str(cm.exception))

	def test_create_record_errors(self):
		with self.assertRaises(cd.CreateDocError) as cm:
			cd.check_doctype("Flow Definition", ["ToDo"])
		self.assertIn("not allowed to create", str(cm.exception))
		_plain(self, str(cm.exception))
		with self.assertRaises(cd.CreateDocError) as cm:
			cd.validate_fields([], {"nope": 1})
		self.assertIn('no field called "nope"', str(cm.exception))


class TestPinnedSampleLists(unittest.TestCase):
	def test_twenty_items_stay_twenty_inside_the_cap(self):
		from huf.ai.flow.support.trigger_sample import MAX_SAMPLE_BYTES, redact_sample

		agents = [{"name": f"Agent {i}", "role": "Helps with task number %d" % i} for i in range(20)]
		safe = redact_sample({"agents": agents, "total": 20})
		self.assertEqual(len(safe["agents"]), 20)
		self.assertEqual(safe["total"], 20)
		import json

		self.assertLessEqual(len(json.dumps(safe).encode()), MAX_SAMPLE_BYTES)

	def test_big_items_still_fit_the_cap_by_keeping_fewer(self):
		import json

		from huf.ai.flow.support.trigger_sample import MAX_SAMPLE_BYTES, redact_sample

		rows = [{f"field_{k}": "x" * 190 for k in range(10)} for _ in range(20)]
		safe = redact_sample({"rows": rows})
		self.assertLessEqual(len(json.dumps(safe).encode()), MAX_SAMPLE_BYTES)
		self.assertIn("rows", safe)
