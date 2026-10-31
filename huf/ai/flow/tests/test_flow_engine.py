"""
Behavioural test suite for huf.ai.flow.engine.

Flow is an experimental, unreleased subsystem: there are zero Flow Definitions
and zero Flow Runs on any real site today, and there were zero tests for this
module before this file. This suite is therefore NOT a characterization suite
freezing today's behaviour -- it asserts INTENDED behaviour at a level of
abstraction (observable outcomes: which node ran, what the context dict
contains, which edge fired, run status transitions) that should survive T-22's
planned replacement of flow_engine's internals with a shared graph IR.

Test classes and their bench requirements
------------------------------------------
Frappe-free (plain pytest / stubbed frappe via huf/ai/tests/conftest.py,
no live bench, no DB):
    - TestFromReferenceResolution
    - TestResolveRecursive
    - TestEvaluateEdges
    - TestExecCondition
    - TestExecTransform
    - TestExecForeach
    - TestExecTriggerWebhook
    - TestExecToolCallInterpolation   (mocks frappe.db.get_value / execute_tool;
                                        no real DB)
    - TestApproveFlowRunRouting       (mocks frappe.get_doc / flow_engine.load_definition)
    - TestHopLimitAndEndCompletion    (drives _execute_loop with a FakeFlowRun)
    - TestKnownDefects                (F-1..F-4 expectedFailure acceptance tests)

Bench-requiring (needs a live Frappe site; run with
`bench --site <site> run-tests --app huf --module huf.ai.flow.tests.test_flow_engine`):
    - TestFlowRunLifecycleBench (UnitTestCase) -- exercises run_flow / resume_flow_run /
      approve_flow_run against real Flow Definition + Flow Run documents, to
      catch anything the frappe-free fakes below paper over (real db_set /
      reload semantics, real permission checks, real Document validation).

Known-defect handling (do NOT pin these as correct; see the T-01 task brief
for full descriptions -- these are being fixed in T-22):
    F-1: flow version auto-increments on every save; resumed/re-entered runs
         re-fetch the CURRENT definition instead of the one pinned at run start.
    F-2: four divergent {{...}} interpolation implementations with different
         semantics (dotted-path resolution vs flat-key-only).
    F-3: loop node burns one hop per iteration against the run's hop budget,
         so a loop with more items than max_hops cannot complete.
    F-4: no lock on run_flow; concurrent resumes can race the same cursor.

Each F-numbered defect is covered by a real assertion of the INTENDED
(post-fix) behaviour, decorated with `@unittest.expectedFailure` and a reason
string naming the F-number, so these tests can become T-22's acceptance
criteria as-is once the fix lands. Everywhere else, we simply do not assert on
the defective path.
"""

import contextlib
import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# flow/engine.py does `from frappe.<dotted.submodule> import X` for a few
# names (frappe.utils, frappe.desk.doctype.notification_log.notification_log,
# frappe.desk.doctype.notification_settings.notification_settings). Unlike a
# plain `import frappe` + attribute access, Python's import statement resolves
# a dotted "from" target as a real submodule lookup, which a bare
# `MagicMock()` standing in for the top-level `frappe` module cannot satisfy
# on its own (see huf/ai/tests/conftest.py, which only stubs the top-level
# name). Pre-register the specific dotted submodules flow_engine needs as
# MagicMocks too, mirroring conftest's "only if frappe isn't already
# importable" guard, so this file can be collected standalone (e.g. plain
# `pytest huf/ai/flow/tests/test_flow_engine.py`) as well as alongside the rest of
# the suite.
if "frappe" not in sys.modules:
	sys.modules["frappe"] = MagicMock()
for _mod_name in (
	"frappe.utils",
	"frappe.desk",
	"frappe.desk.doctype",
	"frappe.desk.doctype.notification_log",
	"frappe.desk.doctype.notification_log.notification_log",
	"frappe.desk.doctype.notification_settings",
	"frappe.desk.doctype.notification_settings.notification_settings",
):
	if _mod_name not in sys.modules:
		sys.modules[_mod_name] = MagicMock()

# When frappe is stubbed, `frappe.whitelist()` is itself a MagicMock call that
# returns another MagicMock -- used as `@frappe.whitelist()` that would
# replace `approve_flow_run` with a MagicMock instead of the real function,
# silently defeating every test in TestApproveFlowRunRouting below. Make the
# stub's `whitelist` behave like the real decorator (identity) instead, but
# only when frappe is in fact our stub -- never touch a real frappe module.
if isinstance(sys.modules.get("frappe"), MagicMock):
	sys.modules["frappe"].whitelist = lambda *a, **k: (lambda f: f)

from huf.ai.flow import engine as flow_engine
from huf.ai.graph.executor import GraphContext

# Another test module may have imported the engine before the identity `whitelist` above was
# installed, leaving MagicMock-wrapped public functions; re-execute the module once so they are real.
if isinstance(sys.modules.get("frappe"), MagicMock) and isinstance(flow_engine.approve_flow_run, MagicMock):
	import importlib

	importlib.reload(flow_engine)


# ---------------------------------------------------------------------------
# Shared frappe-free fakes
# ---------------------------------------------------------------------------


class FakeFlowRun:
	"""A minimal stand-in for the Flow Run Document.

	Mirrors the subset of the Document API flow_engine actually touches:
	attribute access for field reads, `.db_set(...)` for field writes (both
	single-field and dict forms, matching real Frappe's Document.db_set), and
	a no-op `.reload()` since this fake has no separate DB copy to diverge
	from mid-test (tests that need reload-observable state mutate the fake
	directly between calls).
	"""

	def __init__(self, **fields):
		defaults = dict(
			name="FR-TEST-0001",
			flow_id="test-flow",
			flow_definition="test-flow",
			flow_version=1,
			mode="Normal",
			status="Running",
			current_node_id="n1",
			hop_count=0,
			max_hops=flow_engine.DEFAULT_MAX_HOPS,
			context_json="{}",
			waiting=None,
			conversation=None,
			last_agent_run=None,
			last_error="",
		)
		defaults.update(fields)
		for key, value in defaults.items():
			setattr(self, key, value)
		self.db_set_calls = []

	def db_set(self, field, value=None):
		if isinstance(field, dict):
			updates = field
		else:
			updates = {field: value}
		self.db_set_calls.append(dict(updates))
		for key, val in updates.items():
			setattr(self, key, val)

	def reload(self):
		pass


def _fake_transition(flow_run, values, *, from_statuses=None, not_from_statuses=None, bump_hop=False):
	"""Stand-in for ``engine._transition_run`` (a conditional SQL UPDATE) on a FakeFlowRun."""
	status = getattr(flow_run, "status", None)
	if from_statuses and status not in from_statuses:
		return False
	if not_from_statuses and status in not_from_statuses:
		return False
	flow_run.db_set(dict(values))
	if bump_hop:
		flow_run.hop_count = (flow_run.hop_count or 0) + 1
	return True


