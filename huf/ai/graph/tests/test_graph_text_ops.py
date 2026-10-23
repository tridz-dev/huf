"""Text transform ops (lower/upper/trim/replace/contains/starts_with/split_first/regex_extract/concat).

Frappe-free: exercised through ``run_transform`` only.
"""

import unittest

from huf.ai.graph import transforms as T


def run(op, **inp):
	return T.run_transform(op, inp)


TEXT_OPS = {
	"lower", "upper", "trim", "replace", "contains", "starts_with", "split_first", "regex_extract", "concat",
}


class TestTextOps(unittest.TestCase):
	def test_registered(self):
		self.assertTrue(TEXT_OPS <= set(T.REGISTRY))

	def test_lower_upper_trim(self):
		self.assertEqual(run("lower", text="ORDER").value, "order")
		self.assertEqual(run("upper", text="Order").value, "ORDER")
		self.assertEqual(run("trim", text="  1 \n").value, "1")

	def test_null_and_number_coerce(self):
		self.assertEqual(run("lower", text=None).value, "")
		self.assertEqual(run("trim", text=12).value, "12")

	def test_non_scalar_text_fails(self):
		self.assertFalse(run("lower", text=[1]).ok)
		self.assertFalse(run("lower").ok)

	def test_replace(self):
		self.assertEqual(run("replace", text="a-b-c", find="-", **{"with": "+"}).value, "a+b+c")
		self.assertEqual(run("replace", text="a-b-c", find="-", **{"with": ""}, count=1).value, "ab-c")
		self.assertFalse(run("replace", text="x", find="", **{"with": "y"}).ok)

	def test_contains(self):
		self.assertIs(run("contains", text="My ORDER", needle="order").value, False)
		self.assertIs(run("contains", text="My ORDER", needle="order", ignore_case=True).value, True)
		self.assertIs(run("contains", text="abc", needle="").value, True)
		self.assertFalse(run("contains", text="abc").ok)

	def test_starts_with(self):
		self.assertIs(run("starts_with", text="Refund 1", prefix="refund", ignore_case=True).value, True)
		self.assertIs(run("starts_with", text="Refund 1", prefix="refund").value, False)

	def test_split_first(self):
		self.assertEqual(run("split_first", text="a b c", separator=" ").value, "a")
		self.assertEqual(run("split_first", text="abc", separator=",").value, "abc")
		self.assertEqual(run("split_first", text="  a b").value, "a")  # default: whitespace

	def test_regex_extract(self):
		self.assertEqual(run("regex_extract", text="refund #4521 pls", pattern=r"\d+").value, "4521")
		self.assertIsNone(run("regex_extract", text="none here", pattern=r"\d+").value)
		self.assertEqual(run("regex_extract", text="order: 77", pattern=r"order:\s*(\d+)", group=1).value, "77")
		self.assertEqual(run("regex_extract", text="x", pattern=r"y", default="n/a").value, "n/a")

	def test_regex_rejects_unsafe(self):
		for bad in (r"(a+)+$", r"(a|b)*c", r"(a)\1", r"(?=a)a", "x" * 201, "(", ""):
			self.assertFalse(run("regex_extract", text="aaa", pattern=bad).ok, bad)

	def test_regex_group_out_of_range(self):
		self.assertFalse(run("regex_extract", text="1", pattern=r"\d", group=3).ok)

	def test_input_length_bounded(self):
		big = "a" * (T.MAX_TEXT_CHARS + 1)
		self.assertFalse(run("lower", text=big).ok)
		self.assertFalse(run("regex_extract", text=big, pattern="a").ok)

	def test_concat(self):
		self.assertEqual(run("concat", parts=["a", 1, None, "b"]).value, "a1b")
		self.assertEqual(run("concat", parts=["a", "b"], separator="-").value, "a-b")
		self.assertFalse(run("concat", parts=[["x"]]).ok)
		self.assertFalse(run("concat", parts="no").ok)
		self.assertFalse(run("concat", parts=["a" * 6000, "b" * 6000]).ok)


if __name__ == "__main__":
	unittest.main()
