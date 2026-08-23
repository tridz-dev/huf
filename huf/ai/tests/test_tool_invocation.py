"""Tests for huf.ai.tool_invocation (T-10).

Frappe-free by design, following the huf.ai.tools.execution_sandbox /
test_execution_sandbox_isolation.py precedent: the module under test needs
frappe only for a handful of narrow calls (frappe.session.user,
frappe.db.get_value, frappe.get_doc, frappe.logger, frappe.get_traceback),
so this suite installs a small controlled fake into sys.modules before
import instead of depending on a live bench. Run with either:

    python -m unittest huf.ai.tests.test_tool_invocation -v
    pytest huf/ai/tests/test_tool_invocation.py -v

Covers the security fixes T-10 exists to make (seam audit F-21 / invariant
I1): the ignore_permissions strip is unconditional, the guest/mutating-type
gate applies uniformly to real Agent Tool Function docs AND to the bare
alias fallback, and the guest-doctype-pin refusal path is preserved. Also
covers what must be preserved byte-for-byte: signature-aware argument
filtering, _merge_run_context's blank-string-counts-as-absent semantics,
and the extra_args overwrite-vs-setdefault standardization documented in
tool_invocation.build_extra_args.
"""

import asyncio
import importlib.util
import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock


class _FakeSession:
	def __init__(self, user="Administrator"):
		self.user = user


class _FakeDB:
	"""Minimal frappe.db stand-in: a dict of {(doctype, key_tuple): row}."""

	def __init__(self):
		self.tool_function_rows: dict[str, dict] = {}
		self.mcp_rows: dict[str, str] = {}

	def get_value(self, doctype, filters, fields=None, as_dict=False):
		if doctype == "Agent Tool Function":
			tool_name = filters.get("tool_name") if isinstance(filters, dict) else filters
			row = self.tool_function_rows.get(tool_name)
			if not row:
				return None
			if as_dict:
				return dict(row)
			return tuple(row.get(f) for f in fields)
		if doctype == "MCP Server Tool":
			tool_name = filters.get("tool_name") if isinstance(filters, dict) else filters
			return self.mcp_rows.get(tool_name)
		return None


class _FakeDoc:
	"""Minimal frappe.get_doc({...}) stand-in that records insert/update/save."""

	def __init__(self, data):
		self.data = dict(data)
		self.inserted_with = None
		self.saved_with_update = None

	def insert(self, ignore_permissions=False):
		self.inserted_with = {"ignore_permissions": ignore_permissions}
		return self

	def update(self, values):
		self.data.update(values)
		return self

	def save(self, ignore_permissions=False):
		self.saved_with_update = dict(self.data)
		return self


class _FakeFrappe(SimpleNamespace):
	pass


def _install_fake_frappe():
	# On a real bench (bench run-tests) 'frappe' is already the genuine
	# package -- a proper module with a __file__ -- imported by the test
	# runner itself before this module loads. Never clobber that; this
	# suite's fake is only for the frappe-free local/CI path (no bench, no
	# live site), matching the huf.ai.tools.execution_sandbox precedent.
	existing = sys.modules.get("frappe")
	if existing is not None and hasattr(existing, "__file__"):
		return existing

	fake = _FakeFrappe()
	fake.session = _FakeSession()
	fake.db = _FakeDB()
	fake._docs = []

	def get_doc(data):
		doc = _FakeDoc(data)
		fake._docs.append(doc)
		return doc

	fake.get_doc = get_doc
	fake.logger = lambda *a, **k: MagicMock()
	fake.get_traceback = lambda: ""
	fake.set_user = lambda user: setattr(fake.session, "user", user)

	sys.modules["frappe"] = fake
	return fake


_FAKE_FRAPPE = _install_fake_frappe()


