# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""``telegram`` tool argument contract: one table drives the registry schema, validation and the docs.

Also pins the behaviour fixed by F2-TOOL with full Bot API payload assertions over the fake Bot API.
"""

from __future__ import annotations

import ast
import inspect
import json
import re
import tempfile
import textwrap
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.tests.test_telegram_tools_rich import FILE_ID, Base
from huf.ai.tools import _registry
from huf.ai.tools import telegram as tool
from huf.ai.tools import telegram_tool_spec as spec

SAMPLE = {
	"chat": "-1001",
	"integer": 5,
	"number": 1.5,
	"string": "x",
	"boolean": True,
	"array": ["a", "b"],
	"object": {"inline_keyboard": [[{"text": "Go", "url": "https://x.test"}]]},
}
WRONG = {
	"chat": [1],
	"integer": "abc",
	"number": "abc",
	"string": 5,
	"boolean": "maybe",
	"array": 5,
	"object": 5,
}
# Template actions and the gateway argument are owned by the template handlers (F9).
TEMPLATE_ACTIONS = ("send_template", "list_templates", "preview_template")
KEYBOARD = {"inline_keyboard": [[{"text": "Go", "url": "https://x.test"}]]}


def _registry_params() -> dict[str, dict]:
	(entry,) = [t for t in _registry.TELEGRAM_TOOLS if t["tool_name"] == "telegram"]
	return {p["fieldname"]: p for p in entry["parameters"]}


def _sample(action: str, *, only_required: bool = False) -> dict:
	out = {}
	for name, required in spec.ACTION_ARGS[action].items():
		if only_required and not required:
			continue
		out[name] = SAMPLE[spec.ARG_TYPES[name][0]]
	if "parse_mode" in out:
		out["parse_mode"] = "HTML"
	return out


def _dispatch_actions() -> set[str]:
	block = (
		inspect.getsource(tool.handle_action)
		.split("dispatch = {", 1)[1]
		.split("handler = dispatch.get", 1)[0]
	)
	return set(re.findall(r'"(\w+)": _handle_', block))


_READERS = (
	"_resolve_chat_id",
	"_chat_or_error",
	"_common_kw",
	"_more_kw",
	"_build_message_payload",
	"_send_media_action",
	"_need_message",
	"_forward_or_copy",
	"_markup",
	"_parse_mode",
	"_inline_markup",
	"_edit_payload",
	"_idempotency_key",
	"_scope_refusal",
	"_scoped_dispatch",
	"_record_tool_send",
)


def _names_read(func) -> set[str]:
	"""Argument names a function reads from ``kwargs``: .get/.pop/[] with a literal, loops over literal tuples,
	and the media kind literal passed to ``_send_media_action``."""
	found: set[str] = set()
	for node in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(func)))):
		if isinstance(node, ast.Call) and node.args:
			f = node.func
			first = node.args[0]
			if (
				isinstance(f, ast.Attribute)
				and f.attr in ("get", "pop")
				and getattr(f.value, "id", "") == "kwargs"
			):
				if isinstance(first, ast.Constant) and isinstance(first.value, str):
					found.add(first.value)
			if isinstance(f, ast.Name) and f.id == "_send_media_action" and isinstance(first, ast.Constant):
				found.add(first.value)
		if isinstance(node, ast.Subscript) and getattr(node.value, "id", "") == "kwargs":
			if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
				found.add(node.slice.value)
		if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple):
			found |= {
				e.value for e in node.iter.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)
			}
	return found


class TestDeclaration(unittest.TestCase):
	def test_every_action_declared_once_and_dispatched(self):
		self.assertEqual(set(spec.ACTION_ARGS), _dispatch_actions())

	def test_registry_action_enum_is_the_table(self):
		self.assertEqual(
			_registry_params()["action"]["description"].split("One of: ", 1)[1].split("|"),
			list(spec.ACTION_ARGS),
		)

	def test_every_argument_has_a_type_and_description(self):
		for action, args in spec.ACTION_ARGS.items():
			for name in args:
				self.assertIn(name, spec.ARG_TYPES, f"{action}.{name}")
		declared = {n for a in spec.ACTION_ARGS.values() for n in a}
		self.assertEqual(set(spec.ARG_TYPES), declared, "an argument type nothing uses")

	def test_registry_declares_every_argument_with_the_right_type_and_users(self):
		params = _registry_params()
		declared = {n for a in spec.ACTION_ARGS.values() for n in a}
		self.assertEqual(set(params), declared | {"action"})
		for name, (kind, _desc) in spec.ARG_TYPES.items():
			self.assertEqual(params[name]["type"], "string" if kind == "chat" else kind, name)
		for action, args in spec.ACTION_ARGS.items():
			for name in args:
				self.assertIn(action, params[name]["description"], f"{name} must say it is used by {action}")
		for name, row in params.items():
			if name != "action":
				self.assertFalse(row["required"], name)  # the action decides what is required

	def test_internal_arguments_are_not_model_visible(self):
		self.assertFalse(set(spec.INTERNAL_ARGS) & set(_registry_params()))

	def test_dead_and_accidental_arguments_are_gone(self):
		params = set(_registry_params())
		for gone in (
			"notify",
			"name",
			"icon_color",
			"icon_custom_emoji_id",
			"message",
			"file",
			"file_url",
			"limit_page_length",
			"gateway_name",
		):
			self.assertNotIn(gone, params)
		self.assertNotIn("pin", _registry_params()["message_id"]["description"].lower())

	def test_handlers_read_exactly_the_declared_arguments(self):
		declared = {n for a in spec.ACTION_ARGS.values() for n in a}
		template_only = {
			n
			for n in declared
			if all(a in TEMPLATE_ACTIONS for a in spec.ACTION_ARGS if n in spec.ACTION_ARGS[a])
		}
		read: set[str] = set()
		for name, func in vars(tool).items():
			if name.startswith("_handle_") and name not in {f"_handle_{a}" for a in TEMPLATE_ACTIONS}:
				read |= _names_read(func)
		for name in _READERS:
			read |= _names_read(getattr(tool, name))
		read -= {"action"}
		self.assertEqual(
			read - declared - set(spec.INTERNAL_ARGS), set(), "a handler reads an undeclared argument"
		)
		self.assertEqual(declared - read - template_only, set(), "declared but never read")

	def test_tool_description_lists_every_action_usage(self):
		(entry,) = [t for t in _registry.TELEGRAM_TOOLS if t["tool_name"] == "telegram"]
		for action in spec.ACTION_ARGS:
			self.assertIn(spec.usage(action), entry["description"])

	def test_sends_and_chat_actions_derive_from_the_table(self):
		self.assertIs(tool.SEND_ACTIONS, spec.SEND_ACTIONS)
		self.assertIs(tool.CHAT_ACTIONS, spec.CHAT_ACTIONS)
		self.assertLessEqual(spec.SEND_ACTIONS, spec.CHAT_ACTIONS)
		for gone in ("get_me", "get_updates", "get_file", "answer_callback_query"):
			self.assertNotIn(gone, spec.CHAT_ACTIONS)

	def test_reply_markup_description_names_the_actions_and_callback_rule(self):
		desc = _registry_params()["reply_markup"]["description"]
		used = spec.TABLE.used_by("reply_markup")
		self.assertIn("send_message", used)
		self.assertNotIn("send_media_group", used)
		self.assertIn(f"Used by: {', '.join(used)}.", desc)
		self.assertIn("only work inside a Telegram gateway conversation", desc)
		self.assertIn("omit it to remove them", desc)

	def test_voice_formats_are_stated_once(self):
		(entry,) = [t for t in _registry.TELEGRAM_TOOLS if t["tool_name"] == "telegram"]
		self.assertNotIn("OGG/Opus voice note", entry["description"])
		self.assertIn(spec.VOICE_FORMATS, _registry_params()["voice"]["description"])

	def test_handle_action_docstring_has_no_markdown_default(self):
		doc = tool.handle_action.__doc__
		self.assertNotIn("(default)", doc)
		self.assertIn("Omitted means plain text", doc)


class TestValidation(unittest.TestCase):
	def test_valid_full_and_minimal_args_pass_for_every_action(self):
		for action in spec.ACTION_ARGS:
			for only_required in (False, True):
				with self.subTest(action=action, only_required=only_required):
					spec.validate(action, _sample(action, only_required=only_required))

	def test_internal_arguments_are_accepted_everywhere(self):
		internal = dict.fromkeys(spec.INTERNAL_ARGS, "x")
		for action in spec.ACTION_ARGS:
			with self.subTest(action=action):
				spec.validate(action, {**_sample(action, only_required=True), **internal})

	def test_unknown_argument_refused_with_valid_names(self):
		for action in spec.ACTION_ARGS:
			with self.subTest(action=action):
				with self.assertRaises(spec.ArgumentRefusal) as cm:
					spec.validate(action, {**_sample(action), "bogus_arg": 1})
				exc = cm.exception
				self.assertEqual(exc.code, "invalid_argument")
				self.assertIn("unknown argument 'bogus_arg'", exc.message)
				self.assertEqual(exc.extra["valid_arguments"], list(spec.ACTION_ARGS[action]))
				for name in spec.ACTION_ARGS[action]:
					self.assertIn(name, exc.message)

	def test_missing_required_argument_refused(self):
		for action, args in spec.ACTION_ARGS.items():
			for name, required in args.items():
				if not required:
					continue
				with self.subTest(action=action, missing=name):
					given = {k: v for k, v in _sample(action, only_required=True).items() if k != name}
					with self.assertRaises(spec.ArgumentRefusal) as cm:
						spec.validate(action, given)
					self.assertEqual(cm.exception.extra["missing_arguments"], [name])

	def test_wrong_type_refused_naming_the_argument(self):
		for action, args in spec.ACTION_ARGS.items():
			for name in args:
				with self.subTest(action=action, argument=name):
					given = {**_sample(action, only_required=True), name: WRONG[spec.ARG_TYPES[name][0]]}
					with self.assertRaises(spec.ArgumentRefusal) as cm:
						spec.validate(action, given)
					self.assertIn(f"argument '{name}' for {action}", cm.exception.message)

	def test_parse_mode_must_be_a_known_mode(self):
		with self.assertRaises(spec.ArgumentRefusal) as cm:
			spec.validate("send_message", {"text": "x", "parse_mode": "Wiki"})
		self.assertIn("one of Markdown, HTML, MarkdownV2", cm.exception.message)

	def test_json_text_is_accepted_for_arrays_and_objects(self):
		spec.validate("send_poll", {"question": "q", "options": '["a", "b"]'})
		spec.validate("send_message", {"text": "x", "reply_markup": json.dumps(KEYBOARD)})
		with self.assertRaises(spec.ArgumentRefusal):
			spec.validate("send_poll", {"question": "q", "options": "a, b"})

	def test_generic_names_point_at_the_main_value(self):
		with self.assertRaises(spec.ArgumentRefusal) as cm:
			spec.validate("edit_message_text", {"message_id": 1, "text": "x", "message": "y"})
		self.assertIn("use 'text'", cm.exception.message)


class TestHandleAction(Base):
	def test_every_action_refuses_unknown_arguments_before_any_bot_call(self):
		for action in spec.ACTION_ARGS:
			with self.subTest(action=action):
				out = self.run_action(action=action, **_sample(action), bogus_arg=1)
				self.assertEqual(out["error"], "invalid_argument")
				self.assertEqual(out["unknown_arguments"], ["bogus_arg"])
				self.assertEqual(out["valid_arguments"], list(spec.ACTION_ARGS[action]))
		self.assertEqual(self.api.calls, [])

	def test_every_action_refuses_missing_and_mistyped_before_any_bot_call(self):
		for action, args in spec.ACTION_ARGS.items():
			for name, required in args.items():
				given = _sample(action)
				if required:
					with self.subTest(action=action, missing=name):
						given = {k: v for k, v in given.items() if k != name}
						self.assertEqual(self.run_action(action=action, **given)["missing_arguments"], [name])
				with self.subTest(action=action, wrong=name):
					given[name] = WRONG[spec.ARG_TYPES[name][0]]
					self.assertEqual(self.run_action(action=action, **given)["error"], "invalid_argument")
		self.assertEqual(self.api.calls, [])

	def test_harness_arguments_are_accepted_and_never_sent(self):
		out = self.run_action(
			action="send_message",
			chat_id="9",
			text="x",
			conversation_id="C",
			agent_run_id="R",
			agent_name="A",
			call_id="K",
			gateway="GW",
		)
		self.assertTrue(out["success"], out)
		self.assertEqual(self.payload("sendMessage"), {"chat_id": "9", "text": "x"})

	def test_unknown_action_still_lists_valid_actions(self):
		self.assertIn("Unknown action 'nuke'", self.run_action(action="nuke")["error"])

	def test_pin_unpin_and_topics_are_not_tool_actions(self):
		for action in ("pin_message", "unpin_message"):
			out = self.run_action(action=action, chat_id="9", message_id=3)
			self.assertEqual(out["error"], "unsupported_action")
			self.assertIn("telegram_admin", out["message"])
			self.assertIn("ask a chat admin", out["message"])
		out = self.run_action(action="create_forum_topic", chat_id="9", name="n")
		self.assertEqual(out["error"], "unsupported_action")
		self.assertNotIn("telegram_admin", out["message"])
		self.assertEqual(self.api.calls, [])
		for dead in (
			"_handle_pin_message",
			"_handle_unpin_message",
			"_handle_create_forum_topic",
			"_topic_action",
		):
			self.assertFalse(hasattr(tool, dead), dead)


class TestEditActions(Base):
	"""Bug 1 and 2: editing keeps the declared keyboard and parse mode."""

	def test_edit_text_sends_the_declared_reply_markup(self):
		out = self.run_action(
			action="edit_message_text", chat_id="9", message_id=5, text="new", reply_markup=KEYBOARD
		)
		self.assertTrue(out["success"], out)
		self.assertEqual(
			self.payload("editMessageText"),
			{"chat_id": "9", "message_id": 5, "text": "new", "reply_markup": KEYBOARD},
		)

	def test_edit_text_without_reply_markup_removes_the_buttons_as_documented(self):
		self.run_action(action="edit_message_text", chat_id="9", message_id=5, text="new", parse_mode="HTML")
		self.assertEqual(
			self.payload("editMessageText"),
			{"chat_id": "9", "message_id": 5, "text": "new", "parse_mode": "HTML"},
		)

	def test_edit_text_accepts_inline_keyboards_only(self):
		out = self.run_action(
			action="edit_message_text",
			chat_id="9",
			message_id=5,
			text="n",
			reply_markup={"remove_keyboard": True},
		)
		self.assertIn("inline_keyboard", out["error"])
		self.assertEqual(self.api.calls, [])

	def test_edit_caption_sends_parse_mode_and_reply_markup(self):
		out = self.run_action(
			action="edit_message_caption",
			chat_id="9",
			message_id=5,
			caption="<b>cap</b>",
			parse_mode="HTML",
			reply_markup=KEYBOARD,
		)
		self.assertTrue(out["success"], out)
		self.assertEqual(
			self.payload("editMessageCaption"),
			{
				"chat_id": "9",
				"message_id": 5,
				"caption": "<b>cap</b>",
				"parse_mode": "HTML",
				"reply_markup": KEYBOARD,
			},
		)

	def test_edit_caption_plain_and_too_long(self):
		self.run_action(action="edit_message_caption", chat_id="9", message_id=5, caption="*x*")
		self.assertEqual(
			self.payload("editMessageCaption"), {"chat_id": "9", "message_id": 5, "caption": "*x*"}
		)
		long = self.run_action(
			action="edit_message_caption",
			chat_id="9",
			message_id=5,
			caption="x" * (tool.CAPTION_MAX_CHARS + 1),
		)
		self.assertIn("at most", long["error"])
		self.assertEqual(len(self.api.calls), 1)

	def test_edit_reply_markup_replaces_or_removes(self):
		self.run_action(action="edit_message_reply_markup", chat_id="9", message_id=5, reply_markup=KEYBOARD)
		self.assertEqual(
			self.payload("editMessageReplyMarkup"),
			{"chat_id": "9", "message_id": 5, "reply_markup": KEYBOARD},
		)
		self.run_action(action="edit_message_reply_markup", chat_id="9", message_id=5)
		self.assertEqual(
			self.payload("editMessageReplyMarkup"),
			{"chat_id": "9", "message_id": 5, "reply_markup": {"inline_keyboard": []}},
		)


class TestMediaGroup(Base):
	"""Bug 3: media group parse_mode and protect_content reach the Bot API; reply_markup is not a group argument."""

	ITEMS = [
		{"type": "photo", "media": FILE_ID, "caption": "<b>a</b>"},
		{"type": "photo", "media": "https://cdn.test/b.jpg"},
	]

	def test_parse_mode_and_flags_in_payload(self):
		out = self.run_action(
			action="send_media_group",
			chat_id="9",
			items=self.ITEMS,
			parse_mode="HTML",
			protect_content=True,
			disable_notification=True,
			reply_to_message_id=3,
			message_thread_id=4,
		)
		self.assertTrue(out["success"], out)
		self.assertEqual(
			self.payload("sendMediaGroup"),
			{
				"chat_id": "9",
				"message_thread_id": 4,
				"reply_parameters": {"message_id": 3, "allow_sending_without_reply": True},
				"disable_notification": True,
				"protect_content": True,
				"media": [
					{"type": "photo", "media": FILE_ID, "caption": "<b>a</b>", "parse_mode": "HTML"},
					{"type": "photo", "media": "https://cdn.test/b.jpg"},
				],
			},
		)

	def test_without_parse_mode_captions_are_sent_plain(self):
		self.run_action(action="send_media_group", chat_id="9", items=self.ITEMS)
		self.assertEqual(
			self.payload("sendMediaGroup"),
			{
				"chat_id": "9",
				"media": [
					{"type": "photo", "media": FILE_ID, "caption": "<b>a</b>"},
					{"type": "photo", "media": "https://cdn.test/b.jpg"},
				],
			},
		)

	def test_reply_markup_is_refused_not_dropped(self):
		out = self.run_action(action="send_media_group", chat_id="9", items=self.ITEMS, reply_markup=KEYBOARD)
		self.assertEqual(out["error"], "invalid_argument")
		self.assertEqual(out["unknown_arguments"], ["reply_markup"])
		self.assertEqual(self.api.calls, [])


class TestReactionsAndIds(Base):
	"""Bug 4 and 5."""

	def test_reaction_needs_emoji_or_remove(self):
		out = self.run_action(action="set_reaction", chat_id="9", message_id=5)
		self.assertIn("emoji", out["error"])
		self.assertIn("remove=true", out["error"])
		out = self.run_action(action="set_reaction", chat_id="9", message_id=5, remove=False)
		self.assertFalse(out["success"])
		out = self.run_action(action="set_reaction", chat_id="9", message_id=5, emoji="x", remove=True)
		self.assertFalse(out["success"])
		self.assertEqual(self.api.calls, [])

	def test_reaction_payloads(self):
		self.run_action(action="set_reaction", chat_id="9", message_id=5, emoji="x", big=True)
		self.assertEqual(
			self.payload("setMessageReaction"),
			{"chat_id": "9", "message_id": 5, "reaction": [{"type": "emoji", "emoji": "x"}], "is_big": True},
		)
		self.run_action(action="set_reaction", chat_id="9", message_id="6", remove=True)
		self.assertEqual(
			self.payload("setMessageReaction"), {"chat_id": "9", "message_id": 6, "reaction": []}
		)

	def test_non_numeric_message_id_is_refused_never_sent_as_zero(self):
		for action, extra in (
			("delete_message", {}),
			("edit_message_text", {"text": "x"}),
			("edit_message_caption", {"caption": "x"}),
			("edit_message_reply_markup", {}),
			("set_reaction", {"emoji": "x"}),
			("stop_poll", {}),
			("forward_message", {"from_chat_id": "8"}),
			("copy_message", {"from_chat_id": "8"}),
		):
			with self.subTest(action=action):
				out = self.run_action(action=action, chat_id="9", message_id="abc", **extra)
				self.assertEqual(out["error"], "invalid_argument")
				self.assertIn("'message_id'", out["message"])
		self.assertEqual(self.api.calls, [])

	def test_coerce_int_never_defaults_to_zero(self):
		with self.assertRaises(ValueError):
			tool._coerce_int("abc")
		with self.assertRaises(ValueError):
			tool._coerce_int(None)
		self.assertEqual(tool._coerce_int("abc", 0), 0)
		self.assertEqual(tool._coerce_int(" 7 "), 7)

	def test_numeric_string_ids_are_sent_as_integers(self):
		self.run_action(action="delete_message", chat_id="9", message_id="12")
		self.assertEqual(self.payload("deleteMessage"), {"chat_id": "9", "message_id": 12})


class TestUpdates(Base):
	"""Bug 6."""

	def test_offset_zero_is_sent(self):
		self.run_action(action="get_updates", offset=0)
		self.assertEqual(self.payload("getUpdates"), {"offset": 0})

	def test_offset_and_limit(self):
		self.run_action(action="get_updates", offset=7, limit=500)
		self.assertEqual(self.payload("getUpdates"), {"offset": 7, "limit": 100})
		self.run_action(action="get_updates")
		self.assertEqual(self.payload("getUpdates"), {})


class TestDeclaredArguments(Base):
	"""Bug 7: arguments the handlers read are declared and reach the Bot API."""

	def test_quiz_with_several_correct_answers(self):
		out = self.run_action(
			action="send_poll",
			chat_id="9",
			question="q?",
			options=["a", "b", "c"],
			poll_type="quiz",
			correct_option_ids=[0, 2],
			allows_multiple_answers=True,
			is_anonymous=False,
			explanation="because",
			open_period=30,
		)
		self.assertTrue(out["success"], out)
		p = self.payload("sendPoll")
		self.assertEqual(p["correct_option_ids"], [0, 2])
		self.assertEqual((p["type"], p["is_anonymous"], p["open_period"]), ("quiz", False, 30))

	def test_venue_ids(self):
		self.run_action(
			action="send_venue",
			chat_id="9",
			latitude=1,
			longitude=2,
			title="T",
			address="A",
			foursquare_id="fs",
			google_place_id="gp",
		)
		p = self.payload("sendVenue")
		self.assertEqual((p["foursquare_id"], p["google_place_id"]), ("fs", "gp"))

	def test_video_dimensions(self):
		self.run_action(
			action="send_video",
			chat_id="9",
			video=FILE_ID,
			width=640,
			height=480,
			duration=9,
			supports_streaming=True,
		)
		p = self.payload("sendVideo")
		self.assertEqual(
			(p["width"], p["height"], p["duration"], p["supports_streaming"]), (640, 480, 9, True)
		)

	def test_media_arguments_belong_to_their_kind(self):
		for action, arg in (
			("send_photo", "width"),
			("send_document", "duration"),
			("send_sticker", "caption"),
		):
			out = self.run_action(action=action, chat_id="9", **{action[5:]: FILE_ID, arg: 5})
			self.assertEqual(out["error"], "invalid_argument", action)
		self.assertEqual(self.api.calls, [])

	def test_media_source_is_the_kind_argument_only(self):
		out = self.run_action(action="send_voice", chat_id="9", audio=FILE_ID)
		self.assertEqual(out["error"], "invalid_argument")
		out = self.run_action(action="send_photo", chat_id="9", file_url="https://cdn.test/a.jpg")
		self.assertEqual(out["error"], "invalid_argument")
		self.assertEqual(self.api.calls, [])


class TestVoiceFormats(Base):
	"""Bug 9: the formats the schema states are the formats the handler accepts."""

	def _file(self, mime: str):
		handle = tempfile.NamedTemporaryFile(suffix=".bin")
		handle.write(b"data")
		handle.flush()
		self.addCleanup(handle.close)
		doc = MagicMock(content_type=mime)
		doc.get_full_path.return_value = handle.name
		fake = MagicMock()
		fake.db.exists.return_value = True
		fake.get_doc.return_value = doc
		fake.has_permission.return_value = True
		return patch.object(tool, "frappe", fake)

	def test_every_stated_format_is_accepted(self):
		for mime in ("audio/ogg", "audio/mpeg", "audio/mp4", "audio/x-m4a"):
			with self.subTest(mime=mime), self._file(mime):
				self.assertTrue(self.run_action(action="send_voice", chat_id="9", voice="note")["success"])
		self.assertEqual(len(self.api.of("sendVoice")), 4)

	def test_other_formats_name_the_stated_formats(self):
		with self._file("audio/wav"):
			out = self.run_action(action="send_voice", chat_id="9", voice="note")
		self.assertFalse(out["success"])
		self.assertIn(spec.VOICE_FORMATS, out["error"])
		self.assertEqual(self.api.of("sendVoice"), [])