_transition_patch = patch.object(flow_engine, "_transition_run", _fake_transition)


def setUpModule():
	_transition_patch.start()


def tearDownModule():
	_transition_patch.stop()


@contextlib.contextmanager
def _no_mcp():
	"""A built-in tool call without the optional heavy imports (agents SDK, whatsapp/cryptography)."""
	fake = types.ModuleType("huf.ai.mcp_client")
	fake.find_unique_mcp_server_for_tool = lambda name: None
	with patch.dict(sys.modules, {"huf.ai.mcp_client": fake}), \
		patch.object(flow_engine, "_bound_gateway", lambda *a, **k: contextlib.nullcontext()):
		yield


def _ctx(flow_run, **overrides):
	"""Convenience: set a flow run's context_json from a plain dict."""
	data = dict(overrides)
	flow_run.context_json = json.dumps(data)
	return data


# ---------------------------------------------------------------------------
# Pure string / path helpers
# ---------------------------------------------------------------------------


class TestFromReferenceResolution(unittest.TestCase):
	"""`GraphContext.resolve` -- the single ``{"$from": ...}`` reference form
	that replaced the four ``{{...}}`` string interpolators (F-2). Mirrors
	what the old `TestInterpolateString` pinned, one reference at a time
	rather than one placeholder inside a larger string, since composing a
	string out of several interpolated fragments is exactly the capability
	GT-04 removed.
	"""

	def test_simple_substitution(self):
		ctx = GraphContext({"name": "World"})
		self.assertEqual(ctx.resolve({"$from": "context.name"}), "World")

	def test_dotted_path_substitution(self):
		ctx = GraphContext({"order": {"id": "ORD-1"}})
		self.assertEqual(ctx.resolve({"$from": "context.order.id"}), "ORD-1")

	def test_unresolved_reference_returns_none(self):
		ctx = GraphContext({})
		self.assertIsNone(ctx.resolve({"$from": "context.missing"}))

	def test_non_string_value_passes_through(self):
		ctx = GraphContext({"n": 3})
		self.assertEqual(ctx.resolve({"$from": "context.n"}), 3)

	def test_multiple_references_in_one_config_value(self):
		ctx = GraphContext({"a": "1", "b": "2"})
		self.assertEqual(
			ctx.resolve({"a": {"$from": "context.a"}, "b": {"$from": "context.b"}}),
			{"a": "1", "b": "2"},
		)

	def test_static_string_is_left_untouched(self):
		# Plain strings are no longer a templating surface -- only an exact
		# {"$from": ...} mapping is resolved; everything else, including a
		# string that happens to contain "{{...}}", passes through as-is.
		ctx = GraphContext({"name": "World"})
		self.assertEqual(ctx.resolve("Hello {{name}}"), "Hello {{name}}")


class TestResolveRecursive(unittest.TestCase):
	"""`GraphContext.resolve` recurses through nested dict/list structures,
	replacing the old `_substitute_dict` recursive ``{{ }}`` substitution.
	"""

	def test_resolves_nested_structure(self):
		ctx = GraphContext({"name": "Ada", "id": "42"})
		data = {
			"greeting": {"$from": "context.name"},
			"list": [{"$from": "context.id"}, "static"],
			"nested": {"x": {"$from": "context.name"}},
		}
		result = ctx.resolve(data)
		self.assertEqual(
			result,
			{"greeting": "Ada", "list": ["42", "static"], "nested": {"x": "Ada"}},
		)

	def test_non_reference_values_left_untouched(self):
		ctx = GraphContext({})
		data = {"count": 5, "enabled": True, "ratio": 1.5}
		self.assertEqual(ctx.resolve(data), data)

	def test_supports_dotted_paths_like_flat_keys(self):
		ctx = GraphContext({"user": {"email": "a@b.com"}})
		self.assertEqual(ctx.resolve({"to": {"$from": "context.user.email"}}), {"to": "a@b.com"})


# ---------------------------------------------------------------------------
# _evaluate_edges: priority ordering + all four edge types
# ---------------------------------------------------------------------------


class TestEvaluateEdges(unittest.TestCase):
	def _run(self, context=None):
		flow_run = FakeFlowRun()
		_ctx(flow_run, **(context or {}))
		return flow_run

	def test_no_outgoing_edges_returns_none(self):
		flow_run = self._run()
		self.assertIsNone(flow_engine._evaluate_edges(flow_run, "n1", {"status": "success"}, []))

	def test_always_edge_taken_on_success(self):
		flow_run = self._run()
		edges = [{"from": "n1", "to": "n2", "type": "always"}]
		self.assertEqual(flow_engine._evaluate_edges(flow_run, "n1", {"status": "success"}, edges), "n2")

	def test_next_is_not_followed_when_the_node_failed(self):
		flow_run = self._run()
		edges = [{"from": "n1", "to": "n2", "type": "always"}]
		self.assertIsNone(flow_engine._evaluate_edges(flow_run, "n1", {"status": "failed"}, edges))

	def test_on_error_wins_over_next_for_a_failed_node(self):
		flow_run = self._run()
		nodes = [{"id": "n1", "type": "transform", "config": {}, "next": "n2", "on_error": "err"}]
		edges = flow_engine.edges_from_nodes(nodes)
		self.assertEqual(flow_engine._evaluate_edges(flow_run, "n1", {"status": "failed"}, edges), "err")
		self.assertEqual(flow_engine._evaluate_edges(flow_run, "n1", {"status": "success"}, edges), "n2")

	def test_on_success_taken_when_status_success(self):
		flow_run = self._run()
		edges = [{"from": "n1", "to": "n2", "type": "on_success"}]
		self.assertEqual(flow_engine._evaluate_edges(flow_run, "n1", {"status": "success"}, edges), "n2")

	def test_on_success_not_taken_when_status_failed(self):
		flow_run = self._run()
		edges = [{"from": "n1", "to": "n2", "type": "on_success"}]
		self.assertIsNone(flow_engine._evaluate_edges(flow_run, "n1", {"status": "failed"}, edges))

	def test_on_failure_taken_when_status_failed(self):
		flow_run = self._run()
		edges = [{"from": "n1", "to": "n2", "type": "on_failure"}]
		self.assertEqual(flow_engine._evaluate_edges(flow_run, "n1", {"status": "failed"}, edges), "n2")

	def test_on_failure_not_taken_when_status_success(self):
		flow_run = self._run()
		edges = [{"from": "n1", "to": "n2", "type": "on_failure"}]
		self.assertIsNone(flow_engine._evaluate_edges(flow_run, "n1", {"status": "success"}, edges))

	def test_outcome_edges_are_never_followed_generically(self):
		flow_run = self._run()
		edges = [{"from": "n1", "to": "n2", "type": "outcome", "meta": {"outcome": "approved"}}]
		self.assertIsNone(flow_engine._evaluate_edges(flow_run, "n1", {"status": "success"}, edges))
		self.assertIsNone(flow_engine._evaluate_edges(flow_run, "n1", {"status": "failed"}, edges))

	def test_edges_from_other_nodes_are_ignored(self):
		flow_run = self._run()
		edges = [{"from": "other", "to": "n9", "type": "always"}]
		self.assertIsNone(flow_engine._evaluate_edges(flow_run, "n1", {"status": "success"}, edges))


