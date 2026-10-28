"""Pure check: every tool id a frontend action card presets exists in the built-in registry.

list_flow_tools returns every Agent Tool Function (synced from huf/ai/tools/_registry.py by migrate)
except type "Code Execution", so a preset id that is in the registry with an importable handler is
offered to any Huf User. Run: python3 -m pytest huf/ai/flow/tests/test_flow_card_tool_ids.py
"""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ACTIONS_TS = ROOT / "frontend" / "src" / "data" / "actions.ts"
REGISTRY = ROOT / "huf" / "ai" / "tools" / "_registry.py"


def _preset_ids() -> set[str]:
	text = ACTIONS_TS.read_text()
	block = text[text.index("ACTION_CARD_CONTRACT") :]
	ids = set(re.findall(r"toolId:\s*'([^']+)'", block))
	for group in re.findall(r"toolIds:\s*\[([^\]]*)\]", block):
		ids.update(re.findall(r"'([^']+)'", group))
	return ids


def _registry_handlers() -> dict[str, str]:
	out = {}
	for node in ast.walk(ast.parse(REGISTRY.read_text())):
		if isinstance(node, ast.Dict):
			d = {k.value: v.value for k, v in zip(node.keys, node.values)
				if isinstance(k, ast.Constant) and isinstance(v, ast.Constant) and isinstance(v.value, str)}
			if "tool_name" in d and "function_path" in d:
				out[d["tool_name"]] = d["function_path"]
	return out


class TestCardToolIds(unittest.TestCase):
	def test_every_preset_tool_is_registered_with_a_real_handler(self):
		ids, handlers = _preset_ids(), _registry_handlers()
		self.assertGreaterEqual(len(ids), 10)
		for tool_id in sorted(ids):
			self.assertIn(tool_id, handlers, f"{tool_id} missing from _registry.py")
			mod, fn = handlers[tool_id].rsplit(".", 1)
			path = ROOT / (mod.replace(".", "/") + ".py")
			self.assertTrue(path.exists(), f"{tool_id}: {path} missing")
			names = {n.name for n in ast.walk(ast.parse(path.read_text())) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
			self.assertIn(fn, names, f"{tool_id}: {fn} not defined in {path.name}")

	def test_no_preset_is_code_execution(self):
		self.assertNotIn("run_python", _preset_ids())


if __name__ == "__main__":
	unittest.main()
