"""FU-EMBED-HANDOFF: the embed palette offers ``handoff`` and the app-flow target limits stay. Needs no site."""

import unittest

from huf.ai.flow.app_scope import targets
from huf.ai.flow.catalog.node_registry import EMBED_BUILTIN_TYPES, embed_builtin_types


def _step(**config):
	return {"id": "human", "type": "handoff", "config": config}


class TestHandoffEmbed(unittest.TestCase):
	def test_the_embed_palette_offers_handoff(self):
		self.assertIn("handoff", embed_builtin_types())
		for generic in ("code.run", "tool.call", "doc.create", "doc.update"):
			self.assertNotIn(generic, EMBED_BUILTIN_TYPES)

	def test_a_handoff_may_still_only_target_the_runs_member(self):
		good = {"gateway": "wa", "recipient": "$member", "message": ""}
		self.assertEqual(targets.handoff_problems([_step(**good)]), [])
		for change in ({"recipient": "+10000000000"}, {"message": "hi"}, {"conversation": "c1"}):
			self.assertEqual(targets.handoff_problems([_step(**{**good, **change})]), ["human"])
		self.assertEqual(targets.computed_gateways([_step(**{**good, "gateway": "{{ vars.g }}"})]), ["human"])
