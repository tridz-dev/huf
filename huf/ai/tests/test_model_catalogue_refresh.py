# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Catalogue refresh guarantees (2026-10-22 refresh).

Runs without a Frappe site. Inside a bench:
	bench --site <site> run-tests --app huf --module huf.ai.tests.test_model_catalogue_refresh
Without Frappe installed (huf/__init__ imports frappe, so run it as a script):
	python huf/ai/tests/test_model_catalogue_refresh.py -v

The sync module is exercised against an in-memory stand-in for the small
slice of the frappe API it uses, so the patch's idempotency and its
never-delete-referenced-models rule (refresh patch) are checked without a database.
"""

import ast
import importlib
import importlib.util
import sys
import types
import unittest
from pathlib import Path

HUF_PKG = Path(__file__).resolve().parents[2]  # .../huf (the python package)
REPO = HUF_PKG.parent


def _ensure_huf_importable():
	"""Make ``huf.ai.*`` importable even when frappe (needed by huf/__init__) is absent."""
	try:
		import huf.ai  # noqa: F401

		return
	except ImportError:
		pass
	for name, path in (("huf", HUF_PKG), ("huf.ai", HUF_PKG / "ai")):
		mod = types.ModuleType(name)
		mod.__path__ = [str(path)]
		sys.modules[name] = mod


_ensure_huf_importable()
catalogue = importlib.import_module("huf.ai.model_catalogue")
MODELS, RETIRED = catalogue.MODELS, catalogue.RETIRED
BY_NAME = {m["model_name"]: m for m in MODELS}


# Stale names (shut down, deprecated, closed to new users, or invalid IDs) as of
# 2026-10-22 that must never be seeded again.
KNOWN_STALE = {
	"gemini-2.5-flash",
	"gemini-2.5-pro",
	"gemini-2.5-flash-lite",
	"gemini-2.5-flash-preview-tts",
	"gemini-3.5-flash",
	"gemini-3.7-flash",
	"text-embedding-004",
	"gemini-3.5-transcribe",
	"gpt-5.2-chat-latest",
	"gpt-5.3-chat-latest",
	"o4-mini",
	"o3",
	"tts-1",
	"tts-1-hd",
	"whisper-1",
	"gpt-4o-transcribe",
	"dall-e-3",
	"chatgpt-image-latest",
	"gpt-image-1",
	"claude-sonnet-4-5",
	"claude-mythos-preview",
	"groq/llama-3.3-70b-versatile",
	"groq/llama-3.1-8b-instant",
	"groq/qwen/qwen3-32b",
	"groq/playai-tts",
	"groq/meta-llama/llama-4-scout-17b-16e-instruct",
	"deepseek-chat",
	"deepseek-reasoner",
	"kimi-latest",
	"kimi-k2-thinking",
	"kimi-k2.5",
	"grok-4-1-fast",
	"grok-3-mini-latest",
	"codestral-mamba-latest",
	"pixtral-large-latest",
	"magistral-medium-latest",
	"devstral-latest",
	"sonar-reasoning",
	"sonar-reasoning-pro",
	"eleven_turbo_v2_5",
	"scribe_v1",
	"qwen3-max",
	"google/gemini-2.5-flash-lite-preview-06-17",
	"openai/chat-latest",
}

# Providers that publish latest-tracking aliases -> at least one must be seeded.
# Anthropic, Groq, Cohere, Perplexity, ElevenLabs, Moonshot (kimi-latest was
# discontinued), Bedrock and Vertex publish none (verified 2026-10-22).
PROVIDERS_WITH_ALIASES = {
	"OpenAI": {"chat-latest"},
	"Google": {"gemini-flash-latest", "gemini-pro-latest", "gemini-flash-lite-latest"},
	"Mistral": {"mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"},
	"xAI": set(),
	"DeepSeek": {"deepseek-flash"},
	"Alibaba": {"qwen-plus-latest"},
	"OpenRouter": {"~google/gemini-flash-latest", "~anthropic/claude-sonnet-latest", "openrouter/auto"},
}

# audio_service provider key -> AI Provider name (only catalogue-seeded ones).
STT_PROVIDER_KEYS = {
	"openai": "OpenAI",
	"groq": "Groq",
	"mistral": "Mistral",
	"elevenlabs": "ElevenLabs",
	"google": "Google",
	"gemini": "Google",
}


def _default_stt_models() -> dict:
	"""Read audio_service.DEFAULT_STT_MODELS without importing the module (it needs frappe)."""
	tree = ast.parse((HUF_PKG / "ai" / "audio_service.py").read_text())
	for node in tree.body:
		if isinstance(node, ast.Assign) and any(
			isinstance(t, ast.Name) and t.id == "DEFAULT_STT_MODELS" for t in node.targets
		):
			return ast.literal_eval(node.value)
	raise AssertionError("DEFAULT_STT_MODELS not found in audio_service.py")


def _seeded_name(provider: str, routed: str) -> str:
	"""Map a LiteLLM-routed default back to the stored model_name convention."""
	strip = {"Google": "gemini/", "Mistral": "mistral/", "ElevenLabs": "elevenlabs/"}.get(provider)
	if strip and routed.startswith(strip):
		return routed[len(strip) :]
	return routed


class TestCatalogueContent(unittest.TestCase):
	def test_no_stale_model_is_seeded(self):
		self.assertFalse(set(BY_NAME) & KNOWN_STALE, "a known-stale model is seeded")

	def test_alias_flags(self):
		for provider, expected in PROVIDERS_WITH_ALIASES.items():
			aliases = {
				m["model_name"] for m in MODELS if m["provider"] == provider and m.get("is_latest_alias")
			}
			self.assertTrue(aliases, f"{provider} has no latest-alias entry")
			self.assertLessEqual(expected, aliases, f"{provider} missing aliases")
		for m in MODELS:
			if m.get("is_latest_alias"):
				self.assertIs(m["is_latest_alias"], True)

	def test_no_anthropic_latest_alias_invented(self):
		# Anthropic publishes no "-latest" aliases.
		for m in MODELS:
			if m["provider"] == "Anthropic":
				self.assertNotIn("latest", m["model_name"])

	def test_stt_defaults_resolve_to_seeded_transcription_models(self):
		defaults = _default_stt_models()
		for key, provider in STT_PROVIDER_KEYS.items():
			name = _seeded_name(provider, defaults[key])
			self.assertIn(name, BY_NAME, f"STT default for {key} ({name}) is not seeded")
			model = BY_NAME[name]
			self.assertEqual(model["provider"], provider)
			self.assertIn("Transcription", model.get("modalities", "").split(","))

	def test_google_has_exactly_one_transcription_model(self):
		google = [
			m for m in MODELS if m["provider"] == "Google" and "Transcription" in m.get("modalities", "")
		]
		self.assertEqual([m["model_name"] for m in google], ["gemini-flash-latest"])

	def test_doctype_has_alias_field(self):
		import json

		meta = json.loads((HUF_PKG / "huf" / "doctype" / "ai_model" / "ai_model.json").read_text())
		fields = {f["fieldname"]: f for f in meta["fields"]}
		self.assertEqual(fields["is_latest_alias"]["fieldtype"], "Check")
		self.assertIn("is_latest_alias", meta["field_order"])


# ---------------------------------------------------------------------------
# In-memory frappe stand-in
# ---------------------------------------------------------------------------
class _LinkExistsError(Exception):
	pass


class _FakeDB:
	def __init__(self, tables, singles):
		self.tables = tables  # doctype -> {name: {field: value}}
		self.singles = singles  # doctype -> {field: value}

	def _match(self, row, filters):
		return all(row.get(k) == v for k, v in filters.items())

	def exists(self, doctype, name_or_filters):
		rows = self.tables.get(doctype, {})
		if isinstance(name_or_filters, dict):
			return any(self._match(r, name_or_filters) for r in rows.values())
		return name_or_filters in rows

	def get_value(self, doctype, name, fields, as_dict=False):
		row = self.tables[doctype][name]
		if isinstance(fields, str):
			return row.get(fields)
		return {f: row.get(f) for f in fields}

	def set_value(self, doctype, name, field, value=None, update_modified=True):
		changes = field if isinstance(field, dict) else {field: value}
		self.tables[doctype][name].update(changes)

	def get_single_value(self, doctype, field):
		return self.singles.get(doctype, {}).get(field)

	def set_single_value(self, doctype, field, value):
		self.singles.setdefault(doctype, {})[field] = value


class _FakeDoc:
	def __init__(self, fake, data):
		self.fake, self.data = fake, data
		self.flags = types.SimpleNamespace()

	def insert(self, ignore_permissions=False):
		data = dict(self.data)
		doctype = data.pop("doctype")
		if doctype == "Comment":
			self.fake.comments.append(data)
			return
		self.fake.db.tables.setdefault(doctype, {})[data["model_name"]] = data


def _make_fake_frappe(tables, singles):
	fake = types.ModuleType("frappe")
	fake.db = _FakeDB(tables, singles)
	fake.LinkExistsError = _LinkExistsError
	fake.errors_logged = []
	fake.comments = []
	fake.fail_delete = set()

	def get_all(doctype, filters=None, pluck=None, **_):
		rows = fake.db.tables.get(doctype, {})
		return [n for n, r in rows.items() if fake.db._match(r, filters or {})]

	def delete_doc(doctype, name, ignore_permissions=False):
		if name in fake.fail_delete:
			raise RuntimeError(f"simulated failure deleting {name}")
		for dt, rows in fake.db.tables.items():
			if dt == doctype:
				continue
			if any(name in r.values() for r in rows.values()):
				raise _LinkExistsError(name)
		del fake.db.tables[doctype][name]

	fake.get_all = get_all
	fake.get_doc = lambda data: _FakeDoc(fake, data)
	fake.delete_doc = delete_doc
	fake.logger = lambda *a, **k: types.SimpleNamespace(info=lambda *a, **k: None)
	fake.log_error = lambda **kw: fake.errors_logged.append(kw)
	fake.get_traceback = lambda: ""
	return fake


def _load(filename, fake):
	"""Load huf/ai/<filename> bound to ``fake`` as its ``frappe``."""
	saved = sys.modules.get("frappe")
	sys.modules["frappe"] = fake
	try:
		spec = importlib.util.spec_from_file_location(
			f"_huf_{filename[:-3]}_under_test", HUF_PKG / "ai" / filename
		)
		module = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(module)
		return module
	finally:
		if saved is not None:
			sys.modules["frappe"] = saved
		else:
			sys.modules.pop("frappe", None)


def _site():
	tables = {
		"AI Model": {
			"gemini-2.5-flash": {"model_name": "gemini-2.5-flash", "provider": "Google"},
			"groq/playai-tts": {"model_name": "groq/playai-tts", "provider": "Groq"},
			"deepseek-chat": {"model_name": "deepseek-chat", "provider": "DeepSeek"},
			# Pre-existing alias row without the Transcription modality or flag.
			"gemini-flash-latest": {
				"model_name": "gemini-flash-latest",
				"provider": "Google",
				"modalities": "Text,Vision",
			},
			"my-custom-model": {"model_name": "my-custom-model", "provider": "OpenAI"},
		},
		"Agent": {
			"Bench Agent": {"model": "gemini-2.5-flash"},
			"DeepSeek Agent": {"model": "deepseek-chat"},
			"Custom Agent": {"model": "my-custom-model"},
		},
		"Agent Run": {"RUN-1": {"model": "gemini-2.5-flash"}},
		"Agent Allowed Model": {
			"row-1": {"model": "groq/playai-tts", "parent": "Custom Agent", "parenttype": "Agent"}
		},
	}
	singles = {"Agent Settings": {"default_model": "gemini-2.5-flash"}}
	return tables, singles


class TestUpsertOnMigrate(unittest.TestCase):
	def setUp(self):
		self.tables, self.singles = _site()
		self.fake = _make_fake_frappe(self.tables, self.singles)
		self.sync = _load("model_catalogue_sync.py", self.fake)

	def test_upsert_is_additive(self):
		import copy

		agents_before = copy.deepcopy(self.tables["Agent"])
		self.sync.upsert_models()
		models = self.tables["AI Model"]
		for m in MODELS:
			self.assertIn(m["model_name"], models)
		# Never deletes or repoints: stale and custom rows and agents untouched.
		for name in ("gemini-2.5-flash", "groq/playai-tts", "deepseek-chat", "my-custom-model"):
			self.assertIn(name, models)
		self.assertEqual(self.tables["Agent"], agents_before)
		self.assertEqual(self.singles["Agent Settings"]["default_model"], "gemini-2.5-flash")
		alias = models["gemini-flash-latest"]
		self.assertEqual(alias["is_latest_alias"], 1)
		self.assertEqual(alias["modalities"], "Text,Vision,Transcription")
		self.assertEqual(self.fake.errors_logged, [])

	def test_upsert_idempotent(self):
		import copy

		first = self.sync.upsert_models()
		self.assertGreater(first["inserted"], 0)
		snap = copy.deepcopy(self.tables)
		second = self.sync.upsert_models()
		self.assertEqual(self.tables, snap)
		self.assertEqual(second, {"inserted": 0, "updated": 0})


# Confirmed shutdowns that the refresh patch must retire.
KNOWN_CONFIRMED_RETIRED = {
	"gemini-2.5-flash",
	"gemini-2.5-pro",
	"gemini-2.5-flash-lite",
	"text-embedding-004",
	"gpt-5.2-chat-latest",
	"dall-e-3",
	"groq/llama-3.3-70b-versatile",
	"groq/playai-tts",
	"devstral-latest",
	"grok-4-1-fast",
	"openai/chat-latest",
}
# Deprecated or unverified: no longer seeded, but must NOT be repointed/deleted.
NOT_CONFIRMED = {
	"sonar-pro",
	"sonar-reasoning",
	"sonar-reasoning-pro",
	"sonar-deep-research",
	"deepseek-chat",
	"deepseek-reasoner",
	"deepseek-r1",
	"moonshot-v1-8k",
	"kimi-latest",
	"kimi-k2.5",
	"kimi-k2-thinking",
	"kimi-k2.7",
	"qwen-turbo-latest",
	"qwen3-max",
	"grok-3-mini-latest",
	"gpt-4.1",
	"gpt-4.1-mini",
	"gpt-4o",
	"o3",
	"o4-mini",
	"tts-1",
	"whisper-1",
	"vertex_ai/gemini-3.5-flash",
	"vertex_ai/gemini-3.7-flash",
	"bedrock/amazon.titan-image-generator-v2:0",
	"gemini-3.5-transcribe",
	"openai/gpt-image-1",
	"openai/gpt-4o-mini-tts",
}


class TestRetiredMap(unittest.TestCase):
	def test_confirmed_retirements_present_and_unconfirmed_absent(self):
		self.assertFalse(KNOWN_CONFIRMED_RETIRED - set(RETIRED))
		self.assertFalse(NOT_CONFIRMED & set(RETIRED))

	def test_retired_not_seeded(self):
		self.assertFalse(set(RETIRED) & set(BY_NAME))

	def test_repoint_targets_exist_and_keep_provider(self):
		for old, (provider, new) in RETIRED.items():
			self.assertIn(new, BY_NAME, f"{old} -> {new} is not seeded")
			self.assertEqual(BY_NAME[new]["provider"], provider, f"{old} -> {new} crosses providers")

	def test_no_general_model_mapped_to_code_variant(self):
		for old, (_, new) in RETIRED.items():
			if "code" in new:
				self.assertIn("code", old, f"{old} -> {new}")

	def test_patch_registered(self):
		lines = (HUF_PKG / "patches.txt").read_text().split()
		self.assertIn("huf.patches.v1.refresh_model_catalogue", lines)


class TestRefreshPatch(unittest.TestCase):
	def setUp(self):
		self.tables, self.singles = _site()
		# Same name as a retired model but under another provider: an admin's row.
		self.tables["AI Model"]["dall-e-3"] = {"model_name": "dall-e-3", "provider": "OpenRouter"}
		self.fake = _make_fake_frappe(self.tables, self.singles)
		self.sync = _load("model_catalogue_sync.py", self.fake)
		self.retire = _load("model_catalogue_retire.py", self.fake)

	def _run(self):
		self.sync.upsert_models()
		return self.retire.retire_models()

	def test_repoints_with_comments_and_keeps_history(self):
		result = self._run()
		agents, models = self.tables["Agent"], self.tables["AI Model"]
		self.assertEqual(agents["Bench Agent"]["model"], "gemini-flash-latest")
		self.assertEqual(self.singles["Agent Settings"]["default_model"], "gemini-flash-latest")
		self.assertEqual(
			self.tables["Agent Allowed Model"]["row-1"]["model"], "groq/canopylabs/orpheus-v1-english"
		)
		# Unconfirmed retirement: untouched.
		self.assertEqual(agents["DeepSeek Agent"]["model"], "deepseek-chat")
		self.assertIn("deepseek-chat", models)
		self.assertEqual(agents["Custom Agent"]["model"], "my-custom-model")
		# History keeps gemini-2.5-flash; the unreferenced Groq model is deleted.
		self.assertIn("gemini-2.5-flash", models)
		self.assertEqual(self.tables["Agent Run"]["RUN-1"]["model"], "gemini-2.5-flash")
		self.assertNotIn("groq/playai-tts", models)
		# Provider mismatch: admin row untouched.
		self.assertIn("dall-e-3", models)
		self.assertEqual(result["kept"], ["gemini-2.5-flash"])
		self.assertEqual(result["failed"], [])

		refs = {(c["reference_doctype"], c["reference_name"]) for c in self.fake.comments}
		self.assertEqual(
			refs, {("Agent", "Bench Agent"), ("Agent", "Custom Agent"), ("Agent Settings", "Agent Settings")}
		)
		bench = next(c for c in self.fake.comments if c["reference_name"] == "Bench Agent")
		self.assertIn("gemini-2.5-flash", bench["content"])
		self.assertIn("gemini-flash-latest", bench["content"])

	def test_idempotent(self):
		import copy

		self._run()
		snap = copy.deepcopy((self.tables, self.singles, self.fake.comments))
		second = self._run()
		self.assertEqual(copy.deepcopy((self.tables, self.singles, self.fake.comments)), snap)
		self.assertEqual((second["repointed"], second["deleted"]), (0, []))

	def test_retired_model_deleted_once_history_is_gone(self):
		self._run()
		del self.tables["Agent Run"]["RUN-1"]
		self.assertIn("gemini-2.5-flash", self._run()["deleted"])

	def test_one_failing_model_does_not_stop_the_sweep(self):
		self.fake.fail_delete.add("groq/playai-tts")
		self.tables["AI Model"]["text-embedding-004"] = {
			"model_name": "text-embedding-004",
			"provider": "Google",
		}
		result = self._run()
		self.assertEqual(result["failed"], ["groq/playai-tts"])
		self.assertIn("text-embedding-004", result["deleted"])
		self.assertEqual(len(self.fake.errors_logged), 1)


if __name__ == "__main__":
	unittest.main()
