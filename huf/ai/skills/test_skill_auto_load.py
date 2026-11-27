"""Tests for the skill auto_load rule (no bench required)."""

import sys
import types
import unittest
from unittest import mock

try:
	import agents
except ImportError:  # bench-less runs have no agents SDK
	sys.modules["agents"] = types.SimpleNamespace(FunctionTool=object)

from huf.ai.skills import loader
from huf.ai.skills.auto_load import is_injected_up_front


class _Doc:
	def __init__(self, **kw):
		self.__dict__.update(kw)

	def get(self, key, default=None):
		return getattr(self, key, default)


def _entry(name, mode, skill_auto, row_auto):
	skill = _Doc(
		name=name,
		skill_name=name,
		description=f"{name} desc",
		instructions=f"{name} instructions",
		skill_prompts=[],
		auto_load=skill_auto,
	)
	row = _Doc(skill=name, mode=mode, auto_load=row_auto)
	return skill, row


def _patch(entries):
	def fake(agent_name, mode=None):
		return [(s, r) for s, r in entries if not mode or r.mode == mode]

	return mock.patch.object(loader, "get_agent_skill_entries", fake)


class TestSkillAutoLoad(unittest.TestCase):
	def test_optional_flag_combinations(self):
		for skill_auto, row_auto, injected in [
			(1, 1, True),
			(1, 0, False),
			(0, 1, False),
			(0, 0, False),
			(None, None, True),
		]:
			with self.subTest(skill=skill_auto, row=row_auto):
				skill, row = _entry("s", "Optional", skill_auto, row_auto)
				self.assertEqual(is_injected_up_front(skill, row), injected)
				with _patch([(skill, row)]):
					text = loader.get_skill_instructions("a")
					self.assertEqual("s instructions" in text, injected)

	def test_mandatory_always_injected(self):
		skill, row = _entry("m", "Mandatory", 0, 0)
		self.assertTrue(is_injected_up_front(skill, row))
		with _patch([(skill, row)]):
			self.assertIn("m instructions", loader.get_skill_instructions("a"))
			self.assertEqual(loader.get_optional_skills_preamble("a"), "")

	def test_deferred_optional_is_listed_and_loadable(self):
		entries = [_entry("lazy", "Optional", 0, 1), _entry("eager", "Optional", 1, 1)]
		with (
			_patch(entries),
			mock.patch.object(loader, "get_agent_skills", lambda n, mode=None: [s for s, _ in entries]),
		):
			preamble = loader.get_optional_skills_preamble("a")
			self.assertIn("- lazy: lazy desc (not loaded yet)", preamble)
			self.assertIn("- eager: eager desc", preamble)
			self.assertNotIn("eager desc (not loaded yet)", preamble)
			self.assertIn("load_skill", preamble)
			self.assertEqual([s.skill_name for s in loader.get_deferred_skills("a")], ["lazy"])
			self.assertIn("lazy instructions", loader.handle_load_skill("a", "lazy"))
			self.assertIn("not attached", loader.handle_load_skill("a", "nope"))