def _install_module_under_test():
	"""On a real bench, import the module normally through the real huf
	package so this suite also exercises the actual sdk_tools/tool_types
	wiring. Locally (no bench, frappe not installed), load
	huf/ai/tool_invocation.py directly from disk, bypassing
	``huf/__init__.py`` (which does a real ``import frappe`` at package
	load time), stubbing the two narrow constants tool_invocation needs
	from ``huf.ai.tool_types`` rather than pulling in the real
	``huf.ai.tool_registry`` module and its own frappe/DB dependencies.
	"""
	if hasattr(sys.modules.get("frappe"), "__file__"):
		from huf.ai import tool_invocation as _real_module
		return _real_module

	if "huf" not in sys.modules:
		sys.modules["huf"] = types.ModuleType("huf")
	if "huf.ai" not in sys.modules:
		sys.modules["huf.ai"] = types.ModuleType("huf.ai")

	tool_types_stub = types.ModuleType("huf.ai.tool_types")
	tool_types_stub.MUTATING_TOOL_TYPES = {
		"Create Document", "Create Multiple Documents",
		"Update Document", "Update Multiple Documents",
		"Delete Document", "Delete Multiple Documents",
		"Submit Document", "Cancel Document",
		"Set Value", "POST", "Run Agent",
		"Attach File to Document", "Builder",
	}
	tool_types_stub._GUEST_DOCTYPE_PINNED_TYPES = {
		"Get Document", "Get Multiple Documents", "Get List",
		"Create Document", "Create Multiple Documents",
		"Update Document", "Update Multiple Documents",
		"Delete Document", "Delete Multiple Documents",
		"Attach File to Document",
	}
	sys.modules["huf.ai.tool_types"] = tool_types_stub

	module_path = os.path.join(os.path.dirname(__file__), "..", "tool_invocation.py")
	spec = importlib.util.spec_from_file_location("huf.ai.tool_invocation", module_path)
	module = importlib.util.module_from_spec(spec)
	sys.modules["huf.ai.tool_invocation"] = module
	spec.loader.exec_module(module)
	return module


ti = _install_module_under_test()


def _reset_frappe(user="Administrator"):
	_FAKE_FRAPPE.session.user = user
	_FAKE_FRAPPE.db.tool_function_rows.clear()
	_FAKE_FRAPPE.db.mcp_rows.clear()
	_FAKE_FRAPPE._docs.clear()


def _run(coro):
	return asyncio.run(coro)


class ResolveToolDocTests(unittest.TestCase):
	def setUp(self):
		_reset_frappe()

	def test_resolves_real_agent_tool_function(self):
		_FAKE_FRAPPE.db.tool_function_rows["my_tool"] = {
			"name": "ATF-00042",
			"tool_name": "my_tool",
			"types": "Get Document",
			"function_path": None,
			"reference_doctype": "Task",
			"agent": None,
			"function_name": None,
			"allowed_for_guest": 0,
			"blocking": 0,
			"base_url": None,
		}
		doc = ti.resolve_tool_doc("my_tool")
		self.assertEqual(doc["types"], "Get Document")
		self.assertEqual(doc["reference_doctype"], "Task")

	def test_falls_back_to_standard_alias(self):
		doc = ti.resolve_tool_doc("delete_document")
		self.assertIsNotNone(doc)
		self.assertEqual(doc["types"], "Delete Document")
		# F-21: the alias doc must carry no pin and no guest allowance --
		# nothing for the permission gate to trust.
		self.assertIsNone(doc["reference_doctype"])
		self.assertFalse(doc["allowed_for_guest"])

	def test_unknown_tool_name_resolves_to_none(self):
		self.assertIsNone(ti.resolve_tool_doc("not_a_real_tool"))

	def test_real_doc_takes_priority_over_alias_name(self):
		# A real Agent Tool Function named e.g. "get_document" (matching an
		# alias name) must resolve to the real doc's fields, not the
		# synthetic alias -- the alias is only a fallback.
		_FAKE_FRAPPE.db.tool_function_rows["get_document"] = {
			"name": "ATF-00099",
			"tool_name": "get_document",
			"types": "Get Document",
			"function_path": None,
			"reference_doctype": "Contact",
			"agent": None,
			"function_name": None,
			"allowed_for_guest": 1,
			"blocking": 0,
			"base_url": None,
		}
		doc = ti.resolve_tool_doc("get_document")
		self.assertEqual(doc["reference_doctype"], "Contact")
		self.assertTrue(doc["allowed_for_guest"])


