"""The Flows list shows a chat trigger as a plain label: the channel's display name, no credentials or config."""

import unittest
from huf.ai.flow.listing import cards


class TestCardGatewayLabel(unittest.TestCase):
	def test_summary_keeps_only_the_gateway_name_key(self):
		defn = {
			"entry": "t1",
			"nodes": [{"id": "t1", "type": "trigger.whatsapp", "config": {"gateway": "Support", "params": [{"key": "keywords", "value": ["x"]}], "token": "s3cret"}}],
		}
		trigger = cards.summarize_definition(defn)["trigger"]
		self.assertEqual(trigger, {"type": "whatsapp", "gateway": "Support"})


if __name__ == "__main__":
	unittest.main()
