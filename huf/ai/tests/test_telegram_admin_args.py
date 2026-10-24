# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""telegram_admin argument contract: one declaration drives the registry schema, validation and the approval card."""

from __future__ import annotations

import ast
import inspect
import json
import re
import unittest
from unittest.mock import patch

from huf.ai.tests import test_telegram_admin_tools as base_tests
from huf.ai.tools import _registry
from huf.ai.tools import telegram_admin_spec as spec
from huf.ai.tools import telegram_admin_tools as tool

SAMPLE = {
	"chat": "-1001",
	"integer": 5,
	"string": "x",
	"boolean": True,
	"array": ["can_pin_messages"],
	"object": {"type": "default"},
}


def _registry_params() -> dict[str, dict]:
	(entry,) = [t for t in _registry.TELEGRAM_ADMIN_TOOLS if t["tool_name"] == "telegram_admin"]
	return {p["fieldname"]: p for p in entry["parameters"]}


def _sample_args(action: str, *, only_required: bool = False) -> dict:
	out = {}
	for name, required in spec.ACTION_ARGS[action].items():
		if only_required and not required:
			continue
		out[name] = SAMPLE[spec.ARG_TYPES[name][0]]
	if "commands" in out:
		out["commands"] = [{"command": "a", "description": "b"}]
	if "business_connection_id" in out:
		out["business_connection_id"] = "c"
	return out


def _names_read_by(func) -> set[str]:
	"""Argument names a dispatcher function reads: args.get("x"), args["x"], _text/_int(args, "x"), "x" in args."""
	found: set[str] = set()
	for node in ast.walk(ast.parse(_dedent(func))):
		if isinstance(node, ast.Call) and node.args:
			f = node.func
			if isinstance(f, ast.Attribute) and f.attr == "get" and getattr(f.value, "id", "") == "args":
				a = node.args[0]
				if isinstance(a, ast.Constant) and isinstance(a.value, str):
					found.add(a.value)
			if isinstance(f, ast.Name) and f.id in ("_text", "_int") and len(node.args) > 1:
				a = node.args[1]
				if isinstance(a, ast.Constant) and isinstance(a.value, str):
					found.add(a.value)
		if isinstance(node, ast.Subscript) and getattr(node.value, "id", "") == "args":
			if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
				found.add(node.slice.value)
	return found


def _dedent(func) -> str:
	import textwrap

	return textwrap.dedent(inspect.getsource(func))


class TestDeclaration(unittest.TestCase):
	def test_every_action_declared_once(self):
		self.assertEqual(set(spec.ACTION_ARGS), set(tool.ACTIONS))

	def test_every_argument_has_a_type_and_description(self):
		for action, args in spec.ACTION_ARGS.items():
			for name in args:
				self.assertIn(name, spec.ARG_TYPES, f"{action}.{name}")

	def test_registry_declares_every_declared_argument_with_the_right_type(self):
		params = _registry_params()
		expect_names = {n for a in spec.ACTION_ARGS.values() for n in a} | {"action"}
		self.assertEqual(set(params), expect_names)
		for name, (kind, _desc) in spec.ARG_TYPES.items():
			if name in params:
				self.assertEqual(params[name]["type"], "string" if kind == "chat" else kind, name)
		for action, args in spec.ACTION_ARGS.items():
			for name in args:
				self.assertIn(action, params[name]["description"], f"{name} must say it is used by {action}")
		# no per-action argument is schema-required (the action decides), only validated per action
		for name, row in params.items():
			if name != "action":
				self.assertFalse(row["required"], name)

	def test_dispatcher_only_reads_declared_arguments(self):
		declared = {n for a in spec.ACTION_ARGS.values() for n in a}
		read = set()
		for func in (
			tool._execute,
			tool.handle_action,
			tool._until,
			tool._permissions,
			tool._rights,
			tool._menu_button,
			tool._lang,
			tool._connection,
			tool._business_scope,
		):
			read |= _names_read_by(func)
		read |= set(re.findall(r'args\.get\("(\w+)"', inspect.getsource(tool.execute_approved)))
		self.assertEqual(read - declared, set(), "dispatcher reads an argument the table does not declare")
		self.assertEqual(declared - read - {"chat_id"}, set(), "declared but never read")

	def test_tool_description_lists_every_action_usage(self):
		(entry,) = [t for t in _registry.TELEGRAM_ADMIN_TOOLS if t["tool_name"] == "telegram_admin"]
		for action in spec.ACTION_ARGS:
			self.assertIn(spec.usage(action), entry["description"])


