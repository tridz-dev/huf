# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase

from huf.ai.skills.exporter import build_huf_archive, build_skill_md
from huf.ai.skills.importer import (
	_parse_skill_manifest,
	_resolve_link,
	_get_common_destinations,
	import_skill_from_path,
	import_skill_from_huf,
)
from huf.ai.skills.loader import get_skill_prompts


class TestSkillManifestParsing(FrappeTestCase):
	def test_parse_skill_md_with_huf_block(self):
		skill_dir = Path(tempfile.mkdtemp())
		skill_md = skill_dir / "SKILL.md"
		skill_md.write_text(
			"---\n"
			"name: test-md-skill\n"
			"description: A skill from SKILL.md\n"
			"compatibility:\n"
			"  requires: []\n"
			"huf:\n"
			"  version: \"1.2.3\"\n"
			"  author: Test Author\n"
			"  category: Test Category\n"
			"  tools:\n"
			"    - tool_name: get_list\n"
			"  knowledge:\n"
			"    - source_name: Test Source\n"
			"      mode: Mandatory\n"
			"  prompts:\n"
			"    - slug: test-prompt\n"
			"      usage: System\n"
			"---\n"
			"\n"
			"# Instructions\n"
			"These are the instructions.\n",
			encoding="utf-8",
		)

		manifest = _parse_skill_manifest(str(skill_dir))
		self.assertEqual(manifest["name"], "test-md-skill")
		self.assertEqual(manifest["description"], "A skill from SKILL.md")
		self.assertEqual(manifest["version"], "1.2.3")
		self.assertEqual(manifest["author"], "Test Author")
		self.assertEqual(manifest["category"], "Test Category")
		self.assertEqual(manifest["instructions"], "# Instructions\nThese are the instructions.")
		self.assertEqual(manifest["tools"], [{"tool_name": "get_list"}])
		self.assertEqual(manifest["knowledge"], [{"source_name": "Test Source", "mode": "Mandatory"}])
		self.assertEqual(manifest["prompts"], [{"slug": "test-prompt", "usage": "System"}])

		# Cleanup
		shutil.rmtree(skill_dir)

	def test_parse_skill_json_legacy_fallback(self):
		skill_dir = Path(tempfile.mkdtemp())
		(skill_dir / "skill.json").write_text(
			json.dumps(
				{
					"name": "legacy-skill",
					"title": "Legacy Skill",
					"description": "Legacy format",
					"version": "1.0.0",
				}
			),
			encoding="utf-8",
		)

		manifest = _parse_skill_manifest(str(skill_dir))
		self.assertEqual(manifest["name"], "legacy-skill")
		self.assertEqual(manifest["description"], "Legacy format")

		shutil.rmtree(skill_dir)


class TestSkillLinkResolution(FrappeTestCase):
	def test_resolve_link_skips_missing(self):
		warnings = []
		result = _resolve_link("Agent Tool Function", "tool_name", "Missing Tool", warnings)
		self.assertIsNone(result)
		self.assertTrue(any("Missing Tool" in w for w in warnings))

	def test_resolve_link_dict_lookup(self):
		warnings = []
		result = _resolve_link("Agent Tool Function", "tool_name", {"tool_name": "Also Missing"}, warnings)
		self.assertIsNone(result)
		self.assertTrue(any("Also Missing" in w for w in warnings))