# ---------------------------------------------------------------------------
# Node executors: pure-logic ones (no DB writes beyond FakeFlowRun.db_set)
# ---------------------------------------------------------------------------


class TestExecCondition(unittest.TestCase):
	def test_true_branch_routes_to_on_true(self):
		flow_run = FakeFlowRun()
		_ctx(flow_run, flag=True)
		config = {"expression": "input['flag']", "on_true": "t", "on_false": "f"}
		result = flow_engine._exec_condition(flow_run, {}, config, {})
		self.assertEqual(result["status"], "success")
		self.assertEqual(result["next_node_id"], "t")
		self.assertEqual(result["branch"], "true")

	def test_false_branch_routes_to_on_false(self):
		flow_run = FakeFlowRun()
		_ctx(flow_run, flag=False)
		config = {"expression": "input['flag']", "on_true": "t", "on_false": "f"}
		result = flow_engine._exec_condition(flow_run, {}, config, {})
		self.assertEqual(result["next_node_id"], "f")
		self.assertEqual(result["branch"], "false")

	def test_comparison_expression(self):
		flow_run = FakeFlowRun()
		_ctx(flow_run, amount=150)
		config = {"expression": "input['amount'] > 100", "on_true": "t", "on_false": "f"}
		self.assertEqual(flow_engine._exec_condition(flow_run, {}, config, {})["next_node_id"], "t")

	def test_missing_expression_fails(self):
		flow_run = FakeFlowRun()
		result = flow_engine._exec_condition(flow_run, {}, {"on_true": "t", "on_false": "f"}, {})
		self.assertEqual(result["status"], "failed")

	def test_missing_a_target_fails(self):
		flow_run = FakeFlowRun()
		result = flow_engine._exec_condition(flow_run, {}, {"expression": "True", "on_true": "t"}, {})
		self.assertEqual(result["status"], "failed")

	def test_bad_expression_fails(self):
		flow_run = FakeFlowRun()
		config = {"expression": "__import__('os')", "on_true": "t", "on_false": "f"}
		self.assertEqual(flow_engine._exec_condition(flow_run, {}, config, {})["status"], "failed")


class TestExecTransform(unittest.TestCase):
	"""GW-34: graph_ir.schema.json's ``TransformNode.config`` requires exactly
	``op``/``input`` (``additionalProperties: false``) -- the old
	``transformations: [{source_field, target_field, operation}]`` shape
	tested here previously was never a schema-valid config a Flow Definition
	could actually be saved with, so ``_exec_transform`` silently ignoring a
	real ``op``/``input`` config was the bug (see
	huf.ai.flow.tests.test_flow_gw34_node_type_gap for the fuller regression
	suite). These tests now pin the schema's own shape, dispatched through
	``huf.ai.graph.transforms.run_transform`` -- the same function
	``procedure_runtime`` uses for the Procedure profile's ``transform`` node.
	"""

	def test_select_operation(self):
		flow_run = FakeFlowRun()
		_ctx(flow_run, rows=[{"name": "Ada", "age": 30}])
		config = {"op": "select", "input": {"rows": {"$from": "input.rows"}, "fields": ["name"]}}
		result = flow_engine._exec_transform(flow_run, {}, config, {})
		self.assertEqual(result["status"], "success")
		self.assertEqual(result["result"], [{"name": "Ada"}])

	def test_coalesce_operation_resolves_nested_reference(self):
		flow_run = FakeFlowRun()
		_ctx(flow_run, user={"name": "Ada"})
		config = {"op": "coalesce", "input": {"values": [None, {"$from": "input.user.name"}]}}
		result = flow_engine._exec_transform(flow_run, {}, config, {})
		self.assertEqual(result["status"], "success")
		self.assertEqual(result["result"], "Ada")

	def test_unknown_op_fails_closed(self):
		flow_run = FakeFlowRun()
		_ctx(flow_run)
		config = {"op": "not_a_real_op", "input": {}}
		result = flow_engine._exec_transform(flow_run, {}, config, {})
		self.assertEqual(result["status"], "failed")

	def test_legacy_transformations_shape_no_longer_applies(self):
		"""``config.transformations`` predates the shared graph-IR schema and can
		never be saved through FlowDefinition.validate() any more -- it has no
		``op``, so run_transform fails closed rather than silently no-op'ing."""
		flow_run = FakeFlowRun()
		_ctx(flow_run, source_field="hello")
		config = {"transformations": [{"source_field": "source_field", "target_field": "dest", "operation": "copy"}]}
		result = flow_engine._exec_transform(flow_run, {}, config, {})
		self.assertEqual(result["status"], "failed")


def _flow_ctx(defn, flow_run):
	"""A FlowRunContext over a pinned copy of ``defn`` (what run_flow builds)."""
	from huf.ai.graph.executor import PinnedVersion

	return flow_engine._build_run_context(flow_run, PinnedVersion.pin(defn))


def _drive(defn, flow_run):
	"""Run a schema-shaped graph through the real ``_execute_loop``."""
	run_ctx = _flow_ctx(defn, flow_run)
	nodes_map = {n["id"]: n for n in defn["nodes"]}
	with patch.object(flow_engine, "_publish_flow_event"), patch.object(flow_engine, "commit_if_background"):
		flow_engine._execute_loop(flow_run, nodes_map, run_ctx.edges, run_ctx)
	return run_ctx


def _out(node_id, value=1):
	return {"id": node_id, "type": "output", "config": {"value": value}}