class ResolveFunctionPathTests(unittest.TestCase):
	def test_static_map_covers_all_27_types(self):
		# All types the seam audit's §1 documents A (sdk_tools) resolving,
		# now available uniformly through the shared map -- including the
		# five memory types B never had (Save/Search/Get/Archive Memory
		# Record, Promote Memory to Knowledge).
		for tool_type, expected_path in ti.TYPE_TO_FUNCTION_PATH.items():
			self.assertEqual(
				ti.resolve_function_path({"types": tool_type}), expected_path
			)

	def test_custom_function_uses_doc_function_path(self):
		path = ti.resolve_function_path({"types": "Custom Function", "function_path": "a.b.c"})
		self.assertEqual(path, "a.b.c")

	def test_client_side_tool_requires_function_name(self):
		self.assertIsNone(
			ti.resolve_function_path({"types": "Client Side Tool", "function_name": None})
		)
		self.assertEqual(
			ti.resolve_function_path({"types": "Client Side Tool", "function_name": "doThing"}),
			ti.CLIENT_SIDE_TOOL_FUNCTION_PATH,
		)

	def test_unknown_type_resolves_to_none(self):
		self.assertIsNone(ti.resolve_function_path({"types": "Not A Real Type"}))


class BuildExtraArgsTests(unittest.TestCase):
	def test_reference_doctype_pin(self):
		extra = ti.build_extra_args({"types": "Get List", "reference_doctype": "Task"})
		self.assertEqual(extra, {"reference_doctype": "Task"})

	def test_attach_file_to_document_pin(self):
		extra = ti.build_extra_args({"types": "Attach File to Document", "reference_doctype": "Task"})
		self.assertEqual(extra, {"reference_doctype": "Task"})

	def test_no_pin_when_reference_doctype_blank(self):
		extra = ti.build_extra_args({"types": "Get List", "reference_doctype": None})
		self.assertEqual(extra, {})

	def test_run_agent_target(self):
		extra = ti.build_extra_args({"types": "Run Agent", "agent": "Support Bot"})
		self.assertEqual(extra, {"target_agent_name": "Support Bot"})

	def test_client_side_tool_function_name(self):
		extra = ti.build_extra_args({"types": "Client Side Tool", "function_name": "doThing"})
		self.assertEqual(extra, {"function_name": "doThing"})

	def test_get_post_uses_friendly_tool_name_not_docname(self):
		# Seam audit §2: the old B-side bug used tool_doc["name"] (the
		# Frappe docname for a real doc lookup) instead of the friendly
		# tool_name. This resolver always uses tool_name.
		extra = ti.build_extra_args({"types": "GET", "tool_name": "weather_lookup", "name": "ATF-00007"})
		self.assertEqual(extra, {"tool_name": "weather_lookup"})

	def test_get_post_falls_back_to_name_for_alias_docs(self):
		# The synthetic alias doc has no separate docname; tool_name IS name.
		extra = ti.build_extra_args({"types": "POST", "tool_name": "webhook_call", "name": "webhook_call"})
		self.assertEqual(extra, {"tool_name": "webhook_call"})


class CheckToolPermissionTests(unittest.TestCase):
	def setUp(self):
		_reset_frappe()

	def test_non_guest_always_allowed(self):
		_FAKE_FRAPPE.session.user = "Administrator"
		result = ti.check_tool_permission("Delete Document", allowed_for_guest=False)
		self.assertTrue(result["allowed"])

	def test_guest_blocked_from_mutating_type(self):
		_FAKE_FRAPPE.session.user = "Guest"
		result = ti.check_tool_permission("Delete Document", allowed_for_guest=False)
		self.assertFalse(result["allowed"])
		self.assertIn("Guest users cannot use", result["error"])

	def test_guest_allowed_when_explicitly_permitted(self):
		_FAKE_FRAPPE.session.user = "Guest"
		result = ti.check_tool_permission("Delete Document", allowed_for_guest=True)
		self.assertTrue(result["allowed"])

	def test_guest_allowed_for_non_mutating_type_by_default(self):
		_FAKE_FRAPPE.session.user = "Guest"
		result = ti.check_tool_permission("Get Document", allowed_for_guest=False)
		self.assertTrue(result["allowed"])