class TestSkillImportAndExport(FrappeTestCase):
	def setUp(self):
		self.skill_name = "test-export-import-skill"
		if frappe.db.exists("Skill", {"skill_name": self.skill_name}):
			name = frappe.db.get_value("Skill", {"skill_name": self.skill_name}, "name")
			frappe.delete_doc("Skill", name, force=True)

		doc = frappe.get_doc(
			{
				"doctype": "Skill",
				"skill_name": self.skill_name,
				"title": "Test Export Import Skill",
				"description": "A skill for testing export/import roundtrip.",
				"version": "2.0.0",
				"author": "Tester",
				"instructions": "Do the thing.",
				"status": "Active",
			}
		)
		doc.insert(ignore_permissions=True)

	def tearDown(self):
		if frappe.db.exists("Skill", {"skill_name": self.skill_name}):
			name = frappe.db.get_value("Skill", {"skill_name": self.skill_name}, "name")
			frappe.delete_doc("Skill", name, force=True)

	def test_build_skill_md(self):
		skill_doc = frappe.get_doc("Skill", {"skill_name": self.skill_name})
		content = build_skill_md(skill_doc)
		self.assertIn("name: test-export-import-skill", content)
		self.assertIn("title: Test Export Import Skill", content)
		self.assertIn("huf:", content)
		self.assertIn("Do the thing.", content)

	def test_huf_export_import_roundtrip(self):
		# Export
		archive_bytes = build_huf_archive(self.skill_name)
		self.assertTrue(archive_bytes)

		# Write to temp .huf file and import
		temp_dir = tempfile.mkdtemp()
		file_doc = None
		try:
			huf_path = os.path.join(temp_dir, f"{self.skill_name}.huf")
			with open(huf_path, "wb") as f:
				f.write(archive_bytes)

			# Delete the original skill so re-import is not just an update
			name = frappe.db.get_value("Skill", {"skill_name": self.skill_name}, "name")
			frappe.delete_doc("Skill", name, force=True)
			frappe.db.commit()

			# Create a File doc for the uploaded archive
			with open(huf_path, "rb") as f:
				file_doc = frappe.get_doc(
					{
						"doctype": "File",
						"file_name": f"{self.skill_name}.huf",
						"is_private": 0,
					}
				)
				file_doc.content = f.read()
				file_doc.save(ignore_permissions=True)

			result = import_skill_from_huf(file_doc.file_url)
			self.assertEqual(result["skill"], self.skill_name)
			self.assertTrue(frappe.db.exists("Skill", {"skill_name": self.skill_name}))
		finally:
			shutil.rmtree(temp_dir, ignore_errors=True)
			if file_doc and frappe.db.exists("File", file_doc.name):
				frappe.delete_doc("File", file_doc.name, force=True)


class TestSkillPromptRuntime(FrappeTestCase):
	def setUp(self):
		self.agent_name = "test-prompt-agent"
		self.skill_name = "test-prompt-skill"
		self.prompt_name = "test-prompt-doc"

		if not frappe.db.exists("AI Provider", "Test Provider"):
			frappe.get_doc(
				{
					"doctype": "AI Provider",
					"provider_name": "Test Provider",
					"api_key": "dummy-key",
				}
			).insert(ignore_permissions=True)

		if not frappe.db.exists("AI Model", "gpt-4"):
			frappe.get_doc(
				{
					"doctype": "AI Model",
					"model_name": "gpt-4",
					"provider": "Test Provider",
				}
			).insert(ignore_permissions=True)

		if frappe.db.exists("Agent Prompt", self.prompt_name):
			frappe.delete_doc("Agent Prompt", self.prompt_name, force=True)

		prompt_doc = frappe.get_doc(
			{
				"doctype": "Agent Prompt",
				"title": self.prompt_name,
				"slug": self.prompt_name,
				"prompt_body": "You are a helpful tester.",
				"is_active": 1,
			}
		)
		prompt_doc.insert(ignore_permissions=True)

		if frappe.db.exists("Skill", {"skill_name": self.skill_name}):
			name = frappe.db.get_value("Skill", {"skill_name": self.skill_name}, "name")
			frappe.delete_doc("Skill", name, force=True)

		skill_doc = frappe.get_doc(
			{
				"doctype": "Skill",
				"skill_name": self.skill_name,
				"title": "Test Prompt Skill",
				"status": "Active",
				"skill_prompts": [{"prompt": prompt_doc.name, "usage": "System"}],
			}
		)
		skill_doc.insert(ignore_permissions=True)

		if frappe.db.exists("Agent", self.agent_name):
			frappe.delete_doc("Agent", self.agent_name, force=True)

		agent_doc = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": self.agent_name,
				"provider": "Test Provider",
				"model": "gpt-4",
				"instructions": "Base instructions.",
				"agent_skill": [{"skill": skill_doc.name, "mode": "Mandatory"}],
			}
		)
		agent_doc.insert(ignore_permissions=True)

	def tearDown(self):
		if frappe.db.exists("Agent", self.agent_name):
			frappe.delete_doc("Agent", self.agent_name, force=True)
		if frappe.db.exists("Skill", {"skill_name": self.skill_name}):
			name = frappe.db.get_value("Skill", {"skill_name": self.skill_name}, "name")
			frappe.delete_doc("Skill", name, force=True)
		if frappe.db.exists("Agent Prompt", self.prompt_name):
			frappe.delete_doc("Agent Prompt", self.prompt_name, force=True)

	def test_get_skill_prompts(self):
		prompts = get_skill_prompts(self.agent_name)
		self.assertEqual(len(prompts), 1)
		self.assertEqual(prompts[0]["usage"], "System")
		self.assertEqual(prompts[0]["body"], "You are a helpful tester.")


class TestSkillDestinations(FrappeTestCase):
	def test_default_destinations_returned(self):
		destinations = _get_common_destinations()
		self.assertIn("huf-skills", destinations)
		self.assertEqual(destinations["huf-skills"]["repo_url"], "https://github.com/tridz-dev/huf-skills")