class TestExecForeach(unittest.TestCase):
	def _defn(self, items_ref=None, **loop_cfg):
		cfg = {
			"items": items_ref or {"$from": "input.items"},
			"body": ["body"],
			"max_iterations": 10,
			"on_item_error": "fail",
			"collect": {"$from": "body"},
		}
		cfg.update(loop_cfg)
		return {
			"entry": "loop",
			"nodes": [
				{"id": "loop", "type": "foreach", "config": cfg, "next": "finish"},
				{
					"id": "body",
					"type": "transform",
					"config": {"op": "upper", "input": {"text": {"$from": "foreach.item"}}},
				},
				_out("finish", {"$from": "loop"}),
			],
			"contract": {"limits": {"max_foreach_iterations": 200}},
		}

	def test_body_runs_per_item_collects_and_done_edge_continues(self):
		flow_run = FakeFlowRun(current_node_id="loop", max_hops=10)
		_ctx(flow_run, items=["a", "b", "c"])
		run_ctx = _drive(self._defn(), flow_run)
		self.assertEqual(flow_run.status, "Success")
		self.assertEqual(run_ctx.context.node_outputs["loop"], ["A", "B", "C"])
		self.assertEqual(run_ctx.context.node_outputs["finish"], ["A", "B", "C"])

	def test_item_var_and_index_var_are_bound_during_body_and_restored(self):
		defn = self._defn(item_var="row", index_var="i")
		defn["nodes"][1]["config"]["input"] = {"text": {"$from": "input.row"}}
		flow_run = FakeFlowRun(current_node_id="loop", max_hops=10)
		_ctx(flow_run, items=["x", "y"])
		run_ctx = _drive(defn, flow_run)
		self.assertEqual(run_ctx.context.node_outputs["loop"], ["X", "Y"])
		self.assertNotIn("row", run_ctx.context.data)
		self.assertNotIn("i", run_ctx.context.data)

	def test_on_item_error_fail_fails_the_run(self):
		flow_run = FakeFlowRun(current_node_id="loop", max_hops=10)
		_ctx(flow_run, items=["a", {"x": 1}])  # upper() of an object fails
		_drive(self._defn(), flow_run)
		self.assertEqual(flow_run.status, "Failed")
		self.assertIn("item 2", flow_run.last_error)

	def test_on_item_error_skip_drops_the_item_and_continues(self):
		flow_run = FakeFlowRun(current_node_id="loop", max_hops=10)
		_ctx(flow_run, items=["a", {"x": 1}, "c"])
		run_ctx = _drive(self._defn(on_item_error="skip"), flow_run)
		self.assertEqual(flow_run.status, "Success")
		self.assertEqual(run_ctx.context.node_outputs["loop"], ["A", "C"])

	def test_more_items_than_max_iterations_fails(self):
		flow_run = FakeFlowRun(current_node_id="loop", max_hops=10)
		_ctx(flow_run, items=[1, 2, 3])
		_drive(self._defn(max_iterations=2), flow_run)
		self.assertEqual(flow_run.status, "Failed")
		self.assertIn("its limit is 2", flow_run.last_error)

	def test_non_list_items_fails(self):
		flow_run = FakeFlowRun(current_node_id="loop", max_hops=10)
		_ctx(flow_run, items="nope")
		_drive(self._defn(), flow_run)
		self.assertEqual(flow_run.status, "Failed")


class TestExecTriggerWebhook(unittest.TestCase):
	def test_passes_through_existing_context(self):
		flow_run = FakeFlowRun()
		payload = _ctx(flow_run, foo="bar")
		result = flow_engine._exec_trigger_webhook(flow_run, {}, {}, {})
		self.assertEqual(result["status"], "success")
		self.assertEqual(result["output"], payload)


# ---------------------------------------------------------------------------
# tool.call: exercised through the real executor with frappe surface mocked
# ---------------------------------------------------------------------------

class TestChatTriggersRun(unittest.TestCase):
	"""A gateway-routed run starts at the chat trigger node, so the engine must be able to execute it."""

	def test_chat_triggers_have_a_passthrough_executor(self):
		for node_type in ("trigger.gateway", "trigger.whatsapp", "trigger.telegram"):
			flow_run = FakeFlowRun()
			payload = _ctx(flow_run, text="hi")
			result = flow_engine._execute_node(flow_run, {"id": "t", "type": node_type, "config": {}}, {})
			self.assertEqual(result["status"], "success", node_type)
			self.assertEqual(result["output"], payload, node_type)



class TestExecToolCallInterpolation(unittest.TestCase):
	"""tool.call's arg substitution -- one of the four ``{{...}}``
	implementations GT-04 found (F-2), and the one this defect is named for:
	unlike `_interpolate_string`, it only did a flat ``ctx.get(var_name)``
	lookup and could not resolve dotted paths. These tests drive the real
	`_exec_tool_call` executor with the frappe surface it touches
	(db.get_value, get_doc, execute_tool) mocked, and assert on the args
	actually passed to the tool -- an observable outcome that should hold
	across the F-2 fix, now expressed through the single
	``{"$from": ...}`` reference form instead of ``{{...}}``.
	"""

	def _run_tool_call(self, ctx, args, tool_result=None):
		flow_run = FakeFlowRun()
		_ctx(flow_run, **ctx)
		config = {"tool_id": "demo_tool", "input": args}
		captured = {}

		def fake_execute(tool_name, call_args):
			captured["tool_name"] = tool_name
			captured["args"] = call_args
			return tool_result or {"success": True, "result": "ok"}

		fake_run_doc = MagicMock()
		fake_tool_call_doc = MagicMock()

		with patch.object(flow_engine, "frappe") as fake_frappe, \
			_no_mcp(), \
			patch.object(flow_engine, "execute_tool", side_effect=fake_execute), \
			patch.object(flow_engine, "_create_flow_agent_run", return_value=fake_run_doc):
			fake_frappe.get_doc.return_value = fake_tool_call_doc
			flow_engine._exec_tool_call(flow_run, {"id": "n1"}, config, {})

		return captured

	def test_flat_key_reference_resolves(self):
		captured = self._run_tool_call({"name": "Ada"}, {"greeting": {"$from": "input.name"}})
		self.assertEqual(captured["args"]["greeting"], "Ada")

	def test_dotted_path_reference_resolves(self):
		"""F-2: tool.call's arg substitution used to only do a flat
		ctx.get(var_name) lookup and could not resolve dotted paths, unlike
		`_interpolate_string` elsewhere in the engine. Now every node type
		resolves ``{"$from": ...}`` through the same `GraphContext.resolve`,
		so a nested path works here exactly as it does everywhere else.
		"""
		captured = self._run_tool_call(
			{"user": {"email": "a@b.com"}},
			{"to": {"$from": "context.user.email"}},
		)
		self.assertEqual(captured["args"]["to"], "a@b.com")

	def test_template_value_resolves(self):
		captured = self._run_tool_call(
			{"name": "Ada"},
			{"text": {"$template": "Hi {n}", "vars": {"n": {"$from": "input.name"}}}},
		)
		self.assertEqual(captured["args"]["text"], "Hi Ada")

	def test_web_request_step_limit_becomes_request_timeout(self):
		flow_run = FakeFlowRun()
		_ctx(flow_run)
		captured = {}

		def fake_execute(tool_name, call_args):
			captured["args"] = call_args
			return {"success": True, "result": "ok"}

		with patch.object(flow_engine, "frappe") as fake_frappe, \
			_no_mcp(), \
			patch.object(flow_engine, "execute_tool", side_effect=fake_execute), \
			patch.object(flow_engine, "_create_flow_agent_run", return_value=MagicMock()):
			fake_frappe.get_doc.return_value = MagicMock()
			flow_engine._exec_tool_call(
				flow_run, {"id": "n1"}, {"tool_id": "http_request", "input": {"url": "https://x.example"}, "timeout_ms": 12000}, {}
			)
		self.assertEqual(captured["args"]["timeout_seconds"], 12.0)

	def test_legacy_names_are_not_read(self):
		flow_run = FakeFlowRun()
		with patch.object(flow_engine, "execute_tool") as ex:
			result = flow_engine._exec_tool_call(
				flow_run, {"id": "n1"}, {"tool_name": "demo", "args": {"a": 1}}, {}
			)
		self.assertEqual(result["status"], "failed")
		ex.assert_not_called()


