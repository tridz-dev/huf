"""
Voice Engine Abstraction

This module provides a unified interface for voice engines that mint and
manage realtime/composed voice sessions for Agents.

"""

import frappe
from frappe import _

from huf.ai.voice.engines.base import VoiceEngine

# Built-in engine registry. Hooked engines are merged on top per request.
_BUILTIN_ENGINES: dict[str, str] = {
	"elevenlabs_convai": "huf.ai.voice.engines.elevenlabs.ElevenLabsConvaiEngine",
	"litellm_realtime": "huf.ai.voice.engines.litellm_realtime.LitellmRealtimeEngine",
}


def _discover_engines() -> dict[str, str]:
	"""Return the merged registry of built-in + hooked voice engines.

	Built-in engines are loaded first. Each installed app may contribute
	additional engines via the ``huf_voice_engines`` hook. The hook value must
	be a dict mapping ``engine_key`` to ``dotted.path.to.Class``; Frappe merges
	dict-valued hooks into a single dict of lists, which :func:`_iter_hook_engines`
	normalises.

	Hook-provided engine keys that collide with a built-in key are skipped and
	logged as a warning so external apps cannot shadow HUF's built-ins.
	"""
	engines = dict(_BUILTIN_ENGINES)

	for app in frappe.get_installed_apps():
		for engine_key, dotted_path in _iter_hook_engines(app):
			if engine_key in _BUILTIN_ENGINES:
				frappe.logger().warning(
					_(
						"huf_voice_engines in app '{0}' tried to override built-in "
						"engine '{1}'; skipping."
					).format(app, engine_key)
				)
				continue
			if engine_key in engines:
				frappe.logger().warning(
					_(
						"huf_voice_engines in app '{0}' declares duplicate engine "
						"key '{1}'; keeping first registration."
					).format(app, engine_key)
				)
				continue
			engines[engine_key] = dotted_path

	return engines


def _iter_hook_engines(app: str):
	"""Yield ``(engine_key, dotted_path)`` declared by one app's hook.

	Frappe merges dict-valued hooks into a single dict whose values are lists
	of declared values (one per declaration). The first declaration for a key
	wins. A plain list of dicts is also accepted defensively.
	"""
	app_hooks = frappe.get_hooks("huf_voice_engines", app_name=app) or {}

	if isinstance(app_hooks, dict):
		entries = app_hooks.items()
	elif isinstance(app_hooks, list):
		entries = []
		for hook_entry in app_hooks:
			if not isinstance(hook_entry, dict):
				frappe.logger().warning(
					_("huf_voice_engines entry in app '{0}' must be a dict; got {1}").format(
						app, type(hook_entry).__name__
					)
				)
				continue
			entries.extend(hook_entry.items())
	else:
		frappe.logger().warning(
			_("huf_voice_engines entry in app '{0}' must be a dict; got {1}").format(
				app, type(app_hooks).__name__
			)
		)
		return

	for engine_key, dotted_paths in entries:
		if isinstance(dotted_paths, str):
			dotted_paths = [dotted_paths]
		if not dotted_paths:
			continue
		yield engine_key, dotted_paths[0]


def _get_engine_registry() -> dict[str, str]:
	"""Return the discovered engine registry, cached for the current request."""
	if not getattr(frappe.local, "huf_voice_engine_registry", None):
		frappe.local.huf_voice_engine_registry = _discover_engines()
	return frappe.local.huf_voice_engine_registry


def get_engine_class(engine_key: str) -> type[VoiceEngine]:
	"""Resolve an engine's class by key, without instantiating it.

	Use this when only the class-level metadata (``key``/``label``/``kind``) or
	``get_config_schema()`` is needed — constructing an engine may be expensive,
	and an engine is free to require constructor arguments.
	"""
	engines = _get_engine_registry()

	if engine_key not in engines:
		frappe.throw(_("Unknown voice engine: {0}").format(engine_key))

	dotted_path = engines[engine_key]
	engine_class = frappe.get_attr(dotted_path)

	if not isinstance(engine_class, type) or not issubclass(engine_class, VoiceEngine):
		frappe.throw(
			_("Voice engine '{0}' ({1}) must be a subclass of VoiceEngine.").format(
				engine_key, dotted_path
			)
		)

	return engine_class


def get_engine(engine_key: str) -> VoiceEngine:
	"""Get an instantiated engine by key."""
	return get_engine_class(engine_key)()


def supported_engines() -> list[str]:
	"""Return the list of discovered engine keys."""
	return list(_get_engine_registry().keys())
