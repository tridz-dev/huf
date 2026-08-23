# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

"""Unit tests for ``FlowDefinition._validate_definition_json`` (shared graph-IR migration).

Frappe-free by design, mirroring ``huf/ai/tests/test_procedure_conversion.py``:
``huf.huf.doctype.flow_definition.flow_definition`` imports ``frappe`` at module load
time, and ``huf.ai.graph.validator`` (which it now delegates validation to) imports
``huf.ai.graph.permissions``, whose ``default_tool_classifier`` calls
``frappe.get_cached_doc`` -- but only when a ``tool.call`` node is actually present, and
none of the fixtures below use one, so the narrow standalone stub installed here never
needs to answer that call.

These tests exercise the doctype's own validation entry point directly against a bare
instance (bypassing ``frappe.model.document.Document.__init__``), rather than a full
``frappe.get_doc(...).insert()`` round trip -- that would need a live site, which is
what ``huf/huf/doctype/agent_procedure/test_agent_procedure.py`` is for on the Procedure
side. There is no equivalent Flow Definition integration test file yet; this file is
the schema-conformance unit-test layer only.

Run with:
  pytest huf/huf/doctype/flow_definition/test_flow_definition.py
  bench --site <site> run-tests --app huf --module huf.huf.doctype.flow_definition.test_flow_definition
"""

import json
import sys
import types
import unittest
from unittest.mock import MagicMock


def _install_standalone_frappe_stub():
	existing = sys.modules.get("frappe")
	if existing is not None and isinstance(getattr(existing, "__file__", None), str):
		# A real ``frappe`` (or an equivalent module-shaped stub) is already loaded --
		# e.g. running under a real bench. Do not replace it.
		return

	class _FakeValidationError(Exception):
		pass

	def _throw(msg, exc=_FakeValidationError, *a, **k):
		raise exc(msg)

	fake = MagicMock(name="frappe")
	fake.ValidationError = _FakeValidationError
	fake.PermissionError = PermissionError
	fake._ = lambda msg, *a, **k: msg
	fake.throw = _throw
	fake.whitelist = lambda *a, **k: lambda f: f

	fake_utils = types.ModuleType("frappe.utils")
	fake_utils.now_datetime = lambda: None
	fake.utils = fake_utils

	fake_document = types.ModuleType("frappe.model.document")

	class _FakeDocument:
		pass

	fake_document.Document = _FakeDocument
	fake_model = types.ModuleType("frappe.model")
	fake_model.document = fake_document
	fake.model = fake_model

	sys.modules["frappe"] = fake
	sys.modules["frappe.utils"] = fake_utils
	sys.modules["frappe.model"] = fake_model
	sys.modules["frappe.model.document"] = fake_document


_install_standalone_frappe_stub()

import frappe  # noqa: E402 -- must follow the stub install

from huf.huf.doctype.flow_definition.flow_definition import FlowDefinition  # noqa: E402


def _limits(**overrides) -> dict:
	limits = {
		"max_nodes": 20,
		"max_rows": 1000,
		"max_output_bytes": 100_000,
		"max_parallel_calls": 1,
		"max_foreach_iterations": 1,
		"max_external_calls": 5,
		"max_writes": 0,
		"max_wall_time_ms": 5000,
		"fail_closed": True,
	}
	limits.update(overrides)
	return limits


def _contract(**overrides) -> dict:
	contract = {
		"input_schema": {"type": "object"},
		"output_schema": {"type": "object"},
		"applies_when": [],
		"permission_envelope": {"read": [], "write": [], "http": "none", "code": "none"},
		"limits": _limits(),
	}
	contract.update(overrides)
	return contract


def _valid_flow_definition() -> dict:
	"""A minimal, schema-valid Flow graph: shared-IR shape (nodes carry their own
	``next``, no top-level ``edges`` array, ``schema_version`` as the literal string
	``"1.0.0"``)."""
	return {
		"schema_version": "1.0.0",
		"profile": "flow",
		"fingerprint": "0" * 64,
		"entry": "start",
		"nodes": [
			{
				"id": "start",
				"type": "trigger.webhook",
				"config": {"method": "POST"},
				"next": "finish",
			},
			{
				"id": "finish",
				"type": "output",
				"config": {"value": {"$from": "start"}},
			},
		],
		"contract": _contract(),
	}


def _old_shape_definition() -> dict:
	"""The pre-migration shape this validator used to accept: a top-level ``edges``
	array, an integer ``schema_version``, and no ``next``/``on_error`` pointers on
	nodes. Every one of these is now a rejection, not a shim."""
	return {
		"schema_version": 1,
		"id": "flow-1",
		"version": 1,
		"entry": "start",
		"nodes": [
			{"id": "start", "type": "trigger.webhook", "config": {"method": "POST"}},
			{"id": "finish", "type": "end", "config": {}},
		],
		"edges": [{"from": "start", "to": "finish", "type": "always"}],
		"settings": {},
		"metadata": {},
	}


class _FakeFlowDefinition(FlowDefinition):
	"""Bypasses ``frappe.model.document.Document.__init__`` (no live site here) --
	tests set only the attributes ``_validate_definition_json`` actually reads."""

	def __init__(self, definition_json):
		self.definition_json = definition_json
		self.flow_id = "flow-1"
		self.schema_version = None


class TestFlowDefinitionValidation(unittest.TestCase):
	def test_accepts_valid_shared_ir_shape(self):
		doc = _FakeFlowDefinition(json.dumps(_valid_flow_definition()))
		doc._validate_definition_json()
		self.assertEqual(doc.schema_version, "1.0.0")

	def test_rejects_old_edges_array_shape(self):
		doc = _FakeFlowDefinition(json.dumps(_old_shape_definition()))
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc._validate_definition_json()
		# The old shape fails schema conformance on more than one axis at once
		# (int schema_version, a stray top-level "edges"/"id"/"version"/"settings"/
		# "metadata", nodes missing "next"/"contract") -- assert on the parts of the
		# message that prove it was actually rejected for being the old shape, not
		# some unrelated reason.
		message = str(ctx.exception)
		self.assertIn("graph-IR", message)

	def test_rejects_stray_old_format_keys_even_with_new_required_fields_present(self):
		"""A definition that supplies every new-IR required key *and* still carries a
		stray old-format key (top-level "edges") must be rejected -- the schema is
		``additionalProperties: false``, so this is not a matter of ignoring unknown
		keys."""
		defn = _valid_flow_definition()
		defn["edges"] = [{"from": "start", "to": "finish", "type": "always"}]
		doc = _FakeFlowDefinition(json.dumps(defn))
		with self.assertRaises(frappe.ValidationError):
			doc._validate_definition_json()

	def test_rejects_missing_json(self):
		doc = _FakeFlowDefinition(None)
		with self.assertRaises(frappe.ValidationError):
			doc._validate_definition_json()

	def test_rejects_invalid_json(self):
		doc = _FakeFlowDefinition("{not json")
		with self.assertRaises(frappe.ValidationError):
			doc._validate_definition_json()


if __name__ == "__main__":
	unittest.main()
