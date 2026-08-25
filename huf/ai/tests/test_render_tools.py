# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Tests for huf.ai.tools.render_tools — the render_mermaid/render_chart tool
handlers that template structured JSON into the existing Mermaid/chart
<artifact> markup, and for the agent_integration.py prompt-instruction
selection that swaps in the short "call the tool" instructions when
render_mermaid/render_chart are attached to an agent.

huf.ai.tools.render_tools has no frappe dependency (pure string/structural
templating), so tests 1-6 run as plain unittest with no bench/site required.
Test 7 exercises huf.ai.agent_integration, which imports frappe at module
level and therefore does require a Frappe site to even import - see the
docstring on TestPromptInstructionSelection for how that is handled.

Run with:
	bench --site <site> run-tests --app huf --module huf.ai.tests.test_render_tools
"""

import re
import unittest
from unittest import mock

from huf.ai.tools.render_tools import handle_render_chart, handle_render_mermaid


class TestRenderMermaid(unittest.TestCase):
	def test_simple_two_node_graph_produces_valid_dsl_in_artifact_tag(self):
		result = handle_render_mermaid(
			diagram_type="graph TD",
			nodes=[{"id": "a", "label": "Start"}, {"id": "b", "label": "End"}],
			edges=[{"from": "a", "to": "b", "label": "next"}],
			title="My Flow",
		)

		self.assertTrue(result.startswith('<artifact type="mermaid" title="My Flow">'))
		self.assertTrue(result.endswith("</artifact>"))

		body = result[len('<artifact type="mermaid" title="My Flow">\n') : -len("\n</artifact>")]
		lines = body.splitlines()

		self.assertEqual(lines[0], "graph TD")
		self.assertIn("a[Start]", body)
		self.assertIn("b[End]", body)
		self.assertIn("a -->|next| b", body)

		# Balanced brackets, no empty node ids/labels.
		self.assertEqual(body.count("["), body.count("]"))
		self.assertNotIn("[]", body.replace(" ", ""))
		self.assertNotIn("|| ", body)  # no empty pipe segment ever emitted

	def test_edge_omits_pipe_segment_when_no_label_given(self):
		result = handle_render_mermaid(
			diagram_type="graph LR",
			nodes=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
			edges=[{"from": "a", "to": "b"}],
		)

		self.assertIn("a --> b", result)
		self.assertNotIn("|", result)
		# default title applied when none given
		self.assertIn('title="Diagram"', result)

	def test_rejects_edge_referencing_undeclared_node_id(self):
		with self.assertRaises(ValueError) as ctx:
			handle_render_mermaid(
				diagram_type="graph TD",
				nodes=[{"id": "a", "label": "A"}],
				edges=[{"from": "a", "to": "ghost"}],
			)
		self.assertIn("ghost", str(ctx.exception))
		self.assertIn("declared node id", str(ctx.exception))

	def test_rejects_invalid_diagram_type(self):
		with self.assertRaises(ValueError):
			handle_render_mermaid(
				diagram_type="pie chart",
				nodes=[{"id": "a", "label": "A"}],
				edges=[],
			)

	def test_escapes_special_characters_in_node_and_edge_labels(self):
		result = handle_render_mermaid(
			diagram_type="graph TD",
			nodes=[{"id": "a", "label": 'Weird [label] "quoted"'}, {"id": "b", "label": "B"}],
			edges=[{"from": "a", "to": "b", "label": "pipe|here"}],
		)

		# The raw dangerous characters must not survive into the node/edge
		# label text (aside from the syntactic brackets Mermaid itself needs
		# around a node's own label, which _sanity_check_mermaid_dsl already
		# verifies stay balanced).
		node_line = next(line for line in result.splitlines() if line.strip().startswith("a["))
		inner_label = node_line.strip()[len("a[") : -1]
		self.assertNotIn("[", inner_label)
		self.assertNotIn("]", inner_label)
		self.assertNotIn('"', inner_label)

		edge_line = next(line for line in result.splitlines() if "-->" in line and "a" in line.split("-->")[0])
		self.assertNotIn("pipe|here", edge_line)


class TestRenderChart(unittest.TestCase):
	DATA = [{"label": "Jan", "value": 10}, {"label": "Feb", "value": 20}]

	def _artifact_body(self, result):
		match = re.match(r'^<artifact type="chart" language="jsx" title="[^"]*">\n(.*)\n</artifact>$', result, re.DOTALL)
		self.assertIsNotNone(result and match, f"artifact tag shape unexpected: {result[:120]!r}")
		return match.group(1)

	def test_bar_chart_produces_correct_jsx_in_artifact_tag(self):
		result = handle_render_chart(chart_type="bar", data=self.DATA, title="Sales")
		self.assertTrue(result.startswith('<artifact type="chart" language="jsx" title="Sales">'))
		body = self._artifact_body(result)
		self.assertIn("const data = ", body)
		self.assertIn("BarChart", body)
		self.assertIn("<Bar ", body)
		self.assertIn('dataKey="value"', body)
		self.assertIn('dataKey="label"', body)  # x_key default
		self.assertNotIn("CardHeader", body)
		self.assertNotIn("CardTitle", body)

	def test_line_chart_produces_correct_jsx(self):
		result = handle_render_chart(chart_type="line", data=self.DATA)
		body = self._artifact_body(result)
		self.assertIn("LineChart", body)
		self.assertIn("<Line ", body)

	def test_area_chart_produces_correct_jsx(self):
		result = handle_render_chart(chart_type="area", data=self.DATA)
		body = self._artifact_body(result)
		self.assertIn("AreaChart", body)
		self.assertIn("<Area ", body)

	def test_pie_chart_produces_correct_jsx_with_cells_and_fallback_color(self):
		data = [{"label": "A", "value": 1}, {"label": "B", "value": 2}]
		result = handle_render_chart(chart_type="pie", data=data)
		body = self._artifact_body(result)
		self.assertIn("PieChart", body)
		self.assertIn("<Pie ", body)
		self.assertIn("<Cell ", body)
		self.assertIn("colors[index % colors.length] || ", body)  # || fallback, not string concat
		self.assertIn("const colors = ", body)

	def test_rejects_chart_type_outside_allowed_set(self):
		with self.assertRaises(ValueError):
			handle_render_chart(chart_type="scatter", data=self.DATA)

	def test_rejects_data_missing_required_series_key_field(self):
		bad_data = [{"label": "Jan", "value": 10}, {"label": "Feb"}]
		with self.assertRaises(ValueError) as ctx:
			handle_render_chart(chart_type="bar", data=bad_data, series_keys=["value"])
		message = str(ctx.exception)
		self.assertIn("value", message)
		self.assertIn("1", message)  # row index 1 is the offending row

	def test_rejects_data_missing_required_x_key_field(self):
		bad_data = [{"value": 10}]
		with self.assertRaises(ValueError):
			handle_render_chart(chart_type="bar", data=bad_data)

	def test_rejects_empty_data(self):
		with self.assertRaises(ValueError):
			handle_render_chart(chart_type="bar", data=[])

	def test_data_is_json_serialized_safely_not_string_concatenated(self):
		data = [{"label": 'A "quoted" & <b>', "value": 5}]
		result = handle_render_chart(chart_type="bar", data=data)
		body = self._artifact_body(result)
		# json.dumps would escape the embedded quote rather than breaking out
		# of the JS string literal.
		self.assertIn('\\"quoted\\"', body)


class TestPromptInstructionSelection(unittest.TestCase):
	"""Covers the agent_integration.py selection of
	CHART_ARTIFACT_INSTRUCTIONS_WITH_TOOL / MERMAID_ARTIFACT_INSTRUCTIONS_WITH_TOOL
	vs. the full-length originals, based on whether render_chart/render_mermaid
	are present in the agent's resolved tool list.

	huf.ai.agent_integration imports frappe at module level, so it cannot even
	be imported without a Frappe site/bench (this sandbox has neither - no
	`sites/` directory and no installed `frappe` package). This test therefore
	drives AgentManager.create_agent() end to end via bench run-tests only;
	if frappe is not importable it is skipped rather than reported as a
	false failure, so a plain `python -m pytest` run states plainly why the
	real assertions did not execute.
	"""

	@classmethod
	def setUpClass(cls):
		try:
			import frappe  # noqa: F401
		except ImportError:
			raise unittest.SkipTest(
				"frappe is not importable in this environment - this test requires "
				"`bench --site <site> run-tests --app huf --module huf.ai.tests.test_render_tools`"
			)

	def _make_manager(self, tool_names):
		from huf.ai.agent_integration import AgentManager

		manager = AgentManager.__new__(AgentManager)
		manager.agent_doc = mock.MagicMock()
		manager.agent_doc.enable_conversation_data = False
		manager.agent_doc.enable_memory = False
		manager.agent_doc.allow_chat = True
		manager.agent_doc.agent_name = "test-agent"
		manager.effective_model = "test-model"
		manager.effective_provider = "test-provider"
		# create_agent() calls self.provider.get_model(...) - production callers
		# always go through AgentManager.__init__ -> _setup_client(), which sets
		# this up from the Agent's configured AI Provider. This test builds the
		# manager via __new__() to skip all of that DB/network-touching setup,
		# so the seam has to be stubbed by hand here.
		manager.provider = mock.MagicMock()
		# The Agents SDK validates this: Agent(model=...) rejects anything that
		# isn't a string, a Model, or None, so a bare MagicMock will not do.
		manager.provider.get_model.return_value = "test-model"
		manager.tools = [mock.MagicMock(name=n, description="d") for n in tool_names]
		for tool, n in zip(manager.tools, tool_names):
			tool.name = n
		return manager

	def _resolve_instructions(self, tool_names):
		from huf.ai.chart_artifact_instructions import CHART_ARTIFACT_INSTRUCTIONS_WITH_TOOL
		from huf.ai.artifact_instructions import MERMAID_ARTIFACT_INSTRUCTIONS_WITH_TOOL

		manager = self._make_manager(tool_names)

		with mock.patch("huf.ai.prompt_resolver.resolve_prompt", return_value=""), \
			mock.patch("huf.ai.skills.loader.get_skill_instructions", return_value=""), \
			mock.patch("huf.ai.skills.loader.get_optional_skills_preamble", return_value=""), \
			mock.patch("huf.ai.skills.loader.get_skill_prompts", return_value=[]), \
			mock.patch("huf.ai.capabilities.capability_enabled", return_value=True), \
			mock.patch("huf.ai.artifact_instructions.agent_has_media_tools", return_value=False):
			agent = manager.create_agent()

		instructions = agent.instructions if hasattr(agent, "instructions") else agent["instructions"]
		return instructions, CHART_ARTIFACT_INSTRUCTIONS_WITH_TOOL, MERMAID_ARTIFACT_INSTRUCTIONS_WITH_TOOL

	def test_short_variants_selected_when_tools_are_attached(self):
		instructions, chart_short, mermaid_short = self._resolve_instructions(["render_chart", "render_mermaid"])
		self.assertIn(chart_short.strip(), instructions)
		self.assertIn(mermaid_short.strip(), instructions)

	def test_full_variants_selected_when_tools_are_not_attached(self):
		instructions, chart_short, mermaid_short = self._resolve_instructions(["some_other_tool"])
		self.assertNotIn(chart_short.strip(), instructions)
		self.assertNotIn(mermaid_short.strip(), instructions)
		self.assertIn("SYSTEM INSTRUCTION - JSX CHART ARTIFACTS", instructions)
		self.assertIn("4. MERMAID DIAGRAMS\n<artifact type=\"mermaid\"", instructions)


if __name__ == "__main__":
	unittest.main()
