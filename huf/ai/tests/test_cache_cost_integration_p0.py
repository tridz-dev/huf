# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Real-Frappe (Layer B) integration test proving prompt caching actually
reduces the *billed* cost of an Agent Run end-to-end, deterministically.

Why this test exists
---------------------
Prompt caching exists to cut LLM spend (see PR #678
``feat/prompt-cache-auto-mode``, merged into ``pre-develop``, which turns
caching on by default). Everything that already tests caching in this repo
(``test_cache_marker_placement.py``, ``test_cache_metrics.py``,
``test_prompt_cache_mode_runtime.py``, ``cost_calculator.py``'s own
``_calculate_from_custom_pricing`` cached-token discount branch) is a pure
unit test of an isolated function -- none of them submit a real run through
``huf.ai.agent_integration.run_agent_sync`` and check that a cache hit
actually lands as a lower persisted ``Agent Run.cost``. That plumbing gap
(usage dict -> ``calculate_cost()`` call site in ``agent_integration.py`` ->
``Agent Run.cost``/``cached_tokens`` columns) is exactly what silently
breaks if any of those pieces drift out of sync with each other, and a
purely unit-level test suite cannot catch it. Since caching exists
specifically to save money, that plumbing is treated as a first-class,
deterministic (no live LLM, no real spend) test requirement here.

Provider determinism
---------------------
Uses the HUF Test Provider (see ``test_agent_runtime_p0.py``'s module
docstring for the full routing-check citation chain) with an AI Model that
has ``use_custom_pricing=1`` and an explicit
``cached_input_cost_per_1m_tokens`` set below the regular input rate --
this is what makes ``cost_calculator.calculate_cost()`` take the "custom"
pricing branch (`get_model_pricing()` returns non-None) instead of falling
through to LiteLLM's price table, which has no entry for a fake test model
name and would return cost=0.0 regardless of caching either way.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_cache_cost_integration_p0
"""

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.agent_integration import run_agent_sync
from huf.ai.tests.factories import make_agent, make_ai_model, make_ai_provider

PREFIX = "_Test P0CI"

# Mirrors huf/ai/providers/test_provider.py's TEST_TEXT/TEST_CACHED_USAGE
# constants: both scenarios report input_tokens=10, output_tokens=8;
# TEST_CACHED_USAGE additionally reports 6 of those 10 input tokens as
# cache reads (cached_tokens=6). Chosen here to compute the exact expected
# cost by hand rather than re-deriving cost_calculator's own formula.
_INPUT_TOKENS = 10
_OUTPUT_TOKENS = 8
_CACHED_TOKENS = 6

_INPUT_COST_PER_1M = 10.0
_OUTPUT_COST_PER_1M = 20.0
_CACHED_INPUT_COST_PER_1M = 1.0  # 10x cheaper than a regular input token


class TestCacheCostIntegrationP0(IntegrationTestCase):
    def setUp(self):
        self._names = {"Agent": [], "AI Model": [], "AI Provider": [], "Agent Conversation": []}

    def tearDown(self):
        frappe.set_user("Administrator")
        for doctype in ("Agent Conversation", "Agent", "AI Model", "AI Provider"):
            for name in self._names.get(doctype, []):
                try:
                    frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
                except Exception:
                    pass
        frappe.db.commit()

    def _track(self, doctype, name):
        self._names.setdefault(doctype, []).append(name)
        return name

    def _make_custom_priced_test_agent(self):
        """Agent wired to the Test Provider, with an AI Model carrying
        explicit custom pricing (incl. a cached-token discount rate) so
        ``calculate_cost()`` takes its "custom" branch deterministically --
        see this module's docstring for why LiteLLM's own price table is
        not usable here."""
        if frappe.db.exists("AI Provider", "Test_Provider"):
            provider = frappe.get_doc("AI Provider", "Test_Provider")
        else:
            provider = make_ai_provider(provider_name="Test_Provider")
            self._track("AI Provider", provider.name)

        model = make_ai_model(
            provider=provider.name,
            model_name=f"{PREFIX}-model-{frappe.generate_hash(length=6)}",
            use_custom_pricing=1,
            input_cost_per_1m_tokens=_INPUT_COST_PER_1M,
            output_cost_per_1m_tokens=_OUTPUT_COST_PER_1M,
            cached_input_cost_per_1m_tokens=_CACHED_INPUT_COST_PER_1M,
        )
        self._track("AI Model", model.name)

        agent = make_agent(
            agent_name=f"{PREFIX} Agent {frappe.generate_hash(length=8)}",
            provider=provider.name,
            model=model.name,
        )
        self._track("Agent", agent.name)
        return agent

    def _submit(self, agent, scenario):
        result = run_agent_sync(
            agent_name=agent.name,
            prompt=f"__TEST_SCENARIO__:{scenario}",
            now=1,
        )
        self.assertTrue(result.get("success"), result)
        self._track("Agent Conversation", result["conversation_id"])
        return frappe.get_doc("Agent Run", result["agent_run_id"])

    def _expected_cost(self, cached_tokens):
        regular_input_tokens = _INPUT_TOKENS - cached_tokens
        return (
            (regular_input_tokens / 1_000_000) * _INPUT_COST_PER_1M
            + (cached_tokens / 1_000_000) * _CACHED_INPUT_COST_PER_1M
            + (_OUTPUT_TOKENS / 1_000_000) * _OUTPUT_COST_PER_1M
        )

    def test_cache_hit_persists_lower_cost_than_equivalent_uncached_run(self):
        """A cache hit (TEST_CACHED_USAGE) must persist a real, lower
        ``Agent Run.cost`` than the token-identical uncached run
        (TEST_TEXT) -- proving the usage-dict -> calculate_cost() ->
        Agent Run.cost plumbing actually passes caching's savings through,
        not just that the isolated pricing formula is capable of it."""
        agent = self._make_custom_priced_test_agent()

        uncached_run = self._submit(agent, "TEST_TEXT")
        cached_run = self._submit(agent, "TEST_CACHED_USAGE")

        self.assertEqual(uncached_run.cached_tokens, 0)
        self.assertEqual(cached_run.cached_tokens, _CACHED_TOKENS)

        self.assertAlmostEqual(uncached_run.cost, self._expected_cost(cached_tokens=0), places=6)
        self.assertAlmostEqual(cached_run.cost, self._expected_cost(cached_tokens=_CACHED_TOKENS), places=6)

        # The actual money assertion: caching must make the run cheaper,
        # not merely "different" or "not obviously wrong".
        self.assertLess(
            cached_run.cost,
            uncached_run.cost,
            "a cache hit must cost less than an equivalent uncached run — "
            "if this ever fails, caching has stopped saving money end-to-end",
        )
