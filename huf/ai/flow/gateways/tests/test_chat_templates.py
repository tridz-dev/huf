"""The shipped chat templates (frontend/src/data/flowTemplates.json) are valid flow graphs."""

import json
import unittest
from pathlib import Path

from huf.ai.graph.validator import validate_flow_graph

CATALOG = Path(__file__).resolve().parents[5] / "frontend" / "src" / "data" / "flowTemplates.json"


class TestChatTemplates(unittest.TestCase):
	def test_each_chat_template_validates(self):
		templates = {t["id"]: t for t in json.loads(CATALOG.read_text())}
		for template_id in ("whatsapp-agent-reply", "telegram-keyword-reply"):
			result = validate_flow_graph(templates[template_id]["graph"])
			self.assertTrue(result.ok, f"{template_id}: {result.errors}")


if __name__ == "__main__":
	unittest.main()
