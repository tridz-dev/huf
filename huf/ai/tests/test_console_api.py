"""Tests for the Console prompt-engineering API."""

import json
import unittest
from unittest.mock import MagicMock, patch

from huf.ai import console_api


class TestGeneratePrompt(unittest.TestCase):
	@patch("huf.ai.console_api._get_console_model_config")
	@patch("huf.ai.console_api._simple_completion_sync")
	@patch("huf.ai.console_api.has_capability")
	def test_generate_prompt_returns_cleaned_response(
		self, mock_has_capability, mock_completion, mock_config
	):
		mock_has_capability.return_value = True
		mock_config.return_value = ("OpenAI", "gpt-4o")
		mock_completion.return_value = "  You are a helpful assistant.  "

		result = console_api.generate_prompt("Create a friendly assistant prompt")

		self.assertEqual(result["prompt"], "You are a helpful assistant.")
		mock_completion.assert_called_once()

	@patch("huf.ai.console_api.has_capability")
	def test_generate_prompt_requires_description(self, mock_has_capability):
		mock_has_capability.return_value = True
		with self.assertRaises(Exception):
			console_api.generate_prompt("")

	@patch("huf.ai.console_api._get_console_model_config")
	@patch("huf.ai.console_api.has_capability")
	def test_generate_prompt_raises_without_provider(self, mock_has_capability, mock_config):
		mock_has_capability.return_value = True
		mock_config.return_value = (None, None)
		with self.assertRaises(Exception):
			console_api.generate_prompt("Some description")


class TestEvaluateRun(unittest.TestCase):
	@patch("huf.ai.console_api._get_console_model_config")
	@patch("huf.ai.console_api._simple_completion_sync")
	@patch("huf.ai.console_api.has_capability")
	def test_evaluate_run_parses_json_response(
		self, mock_has_capability, mock_completion, mock_config
	):
		mock_has_capability.return_value = True
		mock_config.return_value = ("OpenAI", "gpt-4o")
		mock_completion.return_value = json.dumps({
			"passed": True,
			"score": 95,
			"reasoning": "Response is clear and accurate.",
		})

		result = console_api.evaluate_run("Hello", "Should be a greeting")

		self.assertTrue(result["passed"])
		self.assertEqual(result["score"], 95.0)
		self.assertEqual(result["reasoning"], "Response is clear and accurate.")

	@patch("huf.ai.console_api._get_console_model_config")
	@patch("huf.ai.console_api._simple_completion_sync")
	@patch("huf.ai.console_api.has_capability")
	def test_evaluate_run_strips_markdown_fences(
		self, mock_has_capability, mock_completion, mock_config
	):
		mock_has_capability.return_value = True
		mock_config.return_value = ("OpenAI", "gpt-4o")
		mock_completion.return_value = "```json\n{\"passed\": false, \"score\": 30, \"reasoning\": \"No\"}\n```"

		result = console_api.evaluate_run("Bad output", "Must mention refunds")

		self.assertFalse(result["passed"])
		self.assertEqual(result["score"], 30.0)

	@patch("huf.ai.console_api._simple_completion_sync")
	@patch("huf.ai.console_api.has_capability")
	def test_evaluate_run_uses_explicit_provider_model(
		self, mock_has_capability, mock_completion
	):
		mock_has_capability.return_value = True
		mock_completion.return_value = json.dumps({
			"passed": True,
			"score": 80,
			"reasoning": "OK",
		})

		with patch("huf.ai.console_api.frappe.db.exists", return_value=True):
			result = console_api.evaluate_run(
				"Response",
				"Criteria",
				provider="OpenAI",
				model="gpt-4o",
			)

		self.assertTrue(result["passed"])
		mock_completion.assert_called_once()

	@patch("huf.ai.console_api.has_capability")
	def test_evaluate_run_requires_response_and_criteria(self, mock_has_capability):
		mock_has_capability.return_value = True
		with self.assertRaises(Exception):
			console_api.evaluate_run("", "Criteria")
		with self.assertRaises(Exception):
			console_api.evaluate_run("Response", "")


class TestSavePromptTemplate(unittest.TestCase):
	@patch("huf.ai.console_api.has_capability")
	@patch("huf.ai.console_api.frappe.get_doc")
	def test_save_prompt_template_creates_agent_prompt(
		self, mock_get_doc, mock_has_capability
	):
		mock_has_capability.return_value = True
		mock_doc = MagicMock()
		mock_doc.name = "PROMPT-0001"
		mock_get_doc.return_value = mock_doc

		result = console_api.save_prompt_template(
			prompt_body="You are an expert.",
			title="Expert Prompt",
			description="A test prompt",
			visibility="Public",
			tags="test, demo",
		)

		self.assertEqual(result["name"], "PROMPT-0001")
		self.assertEqual(result["version"], 1)
		mock_get_doc.assert_called_once()
		call_args = mock_get_doc.call_args[0][0]
		self.assertEqual(call_args["doctype"], "Agent Prompt")
		self.assertEqual(call_args["title"], "Expert Prompt")
		self.assertEqual(call_args["visibility"], "Public")

	@patch("huf.ai.console_api.has_capability")
	def test_save_prompt_template_requires_body_and_title(self, mock_has_capability):
		mock_has_capability.return_value = True
		with self.assertRaises(Exception):
			console_api.save_prompt_template("", "Title")
		with self.assertRaises(Exception):
			console_api.save_prompt_template("Body", "")


class TestParseEvaluationJson(unittest.TestCase):
	def test_parses_valid_json(self):
		result = console_api._parse_evaluation_json('{"passed": true, "score": 88, "reasoning": "Good"}')
		self.assertTrue(result["passed"])
		self.assertEqual(result["score"], 88.0)

	def test_clamps_score(self):
		result = console_api._parse_evaluation_json('{"passed": false, "score": 150, "reasoning": "Bad"}')
		self.assertEqual(result["score"], 100.0)

	def test_fills_missing_reasoning(self):
		result = console_api._parse_evaluation_json('{"passed": true, "score": 100}')
		self.assertEqual(result["reasoning"], "No reasoning provided.")


class TestGetConsoleModelConfig(unittest.TestCase):
	@patch("huf.ai.console_api.frappe.conf", {"huf_console_prompt_engineer_model": "OpenAI:gpt-4o"})
	@patch("huf.ai.console_api.frappe.db.exists")
	def test_uses_site_config_when_valid(self, mock_exists):
		mock_exists.return_value = True

		provider, model = console_api._get_console_model_config()

		self.assertEqual(provider, "OpenAI")
		self.assertEqual(model, "gpt-4o")

	@patch("huf.ai.console_api.frappe.conf", {})
	@patch("huf.ai.console_api.frappe.get_all")
	@patch("huf.ai.console_api.frappe.get_doc")
	@patch("huf.ai.console_api.frappe.db.get_value")
	def test_falls_back_to_first_provider_with_key(
		self,
		mock_get_value,
		mock_get_doc,
		mock_get_all,
	):
		mock_get_all.return_value = [{"name": "OpenAI", "provider_brand": "openai"}]
		provider_doc = MagicMock()
		provider_doc.get_password.return_value = "secret"
		mock_get_doc.return_value = provider_doc
		mock_get_value.return_value = "gpt-4o"

		provider, model = console_api._get_console_model_config()

		self.assertEqual(provider, "OpenAI")
		self.assertEqual(model, "gpt-4o")