class TestNormalizeToolResult(unittest.TestCase):
	def test_plain_success_envelope(self):
		out = flow_engine.normalize_tool_result({"success": True, "result": {"id": 1}})
		self.assertTrue(out["success"])
		self.assertEqual(out["result"], {"id": 1})

	def test_json_string_with_success_false_is_a_failure(self):
		raw = {"success": True, "result": json.dumps({"success": False, "error": "no such channel"})}
		out = flow_engine.normalize_tool_result(raw)
		self.assertFalse(out["success"])
		self.assertEqual(out["error"], "no such channel")

	def test_json_string_with_error_key_is_a_failure(self):
		raw = {"success": True, "result": '{"error": "quota exceeded"}'}
		out = flow_engine.normalize_tool_result(raw)
		self.assertFalse(out["success"])
		self.assertIn("quota", out["error"])

	def test_dict_result_with_error_key_is_a_failure(self):
		out = flow_engine.normalize_tool_result({"success": True, "result": {"error": "bad"}})
		self.assertFalse(out["success"])

	def test_json_string_success_is_parsed_for_downstream_fields(self):
		out = flow_engine.normalize_tool_result({"success": True, "result": '{"success": true, "id": 7}'})
		self.assertTrue(out["success"])
		self.assertEqual(out["result"]["id"], 7)

	def test_envelope_failure_keeps_its_error(self):
		out = flow_engine.normalize_tool_result({"success": False, "error": "boom"})
		self.assertFalse(out["success"])
		self.assertEqual(out["error"], "boom")

	def test_non_json_text_result_is_success(self):
		out = flow_engine.normalize_tool_result({"success": True, "result": "sent"})
		self.assertTrue(out["success"])
		self.assertEqual(out["result"], "sent")

	def test_unwrapped_value(self):
		self.assertTrue(flow_engine.normalize_tool_result("hello")["success"])
		self.assertFalse(flow_engine.normalize_tool_result({"success": False})["success"])


class TestExecToolCallFailureDetection(unittest.TestCase):
	def _run(self, tool_return):
		flow_run = FakeFlowRun()
		with patch.object(flow_engine, "frappe"), _no_mcp(), \
			patch.object(flow_engine, "commit_if_background"), \
			patch.object(flow_engine, "execute_tool", return_value=tool_return), \
			patch.object(flow_engine, "_create_flow_agent_run", return_value=MagicMock()):
			return flow_engine._exec_tool_call(flow_run, {"id": "n1"}, {"tool_id": "t", "input": {}}, {})

	def test_tool_json_failure_marks_node_failed(self):
		out = self._run({"success": True, "result": '{"success": false, "error": "denied"}'})
		self.assertEqual(out["status"], "failed")
		self.assertEqual(out["error"], "denied")

	def test_clean_result_stays_green_and_is_the_node_output(self):
		out = self._run({"success": True, "result": '{"ok": 1}'})
		self.assertEqual(out["status"], "success")
		self.assertEqual(out["result"], {"ok": 1})


# ---------------------------------------------------------------------------
# approve_flow_run: its own inline routing + meta.outcome convention
# ---------------------------------------------------------------------------