class TestValidation(unittest.TestCase):
	def test_valid_full_and_minimal_args_pass_for_every_action(self):
		for action in spec.ACTION_ARGS:
			for only_required in (False, True):
				with self.subTest(action=action, only_required=only_required):
					spec.validate(action, _sample_args(action, only_required=only_required))

	def test_unknown_argument_refused_with_valid_names(self):
		for action in spec.ACTION_ARGS:
			with self.subTest(action=action):
				with self.assertRaises(tool.Refused) as cm:
					spec.validate(action, {**_sample_args(action), "bogus_arg": 1})
				p = cm.exception.payload
				self.assertEqual(p["error"], "invalid_argument")
				self.assertIn("unknown argument 'bogus_arg'", p["message"])
				self.assertEqual(p["valid_arguments"], list(spec.ACTION_ARGS[action]))
				for name in spec.ACTION_ARGS[action]:
					self.assertIn(name, p["message"])

	def test_missing_required_argument_refused(self):
		for action, args in spec.ACTION_ARGS.items():
			for name in [n for n, r in args.items() if r]:
				with self.subTest(action=action, missing=name):
					given = _sample_args(action)
					given.pop(name)
					with self.assertRaises(tool.Refused) as cm:
						spec.validate(action, given)
					self.assertIn(name, cm.exception.payload["missing_arguments"])
					given[name] = None  # an explicit null is not a value either
					with self.assertRaises(tool.Refused):
						spec.validate(action, given)

	def test_wrong_type_refused(self):
		wrong = {
			"chat": True,
			"integer": "abc",
			"string": 7,
			"boolean": [1],
			"array": 3,
			"object": 3,
		}
		for action, args in spec.ACTION_ARGS.items():
			for name in args:
				with self.subTest(action=action, arg=name):
					given = _sample_args(action)
					given[name] = wrong[spec.ARG_TYPES[name][0]]
					with self.assertRaises(tool.Refused) as cm:
						spec.validate(action, given)
					self.assertEqual(cm.exception.payload["error"], "invalid_argument")
					self.assertIn(name, cm.exception.payload["message"])

	def test_string_encoded_numbers_booleans_and_json_are_accepted(self):
		spec.validate("ban", {"user_id": "5", "revoke_messages": "true", "duration_minutes": "10"})
		spec.validate("restrict", {"user_id": 5, "permissions": '{"can_send_messages": false}'})
		spec.validate("delete_business_messages", {"business_connection_id": "c", "message_ids": "1, 2"})

	def test_text_for_short_description_suggests_the_right_name(self):
		with self.assertRaises(tool.Refused) as cm:
			spec.validate("set_my_short_description", {"text": "Huf test bot"})
		self.assertIn(
			"unknown argument 'text' for set_my_short_description; use 'short_description'",
			cm.exception.payload["message"],
		)


class Gated(base_tests.Base):
	always_human = True

	def setUp(self):
		super().setUp()
		# business connections live in the site cache; these tests are about arguments, not the connection
		patch.object(tool, "_connection", return_value={"gateway": "gw1"}).start()
		patch.object(tool, "_business_scope").start()