class InvokeToolSecurityTests(unittest.TestCase):
	"""The core of T-10: closing F-21 structurally, for both a real Agent
	Tool Function doc and the bare-name alias path.
	"""

	def setUp(self):
		_reset_frappe()
		# A fake handler module reachable via get_function_from_name's
		# module-import mechanism would require a real importable module;
		# instead we monkeypatch tool_invocation.get_function_from_name
		# directly, since it is a thin re-export by design.
		self._orig_get_function = ti.get_function_from_name

	def tearDown(self):
		ti.get_function_from_name = self._orig_get_function

	def _register_tool(self, tool_name, types, reference_doctype=None, allowed_for_guest=0):
		_FAKE_FRAPPE.db.tool_function_rows[tool_name] = {
			"name": f"ATF-{tool_name}",
			"tool_name": tool_name,
			"types": types,
			"function_path": None,
			"reference_doctype": reference_doctype,
			"agent": None,
			"function_name": None,
			"allowed_for_guest": allowed_for_guest,
			"blocking": 0,
			"base_url": None,
		}

	def test_ignore_permissions_is_always_stripped(self):
		captured = {}

		def fake_handler(**kwargs):
			captured.update(kwargs)
			return {"ok": True}

		ti.get_function_from_name = lambda path: fake_handler
		self._register_tool("dangerous_tool", "Update Document", reference_doctype="Task")

		result = _run(ti.invoke_tool(
			"dangerous_tool",
			{"name": "TASK-0001", "ignore_permissions": True},
		))

		self.assertTrue(result.success)
		self.assertNotIn("ignore_permissions", captured)

	def test_ignore_permissions_stripped_via_alias_path_too(self):
		# F-21's exact live gap: a caller reaching a mutating built-in by
		# bare name with no backing Agent Tool Function document at all.
		captured = {}

		def fake_handler(**kwargs):
			captured.update(kwargs)
			return {"ok": True}

		ti.get_function_from_name = lambda path: fake_handler
		_FAKE_FRAPPE.session.user = "Administrator"

		result = _run(ti.invoke_tool(
			"delete_document",
			{"doctype": "Task", "name": "TASK-0001", "ignore_permissions": True},
		))

		self.assertTrue(result.success)
		self.assertNotIn("ignore_permissions", captured)

	def test_guest_blocked_from_mutating_alias_with_no_backing_doc(self):
		ti.get_function_from_name = lambda path: (lambda **kw: {"ok": True})
		_FAKE_FRAPPE.session.user = "Guest"

		result = _run(ti.invoke_tool("delete_document", {"name": "TASK-0001"}))

		self.assertFalse(result.success)
		self.assertTrue(result.denied)

	def test_guest_pinned_type_without_pin_is_refused(self):
		ti.get_function_from_name = lambda path: (lambda **kw: {"ok": True})
		self._register_tool("open_lookup", "Get Document", reference_doctype=None, allowed_for_guest=1)
		_FAKE_FRAPPE.session.user = "Guest"

		result = _run(ti.invoke_tool("open_lookup", {"name": "TASK-0001"}))

		self.assertFalse(result.success)
		self.assertTrue(result.denied)
		self.assertIn("no fixed target doctype", result.error)

	def test_guest_pinned_type_with_pin_sets_sanctioned_bypass(self):
		captured = {}

		def fake_handler(**kwargs):
			captured.update(kwargs)
			return {"ok": True}

		ti.get_function_from_name = lambda path: fake_handler
		self._register_tool("public_faq", "Get Document", reference_doctype="FAQ", allowed_for_guest=1)
		_FAKE_FRAPPE.session.user = "Guest"

		result = _run(ti.invoke_tool("public_faq", {"name": "FAQ-1"}))

		self.assertTrue(result.success)
		# The ONE sanctioned bypass, set by the service itself post-strip --
		# never accepted verbatim from the caller.
		self.assertTrue(captured.get("ignore_permissions"))
		self.assertEqual(captured.get("reference_doctype"), "FAQ")

	def test_extra_args_pin_overwrites_caller_supplied_value(self):
		# Standardized on overwrite semantics (seam audit §2): a caller
		# cannot override a pinned reference_doctype by supplying their own.
		captured = {}

		def fake_handler(**kwargs):
			captured.update(kwargs)
			return {"ok": True}

		ti.get_function_from_name = lambda path: fake_handler
		self._register_tool("pinned_tool", "Get List", reference_doctype="Task")

		_run(ti.invoke_tool("pinned_tool", {"reference_doctype": "User"}))

		self.assertEqual(captured.get("reference_doctype"), "Task")