class TestApproveFlowRunRouting(unittest.TestCase):
	"""approve_flow_run routes by the human.approval node's own ``approve_next`` /
	``reject_next`` (outcome-labelled edges), checks the approver first (fail closed,
	for both decisions), and stores the decision record as the node's output.
	"""

	def _defn(self, approve_next="next_ok", reject_next="next_no", **cfg):
		config = {"message": "ok?", "approve_next": approve_next, "reject_next": reject_next}
		config.update(cfg)
		return {
			"id": "test-flow",
			"entry": "approval",
			"nodes": [
				{"id": "approval", "type": "human.approval", "config": config},
				_out("next_ok"),
				_out("next_no"),
			],
		}

	def _invoke(self, flow_run, defn, decision, comment=None, roles=None, session_user="someone@example.com"):
		fake_frappe = MagicMock()
		fake_frappe.session.user = session_user
		fake_frappe.get_roles.return_value = roles or []
		fake_frappe.get_doc.return_value = flow_run

		def fake_throw(msg, exc=Exception):
			raise exc(msg)

		fake_frappe.throw.side_effect = fake_throw
		fake_frappe.PermissionError = PermissionError
		fake_frappe._ = lambda s: s

		with patch.object(flow_engine, "frappe", fake_frappe), \
			patch.object(flow_engine, "_", lambda s: s), \
			patch.object(flow_engine, "load_definition", return_value=defn), \
			patch.object(flow_engine, "run_flow") as fake_run_flow, \
			patch.object(flow_engine, "commit_if_background"), \
			patch.object(flow_engine, "_clear_flow_notifications"), \
			patch.object(flow_engine, "_publish_flow_event"), \
			patch.object(flow_engine.flow_hooks, "notify_failure"):
			flow_engine.approve_flow_run(flow_run.name, decision, comment)
		return fake_run_flow

	def _waiting_flow_run(self, approver_type="role", approver_role="System Manager", approver_users=None):
		flow_run = FakeFlowRun(
			status="Waiting Approval",
			current_node_id="approval",
			waiting=json.dumps(
				{
					"type": "approval",
					"node_id": "approval",
					"approver_type": approver_type,
					"approver_role": approver_role,
					"approver_users": approver_users or [],
				}
			),
		)
		_ctx(flow_run)
		return flow_run

	def test_approved_routes_to_approve_next(self):
		flow_run = self._waiting_flow_run()
		fake_run_flow = self._invoke(flow_run, self._defn(), "approved", roles=["System Manager"])
		self.assertEqual(flow_run.current_node_id, "next_ok")
		self.assertEqual(flow_run.status, "Running")
		fake_run_flow.assert_called_once_with(flow_run.name)

	def test_rejected_routes_to_reject_next(self):
		flow_run = self._waiting_flow_run()
		self._invoke(flow_run, self._defn(), "rejected", comment="not good", roles=["System Manager"])
		self.assertEqual(flow_run.current_node_id, "next_no")
		self.assertEqual(flow_run.status, "Running")

	def test_invalid_decision_is_refused(self):
		flow_run = self._waiting_flow_run()
		with self.assertRaises(Exception):
			self._invoke(flow_run, self._defn(), "maybe", roles=["System Manager"])
		self.assertEqual(flow_run.status, "Waiting Approval")

	def test_decision_record_is_the_approval_nodes_output_and_survives_a_reload(self):
		flow_run = self._waiting_flow_run()
		self._invoke(flow_run, self._defn(), "approved", comment="lgtm", roles=["System Manager"], session_user="boss")
		stored = json.loads(flow_run.context_json)[flow_engine.NODE_OUTPUTS_KEY]["approval"]
		self.assertEqual(stored["decision"], "approved")
		self.assertEqual(stored["comment"], "lgtm")
		self.assertEqual(stored["decided_by"], "boss")
		# the next run_flow builds a fresh context from context_json: the output is still addressable
		reloaded = flow_engine.load_context(flow_run.context_json)
		self.assertEqual(reloaded.resolve({"$from": "approval.decision"}), "approved")
		self.assertNotIn(flow_engine.NODE_OUTPUTS_KEY, reloaded.data)

	def test_hop_count_increments_on_routed_approval(self):
		flow_run = self._waiting_flow_run()
		flow_run.hop_count = 3
		self._invoke(flow_run, self._defn(), "approved", roles=["System Manager"])
		self.assertEqual(flow_run.hop_count, 4)

	def test_not_waiting_approval_raises(self):
		flow_run = FakeFlowRun(status="Running")
		with self.assertRaises(Exception):
			self._invoke(flow_run, self._defn(), "approved")

	def test_role_permission_denied_blocks_routing_for_approve_and_reject(self):
		for decision in ("approved", "rejected"):
			flow_run = self._waiting_flow_run(approver_type="role", approver_role="Flow Approver")
			with self.assertRaises(PermissionError):
				self._invoke(flow_run, self._defn(), decision, roles=["Some Other Role"])
			# Permission is checked BEFORE any routing/context mutation happens.
			self.assertEqual(flow_run.status, "Waiting Approval")
			self.assertEqual(flow_run.context_json, "{}")

	def test_no_declared_approver_only_system_manager_may_decide(self):
		for decision in ("approved", "rejected"):
			flow_run = self._waiting_flow_run(approver_type=None, approver_role=None)
			with self.assertRaises(PermissionError):
				self._invoke(flow_run, self._defn(), decision, roles=["Flow Approver", "Desk User"])
			self.assertEqual(flow_run.status, "Waiting Approval")
		flow_run = self._waiting_flow_run(approver_type=None, approver_role=None)
		self._invoke(flow_run, self._defn(), "rejected", roles=["System Manager"])
		self.assertEqual(flow_run.current_node_id, "next_no")

	def test_resume_flow_run_cannot_bypass_the_approver_check(self):
		flow_run = self._waiting_flow_run()
		fake_frappe = MagicMock()
		fake_frappe.get_doc.return_value = flow_run
		fake_frappe.PermissionError = PermissionError
		fake_frappe.throw.side_effect = lambda msg, exc=Exception: (_ for _ in ()).throw(exc(msg))
		with patch.object(flow_engine, "frappe", fake_frappe), patch.object(flow_engine, "_", lambda s: s):
			with self.assertRaises(PermissionError):
				flow_engine.resume_flow_run(flow_run.name)
		self.assertEqual(flow_run.status, "Waiting Approval")


class TestCheckApprover(unittest.TestCase):
	"""Pure fail-closed approver policy (contract section 3, human.approval)."""

	def test_role_requires_that_role(self):
		w = {"approver_type": "role", "approver_role": "Accounts Manager"}
		self.assertIsNone(flow_engine.check_approver(w, "u", ["Accounts Manager"]))
		self.assertIsNotNone(flow_engine.check_approver(w, "u", ["System Manager"]))

	def test_user_requires_listed_user(self):
		w = {"approver_type": "user", "approver_users": ["a@x.com", "b@x.com"]}
		self.assertIsNone(flow_engine.check_approver(w, "b@x.com", []))
		self.assertIsNotNone(flow_engine.check_approver(w, "c@x.com", ["System Manager"]))

	def test_absent_type_is_system_manager_only(self):
		self.assertIsNone(flow_engine.check_approver({}, "u", ["System Manager"]))
		self.assertIsNotNone(flow_engine.check_approver({}, "u", ["Desk User"]))
		self.assertIsNotNone(flow_engine.check_approver(None, "u", []))

	def test_role_type_with_missing_role_fails_closed(self):
		self.assertIsNotNone(flow_engine.check_approver({"approver_type": "role"}, "u", ["Desk User"]))

	def test_user_type_with_empty_list_fails_closed(self):
		w = {"approver_type": "user", "approver_users": []}
		self.assertIsNotNone(flow_engine.check_approver(w, "anyone", ["Desk User"]))
		self.assertIsNone(flow_engine.check_approver(w, "anyone", ["System Manager"]))

	def test_unknown_type_is_system_manager_only(self):
		w = {"approver_type": "anyone"}
		self.assertIsNotNone(flow_engine.check_approver(w, "u", ["Desk User"]))

	def test_legacy_approval_type_key_is_ignored(self):
		w = {"approval_type": "user", "approver_users": ["a@x.com"]}
		self.assertIsNotNone(flow_engine.check_approver(w, "a@x.com", ["Desk User"]))


class TestApprovalTimeout(unittest.TestCase):
	def test_expired_only_after_deadline(self):
		from datetime import datetime

		w = {"timeout_at": "2026-01-01T10:00:00"}
		self.assertFalse(flow_engine.approval_expired(w, datetime(2026, 1, 1, 9, 59)))
		self.assertTrue(flow_engine.approval_expired(w, datetime(2026, 1, 1, 10, 0)))
		self.assertFalse(flow_engine.approval_expired({}, datetime(2030, 1, 1)))


class TestExecHumanApproval(unittest.TestCase):
	def test_pause_records_schema_fields_and_node_outputs(self):
		flow_run = FakeFlowRun(current_node_id="approval", status="Running")
		_ctx(flow_run, foo="bar")
		node = {"id": "approval", "type": "human.approval"}
		config = {
			"message": "Approve?",
			"approve_next": "a",
			"reject_next": "r",
			"timeout_next": "t",
			"timeout_ms": 1000,
			"approver_type": "user",
			"approver_users": ["a@x.com"],
		}
		ctx = GraphContext({"foo": "bar"})
		ctx.record_output("earlier", {"v": 1})
		run_ctx = flow_engine.FlowRunContext({}, flow_run=flow_run, context=ctx)
		import datetime as _dt
		with patch.object(flow_engine, "commit_if_background"), \
			patch.object(flow_engine, "now_datetime", lambda: _dt.datetime(2026, 1, 1)), \
			patch.object(flow_engine, "_send_approval_notifications"), \
			patch.object(flow_engine.flow_hooks, "notify_approvers"):
			out = flow_engine._exec_human_approval(flow_run, node, config, run_ctx)
		self.assertEqual(out, {"status": "waiting_approval"})
		self.assertEqual(flow_run.status, "Waiting Approval")
		waiting = json.loads(flow_run.waiting)
		self.assertEqual(waiting["approver_type"], "user")
		self.assertEqual(waiting["approver_users"], ["a@x.com"])
		self.assertEqual(waiting["timeout_next"], "t")
		self.assertEqual(waiting["message"], "Approve?")
		self.assertTrue(waiting["timeout_at"])
		for legacy in ("approval_type", "store_decision_in_context", "title", "instructions"):
			self.assertNotIn(legacy, waiting)
		self.assertEqual(json.loads(flow_run.context_json)[flow_engine.NODE_OUTPUTS_KEY], {"earlier": {"v": 1}})


