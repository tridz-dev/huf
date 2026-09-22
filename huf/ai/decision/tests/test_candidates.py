import unittest
from types import SimpleNamespace

from huf.ai.decision.candidates import constrain_selected_tool, get_tool_candidates


class TestDecisionCandidates(unittest.TestCase):
	def test_candidates_are_deduplicated_from_authoritative_tools(self):
		tools = [SimpleNamespace(tool_name="refund", description="Refund a payment"), SimpleNamespace(tool_name="refund"), SimpleNamespace(tool_name="lookup")]
		self.assertEqual([option.id for option in get_tool_candidates(tools)], ["refund", "lookup"])

	def test_selection_cannot_widen_authority(self):
		tools = [SimpleNamespace(tool_name="refund")]
		self.assertEqual(constrain_selected_tool("refund", tools), "refund")
		self.assertIsNone(constrain_selected_tool("delete", tools))

	def test_runtime_selection_rechecks_authorized_set(self):
		from huf.ai.decision.backends.fake import FakeDecisionBackend
		from huf.ai.decision.runtime import DecisionRuntime
		from huf.ai.decision.types import DecisionPolicy, DecisionRequest, Option, Question, QuestionKind, StateBinding
		from huf.ai.decision.tool_selection import select_authorized_tool
		policy = DecisionPolicy(policy_id="tool", questions=(Question("tool", QuestionKind.SELECT, "Pick", (Option("refund"), Option("lookup"))),), state_bindings=(StateBinding("request", "$"),))
		request = DecisionRequest(policy=policy, state="find a tool")
		selected, response = select_authorized_tool(DecisionRuntime(), request, FakeDecisionBackend(), [SimpleNamespace(tool_name="refund")])
		self.assertEqual(response.status.value, "success")
		self.assertEqual(selected, "refund")

	def test_procedure_candidates_require_current_bindings(self):
		from huf.ai.decision.candidates import constrain_selected_procedure, get_procedure_candidates
		bindings = [SimpleNamespace(procedure_id="support_lookup", procedure_name="Support lookup", binding_name="binding-1")]
		self.assertEqual([item.id for item in get_procedure_candidates(bindings)], ["support_lookup"])
		self.assertEqual(constrain_selected_procedure("support_lookup", bindings), "support_lookup")
		self.assertIsNone(constrain_selected_procedure("unbound", bindings))