class SignatureFilteringTests(unittest.TestCase):
	"""Preserved byte-for-byte: filter to declared params unless the handler
	accepts **kwargs.
	"""

	def setUp(self):
		_reset_frappe()

	def test_filters_to_declared_params(self):
		captured = {}

		def fake_handler(name, reference_doctype):
			captured["kwargs"] = {"name": name, "reference_doctype": reference_doctype}
			return {"ok": True}

		ti.get_function_from_name = lambda path: fake_handler
		_FAKE_FRAPPE.db.tool_function_rows["strict_tool"] = {
			"name": "ATF-strict", "tool_name": "strict_tool", "types": "Get Document",
			"function_path": None, "reference_doctype": "Task", "agent": None,
			"function_name": None, "allowed_for_guest": 0, "blocking": 0, "base_url": None,
		}

		result = _run(ti.invoke_tool(
			"strict_tool", {"name": "TASK-1", "extra_unrelated_key": "dropped"}
		))

		self.assertTrue(result.success)
		self.assertNotIn("extra_unrelated_key", captured["kwargs"])

	def test_passes_everything_when_handler_accepts_kwargs(self):
		captured = {}

		def fake_handler(**kwargs):
			captured.update(kwargs)
			return {"ok": True}

		ti.get_function_from_name = lambda path: fake_handler
		_FAKE_FRAPPE.db.tool_function_rows["loose_tool"] = {
			"name": "ATF-loose", "tool_name": "loose_tool", "types": "Get Document",
			"function_path": None, "reference_doctype": None, "agent": None,
			"function_name": None, "allowed_for_guest": 0, "blocking": 0, "base_url": None,
		}

		_run(ti.invoke_tool("loose_tool", {"name": "TASK-1", "whatever": "kept"}))

		self.assertIn("whatever", captured)


class MergeRunContextTests(unittest.TestCase):
	"""_merge_run_context: preserved byte-for-byte, including the
	blank-string-counts-as-absent semantics documented in sdk_tools.py's
	original docstring (a real production incident).
	"""

	def test_blank_string_is_overwritten_by_run_context(self):
		args = {"conversation_id": ""}
		ctx = ti.RunContext(conversation_id="CONV-real-id")
		ti._merge_run_context(args, ctx)
		self.assertEqual(args["conversation_id"], "CONV-real-id")

	def test_explicit_non_blank_value_wins(self):
		args = {"conversation_id": "CONV-caller-chosen"}
		ctx = ti.RunContext(conversation_id="CONV-context")
		ti._merge_run_context(args, ctx)
		self.assertEqual(args["conversation_id"], "CONV-caller-chosen")

	def test_call_id_only_setdefault(self):
		args = {"call_id": "already-set"}
		ctx = ti.RunContext(call_id="from-ctx")
		ti._merge_run_context(args, ctx)
		self.assertEqual(args["call_id"], "already-set")


