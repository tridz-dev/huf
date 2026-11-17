"""Seed re-apply never loosens security fields. Pure unit tests (no DB)."""
import json
import unittest
from unittest.mock import patch

from huf.ai.app_seeding import loaders


class FakeDoc:
	doctype = "Agent Tool Function"
	name = "t1"

	class meta:
		@staticmethod
		def has_field(_k):
			return True

	def __init__(self, **vals):
		self.v = dict(vals)

	def get(self, k, default=None):
		return self.v.get(k, default)

	def set(self, k, val):
		self.v[k] = val

	def __setattr__(self, k, val):
		if k == "v":
			object.__setattr__(self, k, val)
		else:
			self.v[k] = val

	def append(self, k, row):
		self.v.setdefault(k, []).append(row)


def _apply(doc, data):
	with patch.object(loaders.frappe, "logger"):
		return loaders._apply_seed_preserving_edits(doc, data)


class TestSeedTighten(unittest.TestCase):
	def test_reseed_loosening_ignored(self):
		old = {"requires_confirmation": 1, "is_outbound": 1, "allowed_for_guest": 0, "required_roles": "A, B"}
		doc = FakeDoc(**old, seed_snapshot=json.dumps(old))
		seed = {"requires_confirmation": 0, "is_outbound": 0, "allowed_for_guest": 1, "required_roles": ""}
		w = _apply(doc, seed)
		self.assertEqual(doc.get("requires_confirmation"), 1)
		self.assertEqual(doc.get("is_outbound"), 1)
		self.assertEqual(doc.get("allowed_for_guest"), 0)
		self.assertEqual(loaders._split_roles(doc.get("required_roles")), ["A", "B"])
		self.assertEqual(len(w), 4)

	def test_seed_adds_role_ignored(self):
		old = {"required_roles": "A"}
		doc = FakeDoc(**old, seed_snapshot=json.dumps(old))
		w = _apply(doc, {"required_roles": "A, B"})
		self.assertEqual(loaders._split_roles(doc.get("required_roles")), ["A"])
		self.assertTrue(w)

	def test_seed_narrows_applied(self):
		old = {"required_roles": "A, B"}
		doc = FakeDoc(**old, seed_snapshot=json.dumps(old))
		w = _apply(doc, {"required_roles": "B"})
		self.assertEqual(loaders._split_roles(doc.get("required_roles")), ["B"])
		self.assertEqual(w, [])

	def test_intersection_empty_keeps_existing(self):
		doc = FakeDoc(required_roles="A")
		w = _apply(doc, {"required_roles": "C"})
		self.assertEqual(loaders._split_roles(doc.get("required_roles")), ["A"])
		self.assertTrue(w)

	def test_existing_empty_applies_seed(self):
		doc = FakeDoc(required_roles="")
		w = _apply(doc, {"required_roles": "C, D"})
		self.assertEqual(loaders._split_roles(doc.get("required_roles")), ["C", "D"])
		self.assertEqual(w, [])

	def test_reseed_tightening_applies(self):
		old = {"requires_confirmation": 0, "is_outbound": 0, "allowed_for_guest": 1, "required_roles": "A, B"}
		doc = FakeDoc(**old, seed_snapshot=json.dumps(old))
		seed = {"requires_confirmation": 1, "is_outbound": 1, "allowed_for_guest": 0, "required_roles": "A"}
		w = _apply(doc, seed)
		self.assertEqual((doc.get("requires_confirmation"), doc.get("is_outbound"), doc.get("allowed_for_guest")), (1, 1, 0))
		self.assertEqual(loaders._split_roles(doc.get("required_roles")), ["A"])
		self.assertEqual(w, [])

	def test_first_adoption_keeps_stricter(self):
		doc = FakeDoc(requires_confirmation=1, allowed_for_guest=0, required_roles="A")
		w = _apply(doc, {"requires_confirmation": 0, "allowed_for_guest": 1, "required_roles": "C"})
		self.assertEqual(doc.get("requires_confirmation"), 1)
		self.assertEqual(doc.get("allowed_for_guest"), 0)
		self.assertEqual(loaders._split_roles(doc.get("required_roles")), ["A"])
		self.assertTrue(w)

	def test_agent_allowed_roles_only_narrow(self):
		doc = FakeDoc(allowed_roles=[{"role": "Sales"}, {"role": "HR"}])
		_apply(doc, {"allowed_roles": [{"role": "Sales"}]})
		self.assertEqual(loaders._table_roles(doc.get("allowed_roles")), ["Sales"])
		_apply(doc, {"allowed_roles": [{"role": "Sales"}, {"role": "X"}]})
		self.assertEqual(loaders._table_roles(doc.get("allowed_roles")), ["Sales"])