# ---------------------------------------------------------------------------
# Hop limit trip + end-node completion, via the real _execute_loop
# ---------------------------------------------------------------------------


class TestHopLimitAndEndCompletion(unittest.TestCase):
	def test_hop_limit_trip_fails_the_run(self):
		flow_run = FakeFlowRun(current_node_id="n1", hop_count=5, max_hops=5)
		_ctx(flow_run)
		nodes_map = {"n1": _out("n1")}
		with patch.object(flow_engine, "_publish_flow_event"):
			flow_engine._execute_loop(flow_run, nodes_map, [], {})
		self.assertEqual(flow_run.status, "Failed")
		self.assertIn("took more than 5 steps", flow_run.last_error)

	def test_end_node_completes_run_successfully(self):
		flow_run = FakeFlowRun(current_node_id="n1", hop_count=0, max_hops=10)
		_ctx(flow_run)
		nodes_map = {"n1": _out("n1")}
		with patch.object(flow_engine, "_publish_flow_event"):
			flow_engine._execute_loop(flow_run, nodes_map, [], {})
		self.assertEqual(flow_run.status, "Success")
		self.assertIsNotNone(flow_run.completed_at)

	def test_unmatched_node_fails_gracefully(self):
		flow_run = FakeFlowRun(current_node_id="missing", hop_count=0, max_hops=10)
		_ctx(flow_run)
		with patch.object(flow_engine, "_publish_flow_event"):
			flow_engine._execute_loop(flow_run, {}, [], {})
		self.assertEqual(flow_run.status, "Failed")
		self.assertIn("no longer exists", flow_run.last_error)

	def test_normal_mode_advances_via_evaluate_edges_between_nodes(self):
		flow_run = FakeFlowRun(current_node_id="n1", hop_count=0, max_hops=10, mode="Normal")
		_ctx(flow_run)
		nodes_map = {
			"n1": _out("n1"),
		}
		edges = []  # end node completes before edges are even consulted
		with patch.object(flow_engine, "_publish_flow_event"):
			flow_engine._execute_loop(flow_run, nodes_map, edges, {})
		self.assertEqual(flow_run.status, "Success")

	def test_no_outgoing_edges_from_non_end_node_completes_run(self):
		flow_run = FakeFlowRun(current_node_id="n1", hop_count=0, max_hops=10, mode="Normal")
		_ctx(flow_run)
		nodes_map = {"n1": {"id": "n1", "type": "transform", "config": {"op": "coalesce", "input": {"values": []}}}}
		with patch.object(flow_engine, "_publish_flow_event"):
			flow_engine._execute_loop(flow_run, nodes_map, [], {})
		self.assertEqual(flow_run.status, "Success")

	def test_hop_count_increments_each_step(self):
		flow_run = FakeFlowRun(current_node_id="n1", hop_count=0, max_hops=10, mode="Normal")
		_ctx(flow_run)
		nodes_map = {
			"n1": {"id": "n1", "type": "transform", "config": {"op": "coalesce", "input": {"values": []}}, "next": "n2"},
			"n2": _out("n2"),
		}
		edges = flow_engine.edges_from_nodes(list(nodes_map.values()))
		with patch.object(flow_engine, "_publish_flow_event"):
			flow_engine._execute_loop(flow_run, nodes_map, edges, {})
		self.assertEqual(flow_run.hop_count, 2)
		self.assertEqual(flow_run.status, "Success")


# ---------------------------------------------------------------------------
# GW-02: a failed node with no successor must fail the run, not silently
# report success.
# ---------------------------------------------------------------------------


class TestFailedNodeWithNoSuccessorFailsRun(unittest.TestCase):
	"""GW-02 regression: ``huf.ai.graph.executor.GraphExecutor.run`` used to
	read ``next_node_id is None`` as "run boundary reached, complete the run
	successfully" no matter what the node's own outcome was. Router.resolve's
	fail-closed guard (I7) only fires when Flow's own ``default_resolver`` is
	NOT supplied -- but flow/engine.py always supplies one
	(``_build_router``'s ``default_resolver``), so a failed tool.call node
	with no ``next``/``on_error`` pointer and no matching edge silently
	completed the whole Flow Run as "Success". The fix enforces fail-closed
	centrally in ``GraphExecutor.run``, independent of which resolver
	produced the (missing) next node id.
	"""

	def _run_failing_tool_call(self, on_error=None):
		flow_run = FakeFlowRun(current_node_id="n1", hop_count=0, max_hops=10, mode="Normal")
		_ctx(flow_run)
		node = {"id": "n1", "type": "tool.call", "config": {"tool_id": "demo_tool", "input": {}}}
		if on_error:
			node["on_error"] = on_error
		nodes_map = {"n1": node}
		if on_error:
			nodes_map[on_error] = _out(on_error)

		def fake_execute_tool(tool_name, call_args):
			return {"success": False, "error": "boom"}

		fake_run_doc = MagicMock()
		fake_tool_call_doc = MagicMock()

		with patch.object(flow_engine, "frappe") as fake_frappe, _no_mcp(), \
			patch.object(flow_engine, "execute_tool", side_effect=fake_execute_tool), \
			patch.object(flow_engine, "_create_flow_agent_run", return_value=fake_run_doc), \
			patch.object(flow_engine, "_publish_flow_event"), \
			patch.object(flow_engine, "commit_if_background"), \
			patch.object(flow_engine.flow_hooks, "notify_failure"):
			fake_frappe.get_doc.return_value = fake_tool_call_doc
			flow_engine._execute_loop(flow_run, nodes_map, flow_engine.edges_from_nodes(list(nodes_map.values())), {})

		return flow_run

	def test_failed_node_no_successor_fails_the_run(self):
		"""A single engineered-to-fail node with no on_error edge must report
		Flow Run status Failed, not Success."""
		flow_run = self._run_failing_tool_call(on_error=None)
		self.assertEqual(flow_run.status, "Failed")
		self.assertIn("boom", flow_run.last_error or "")

	def test_failed_node_with_on_error_edge_still_succeeds(self):
		"""Regression guard: a failing node that DOES declare a matching
		on_error successor must still be able to complete the run
		successfully by routing to the error-handling node -- the fail-closed
		fix must not break existing on_error routing."""
		flow_run = self._run_failing_tool_call(on_error="recover")
		self.assertEqual(flow_run.status, "Success")