class TelemetryTests(unittest.TestCase):
	"""GT-05/I5: telemetry owned by the service, opt-in per call so the
	LLM path (which already has its own, elsewhere) doesn't get doubled.
	"""

	def setUp(self):
		_reset_frappe()

	def test_telemetry_off_by_default_creates_no_doc(self):
		ti.get_function_from_name = lambda path: (lambda **kw: {"ok": True})
		_FAKE_FRAPPE.db.tool_function_rows["quiet_tool"] = {
			"name": "ATF-quiet", "tool_name": "quiet_tool", "types": "Get Document",
			"function_path": None, "reference_doctype": None, "agent": None,
			"function_name": None, "allowed_for_guest": 0, "blocking": 0, "base_url": None,
		}

		_run(ti.invoke_tool("quiet_tool", {"name": "X"}))

		self.assertEqual(len(_FAKE_FRAPPE._docs), 0)

	def test_telemetry_on_creates_started_then_finalizes_completed(self):
		ti.get_function_from_name = lambda path: (lambda **kw: {"value": 42})
		_FAKE_FRAPPE.db.tool_function_rows["loud_tool"] = {
			"name": "ATF-loud", "tool_name": "loud_tool", "types": "Get Document",
			"function_path": None, "reference_doctype": None, "agent": None,
			"function_name": None, "allowed_for_guest": 0, "blocking": 0, "base_url": None,
		}

		ctx = ti.RunContext(conversation_id="CONV-1", agent_run_id="RUN-1")
		result = _run(ti.invoke_tool("loud_tool", {"name": "X"}, ctx=ctx, telemetry=True))

		self.assertTrue(result.success)
		self.assertEqual(len(_FAKE_FRAPPE._docs), 1)
		doc = _FAKE_FRAPPE._docs[0]
		self.assertEqual(doc.inserted_with, {"ignore_permissions": True})
		self.assertEqual(doc.data["status"], "Completed")
		self.assertEqual(doc.data["agent_run"], "RUN-1")
		self.assertEqual(doc.data["conversation"], "CONV-1")
		self.assertTrue(doc.data["call_id"].startswith("call_"))

	def test_telemetry_marks_failed_on_handler_error(self):
		def raising_handler(**kwargs):
			raise ValueError("boom")

		ti.get_function_from_name = lambda path: raising_handler
		_FAKE_FRAPPE.db.tool_function_rows["failing_tool"] = {
			"name": "ATF-fail", "tool_name": "failing_tool", "types": "Get Document",
			"function_path": None, "reference_doctype": None, "agent": None,
			"function_name": None, "allowed_for_guest": 0, "blocking": 0, "base_url": None,
		}

		result = _run(ti.invoke_tool("failing_tool", {"name": "X"}, telemetry=True))

		self.assertFalse(result.success)
		self.assertEqual(_FAKE_FRAPPE._docs[0].data["status"], "Failed")
		self.assertIn("boom", _FAKE_FRAPPE._docs[0].data["error_message"])


class InvokeToolSyncTests(unittest.TestCase):
	"""flow_tool_executor's use case: a synchronous caller, no ambient
	event loop, no per-call new_event_loop hazard (seam audit §3).
	"""

	def setUp(self):
		_reset_frappe()

	def test_sync_wrapper_runs_to_completion(self):
		ti.get_function_from_name = lambda path: (lambda **kw: {"value": 1})
		_FAKE_FRAPPE.db.tool_function_rows["sync_tool"] = {
			"name": "ATF-sync", "tool_name": "sync_tool", "types": "Get Document",
			"function_path": None, "reference_doctype": None, "agent": None,
			"function_name": None, "allowed_for_guest": 0, "blocking": 0, "base_url": None,
		}

		result = ti.invoke_tool_sync("sync_tool", {"name": "X"})

		self.assertTrue(result.success)
		self.assertEqual(result.result, {"value": 1})

	def test_sync_wrapper_awaits_coroutine_handlers(self):
		async def async_handler(**kwargs):
			return {"async": True}

		ti.get_function_from_name = lambda path: async_handler
		_FAKE_FRAPPE.db.tool_function_rows["async_tool"] = {
			"name": "ATF-async", "tool_name": "async_tool", "types": "Get Document",
			"function_path": None, "reference_doctype": None, "agent": None,
			"function_name": None, "allowed_for_guest": 0, "blocking": 0, "base_url": None,
		}

		result = ti.invoke_tool_sync("async_tool", {"name": "X"})

		self.assertTrue(result.success)
		self.assertEqual(result.result, {"async": True})


class ToolResultAsDictTests(unittest.TestCase):
	def test_success_shape(self):
		r = ti.ToolResult(success=True, result={"a": 1})
		self.assertEqual(r.as_dict(), {"success": True, "result": {"a": 1}})

	def test_failure_shape(self):
		r = ti.ToolResult(success=False, error="nope")
		self.assertEqual(r.as_dict(), {"success": False, "error": "nope"})

	def test_denied_shape(self):
		r = ti.ToolResult(success=False, error="nope", denied=True)
		self.assertEqual(r.as_dict(), {"success": False, "error": "nope", "denied": True})


if __name__ == "__main__":
	unittest.main()
