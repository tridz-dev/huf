"""Handoff adapters: how a handed-off WhatsApp conversation reaches a human tool (Helpdesk, CRM, ERPNext).

An adapter subclasses :class:`ChannelAdapter` and is registered by dotted module path in
``ADAPTER_MODULES`` (the module exposes ``Adapter``). Concrete adapters live in their own modules and
plug in by adding one entry here; a missing module or an app that is not installed falls back to
:class:`NoneAdapter` with a logged warning.
"""

from __future__ import annotations

from typing import Any

import frappe

# target name -> dotted module path exposing ``Adapter``. Concrete adapter WPs append here.
ADAPTER_MODULES: dict[str, str] = {}
# target name -> Frappe app that must be installed for the adapter to be used.
TARGET_APPS: dict[str, str] = {"helpdesk": "helpdesk", "crm": "crm", "erpnext": "erpnext"}
# linked-document doctype -> target, to find the adapter of an already handed-off conversation.
DOCTYPE_TARGETS: dict[str, str] = {"HD Ticket": "helpdesk", "CRM Lead": "crm", "CRM Deal": "crm", "Opportunity": "erpnext"}

PRIORITIES = ("low", "normal", "high", "urgent")


class ChannelAdapter:
	"""Adapter interface. Subclasses override what their target supports."""

	name = "none"

	def handoff(self, conversation, summary: str = "", priority: str = "normal") -> tuple[str | None, str | None]:
		"""Create/attach the human-side record; return ``(doctype, name)`` (``(None, None)`` for none)."""
		return None, None

	def lookup_customer(self, phone: str) -> dict[str, Any] | None:
		"""Return the customer record matching ``phone`` (``{doctype, name, ...}``) or None."""
		return None

	def append_inbound(self, conversation, text: str, event: str | None = None) -> None:
		"""Add an inbound customer message to the linked document of a handed-off conversation."""
		return None

	def on_human_reply(self, doc, conversation) -> bool:
		"""A human replied on the linked document. Return True when the adapter delivered it itself;
		False lets the default Communication hook send it through ``send_reply``."""
		return False


class NoneAdapter(ChannelAdapter):
	"""No linked document: the handoff is only a status change."""

	name = "none"


def register_adapter(target: str, module_path: str, app: str | None = None) -> None:
	ADAPTER_MODULES[target] = module_path
	if app:
		TARGET_APPS[target] = app


def _app_installed(app: str | None) -> bool:
	return not app or app in frappe.get_installed_apps()


def adapter_available_for_app(app: str) -> bool:
	"""True when some registered target is backed by ``app`` and its module is importable."""
	for target, target_app in TARGET_APPS.items():
		if target_app == app and target in ADAPTER_MODULES and _load(target) is not None:
			return True
	return False


def _load(target: str) -> ChannelAdapter | None:
	path = ADAPTER_MODULES.get(target)
	if not path:
		return None
	try:
		return frappe.get_module(path).Adapter()
	except Exception:
		return None


def get_adapter(target: str | None) -> ChannelAdapter:
	"""Adapter for ``target``; ``none``/unknown/missing/app-not-installed -> :class:`NoneAdapter` (warning logged)."""
	target = (target or "none").strip().lower()
	if target == "none":
		return NoneAdapter()
	if not _app_installed(TARGET_APPS.get(target)):
		frappe.logger("huf").warning(f"Channel handoff target '{target}': app not installed, using 'none'")
		return NoneAdapter()
	adapter = _load(target)
	if adapter is None:
		frappe.logger("huf").warning(f"Channel handoff target '{target}': no adapter available, using 'none'")
		return NoneAdapter()
	return adapter


def adapter_for_conversation(conversation) -> ChannelAdapter:
	"""Adapter of a handed-off conversation: by its linked doctype, else the gateway's handoff target."""
	target = DOCTYPE_TARGETS.get(conversation.get("handoff_doctype") or "")
	if not target and conversation.get("handoff_doctype"):
		return NoneAdapter()
	if not target and conversation.get("gateway"):
		target = frappe.db.get_value("Gateway", conversation.get("gateway"), "handoff_target")
	return get_adapter(target)

ADAPTER_MODULES["crm"] = "huf.ai.channels.adapters.crm"