class TestHandleAction(Gated):
	def test_live_bug_text_for_short_description_is_refused_before_approval(self):
		r = self.run_action("set_my_short_description", text="Huf test bot")
		self.assertFalse(r["success"])
		self.assertEqual(r["error"], "invalid_argument")
		self.assertIn("use 'short_description'", r["message"])
		self.assertIn("short_description", r["valid_arguments"])
		self.assertEqual(self.api.calls, [])  # nothing sent: no approval card, no Bot API call
		self.assertEqual(self.cache.d, {})  # no pending approval created

	def test_missing_value_never_clears_but_explicit_empty_does(self):
		for action, key, method in (
			("set_my_name", "name", "setMyName"),
			("set_my_description", "description", "setMyDescription"),
			("set_my_short_description", "short_description", "setMyShortDescription"),
		):
			self.api.calls.clear()
			self.cache.d.clear()
			r = self.run_action(action)
			self.assertEqual(r["error"], "invalid_argument", action)
			self.assertEqual(self.api.of(method), [])
			self.assertEqual(self.api.of("sendMessage"), [])
			r = self.run_action(action, **{key: ""})
			self.assertEqual(r["status"], "pending_human_approval", action)
			self.assertIn("Clear the bot", json.dumps(self.api.of("sendMessage")[-1]["payload"]["text"]))

	def test_every_action_with_valid_args_gets_past_validation(self):
		for action in spec.ACTION_ARGS:
			with self.subTest(action=action):
				r = self.run_action(action, **_sample_args(action, only_required=True))
				self.assertNotEqual(r.get("error"), "invalid_argument", r)

	def test_unknown_argument_never_reaches_a_human_for_any_action(self):
		for action in spec.ACTION_ARGS:
			with self.subTest(action=action):
				before = len(self.api.calls)
				r = self.run_action(action, **_sample_args(action, only_required=True), nonsense=1)
				self.assertEqual(r["error"], "invalid_argument")
				self.assertEqual(len(self.api.calls), before)


class TestApprovalCard(Gated):
	def card(self, action, **kw):
		self.api.calls.clear()
		self.cache.d.clear()
		r = self.run_action(action, **kw)
		self.assertEqual(r["status"], "pending_human_approval", r)
		return self.api.of("sendMessage")[-1]["payload"]["text"]

	def test_short_description_card_is_readable(self):
		text = self.card("set_my_short_description", short_description="Huf test bot")
		self.assertIn('Set the bot short description to "Huf test bot"', text)
		self.assertIn("Action: set_my_short_description | bot-wide", text)

	def test_ids_stay_visible(self):
		text = self.card("ban", user_id=5, duration_minutes=10, revoke_messages=True)
		self.assertIn("Ban user 5 for 10 minutes and delete their messages", text)
		self.assertIn(f"chat {base_tests.CHAT}", text)
		text = self.card("pin", message_id=7)
		self.assertIn("Pin message 7 silently", text)
		self.assertIn("chat", text)

	def test_card_for_every_state_changing_action_names_the_values(self):
		for action, (_g, _r, state_changing, _c) in tool.ACTIONS.items():
			if not state_changing or action == "send_business_message":
				continue
			with self.subTest(action=action):
				args = _sample_args(action)
				text = self.card(action, **args)
				self.assertNotIn(" with {", text)  # no raw JSON dump
				self.assertNotEqual(text.splitlines()[1].split(":")[0], "")


class TestPlainTelegramToolSchema(unittest.TestCase):
	"""The plain ``telegram`` tool: every argument its handlers read is declared in the registry schema."""

	INTERNAL = {"action", "gateway", "gateway_name"}  # set by the gateway layer, never by the model

	def test_every_read_argument_is_declared(self):
		from pathlib import Path

		from huf.ai.tools import telegram as tg

		src = Path(tg.__file__).read_text(encoding="utf-8")
		read = set(re.findall(r'kwargs(?:\.get|\.pop)?\(\s*"(\w+)"', src))
		read |= set(re.findall(r'kwargs\["(\w+)"\]', src))
		read |= set(re.findall(r'"(\w+)" in kwargs', src))
		(entry,) = [t for t in _registry.TELEGRAM_TOOLS if t["tool_name"] == "telegram"]
		declared = {p["fieldname"] for p in entry["parameters"]}
		self.assertEqual(read - declared - self.INTERNAL, set())