# ---------------------------------------------------------------------------
# Known defects (F-1..F-4): intended-behaviour acceptance tests for T-22
# ---------------------------------------------------------------------------


class TestKnownDefects(unittest.TestCase):
	def test_resumed_run_uses_definition_pinned_at_start_not_current(self):
		"""F-1 (flow_definition.py:33, flow/engine.py:141): flow_version
		auto-increments on every FlowDefinition save, and `load_definition` /
		`run_flow` always re-fetch the CURRENT definition rather than the one
		recorded on the Flow Run at creation time (`flow_run.flow_version`).
		Intended behaviour: a resumed run continues executing against the
		definition version it started with, even if the definition has since
		been edited and re-saved.
		"""
		flow_run = FakeFlowRun(
			current_node_id="n1",
			flow_version=1,
			status="Waiting User",
			hop_count=0,
			max_hops=10,
		)
		_ctx(flow_run)

		# Two definition "versions": v1 routes n1 -> old_next, v2 (simulating a
		# later edit + auto-bumped version) routes n1 -> new_next instead.
		defn_v1 = {
			"id": "test-flow",
			"version": 1,
			"entry": "n1",
			"nodes": [_out("n1")],
			"edges": [],
			"settings": {},
		}
		defn_v2 = {
			"id": "test-flow",
			"version": 2,
			"entry": "n1",
			# Deliberately a node shape that cannot complete successfully (a
			# condition node with no expression configured), so this test can
			# tell v1-vs-v2 execution apart by outcome rather than by node type.
			"nodes": [{"id": "n1", "type": "condition", "config": {}}],
			"edges": [],
			"settings": {},
		}
		versions = {1: defn_v1, 2: defn_v2}
		# Simulate the definition doc having since been edited and auto-bumped
		# to v2 (flow_definition.py:33's before_save) -- independent of what
		# version this particular run was pinned to at start.
		current_version_on_disk = {"v": 2}

		def fake_load_definition(flow_id):
			# This mirrors the ACTUAL (buggy) behaviour: flow/engine.py:141
			# always re-fetches whatever is current on disk, ignoring
			# flow_run.flow_version entirely. A fixed implementation would key
			# off `flow_run.flow_version` (== 1) here instead.
			return versions[current_version_on_disk["v"]]

		fake_frappe = MagicMock()
		fake_frappe.get_doc.return_value = flow_run

		with patch.object(flow_engine, "frappe", fake_frappe), \
			patch.object(flow_engine, "load_definition", side_effect=fake_load_definition), \
			patch.object(flow_engine, "commit_if_background"):
			# Simulate the definition being edited (and auto-version-bumped) to v2
			# WHILE this run is paused waiting on user input.
			flow_engine.resume_flow_run(flow_run.name)

		# Intended: the node type actually executed should be the one from the
		# PINNED version (v1's output node), so the run should have completed via the
		# end node, not been left failing against a v2-shaped condition node.
		self.assertEqual(flow_run.status, "Success")

	def test_loop_over_more_than_max_hops_items_still_completes(self):
		"""F-3 (flow/engine.py ~1111, DEFAULT_MAX_HOPS ~34): each loop iteration
		burns one hop against the run's overall hop budget, via the same
		`hop_count` the outer `_execute_loop` checks. A loop with more items
		than `max_hops` can therefore never finish. Intended behaviour: loop
		iteration should not be constrained by the run's hop budget, so a
		150-item loop over a run with the default 100-hop budget still
		completes.
		"""
		items = list(range(150))
		flow_run = FakeFlowRun(current_node_id="loop", hop_count=0, max_hops=flow_engine.DEFAULT_MAX_HOPS)
		_ctx(flow_run, items=items)
		defn = {
			"entry": "loop",
			"nodes": [
				{
					"id": "loop",
					"type": "foreach",
					"config": {
						"items": {"$from": "input.items"},
						"body": ["body"],
						"max_iterations": 1000,
						"on_item_error": "fail",
						"collect": {"$from": "body"},
					},
					"next": "finish",
				},
				{"id": "body", "type": "transform", "config": {"op": "coalesce", "input": {"values": [1]}}},
				_out("finish"),
			],
			"contract": {"limits": {"max_foreach_iterations": 1000}},
		}
		_drive(defn, flow_run)
		self.assertEqual(flow_run.status, "Success")

	def test_concurrent_resumes_do_not_double_advance_the_cursor(self):
		"""F-4: run_flow takes no lock, so two concurrent resumes of the same
		paused run can both read the same `current_node_id` and both advance
		it, effectively double-executing a step. Intended behaviour: only one
		of two concurrent `run_flow` calls against the same run should be able
		to advance the cursor past a given node in a single logical step; the
		other should observe (or be serialized behind) the first one's move.

		Modeled here without real threads: two "concurrent" callers both
		snapshot current_node_id before either writes it back, then both
		attempt to move forward. Intended behaviour requires some form of
		mutual exclusion (e.g. an optimistic version check or a row lock) that
		makes the second writer detect the conflict instead of silently
		clobbering / duplicating the first writer's advance.
		"""
		flow_run = FakeFlowRun(current_node_id="n1", hop_count=0, max_hops=10)
		_ctx(flow_run)

		# Two callers race to read current_node_id...
		snapshot_a = flow_run.current_node_id
		snapshot_b = flow_run.current_node_id
		self.assertEqual(snapshot_a, snapshot_b)

		advanced_by = []
		original_db_set = flow_run.db_set

		def tracking_db_set(field, value=None):
			updates = field if isinstance(field, dict) else {field: value}
			if "current_node_id" in updates:
				advanced_by.append(updates["current_node_id"])
			original_db_set(field, value)

		flow_run.db_set = tracking_db_set

		nodes_map = {
			"n1": {"id": "n1", "type": "transform", "config": {"op": "coalesce", "input": {"values": []}}, "next": "n2"},
			"n2": _out("n2"),
		}
		edges = flow_engine.edges_from_nodes(list(nodes_map.values()))

		# ...and both drive the loop forward from the same starting snapshot.
		with patch.object(flow_engine, "_publish_flow_event"):
			flow_engine._execute_loop(flow_run, nodes_map, edges, {})
			flow_run.current_node_id = snapshot_a  # simulate caller B replaying its stale read
			flow_engine._execute_loop(flow_run, nodes_map, edges, {})

		# Intended: the cursor must not be advanced from the same starting node
		# twice -- a real lock/optimistic-concurrency check should have made
		# the second call a no-op (or raise), so "n2" should appear at most once.
		self.assertEqual(advanced_by.count("n2"), 1)


if __name__ == "__main__":
	unittest.main()
