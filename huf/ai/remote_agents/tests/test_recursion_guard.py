"""Tests for recursion_guard.py. Plain unittest, no Frappe dependency."""

from __future__ import annotations

import unittest

from huf.ai.remote_agents.recursion_guard import (
	MAX_HOPS,
	CallChain,
	RemoteAgentRecursionError,
	check_and_extend,
)


class TestCallChainSerialization(unittest.TestCase):
	def test_empty_chain_from_missing_header(self):
		self.assertEqual(CallChain.from_header_value(None).hops, ())
		self.assertEqual(CallChain.from_header_value("").hops, ())

	def test_roundtrip(self):
		chain = CallChain.start("siteA|agent1").extended("siteB|agent2")
		serialized = chain.to_header_value()
		self.assertEqual(serialized, "siteA|agent1,siteB|agent2")
		parsed = CallChain.from_header_value(serialized)
		self.assertEqual(parsed.hops, chain.hops)

	def test_chain_is_immutable(self):
		chain = CallChain.start("siteA|agent1")
		extended = chain.extended("siteB|agent2")
		# original untouched
		self.assertEqual(chain.hops, ("siteA|agent1",))
		self.assertEqual(extended.hops, ("siteA|agent1", "siteB|agent2"))


class TestDirectSelfCall(unittest.TestCase):
	def test_agent_calling_itself_is_rejected(self):
		chain = CallChain.start("siteA|agent1")
		with self.assertRaises(RemoteAgentRecursionError) as ctx:
			check_and_extend(chain, "siteA|agent1")
		self.assertIn("siteA|agent1", ctx.exception.chain)
		self.assertEqual(ctx.exception.attempted_hop, "siteA|agent1")

	def test_top_level_call_with_no_prior_chain_is_fine(self):
		# empty chain (a fresh top-level request) extending to a first hop must succeed
		chain = CallChain()
		result = check_and_extend(chain, "siteA|agent1")
		self.assertEqual(result.hops, ("siteA|agent1",))


class TestIndirectCycle(unittest.TestCase):
	def test_a_to_b_to_c_to_a_is_rejected(self):
		chain = CallChain.start("siteA|agent1")
		chain = check_and_extend(chain, "siteB|agent2")
		chain = check_and_extend(chain, "siteC|agent3")
		# now C tries to call back to A - must be caught even though A isn't the immediate caller
		with self.assertRaises(RemoteAgentRecursionError):
			check_and_extend(chain, "siteA|agent1")

	def test_diamond_shaped_legit_fanout_is_not_falsely_flagged(self):
		# A calls B and C (two separate chains, not a cycle - each fan-out branch gets its own
		# chain starting from A, this models B and C as two independent extensions of the SAME
		# origin chain, not one shared mutated chain)
		origin = CallChain.start("siteA|agent1")
		branch_to_b = check_and_extend(origin, "siteB|agent2")
		branch_to_c = check_and_extend(origin, "siteC|agent3")
		self.assertEqual(branch_to_b.hops, ("siteA|agent1", "siteB|agent2"))
		self.assertEqual(branch_to_c.hops, ("siteA|agent1", "siteC|agent3"))
		# B and C each independently calling a shared fourth agent D is fine - D appears once in
		# each branch's own chain, not shared/mutated state
		check_and_extend(branch_to_b, "siteD|agent4")
		check_and_extend(branch_to_c, "siteD|agent4")


class TestMaxDepth(unittest.TestCase):
	def test_exceeding_max_hops_is_rejected(self):
		chain = CallChain.start("hop0")
		for i in range(1, MAX_HOPS):
			chain = check_and_extend(chain, f"hop{i}")
		self.assertEqual(len(chain.hops), MAX_HOPS)
		with self.assertRaises(RemoteAgentRecursionError) as ctx:
			check_and_extend(chain, "hop_overflow")
		self.assertIn("maximum allowed depth", str(ctx.exception))

	def test_custom_max_hops_respected(self):
		chain = CallChain.start("hop0")
		chain = check_and_extend(chain, "hop1", max_hops=2)
		with self.assertRaises(RemoteAgentRecursionError):
			check_and_extend(chain, "hop2", max_hops=2)


if __name__ == "__main__":
	unittest.main()
