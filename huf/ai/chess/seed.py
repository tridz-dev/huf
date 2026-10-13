"""Seeding for the HUF Chess App: Agent and HUF App manifest."""

import frappe

logger = frappe.logger("huf")

CHESS_AGENT_NAME = "HUF Chess Player"

CHESS_AGENT_INSTRUCTIONS = """You are the chess opponent in the HUF Chess app. Play to win. You will receive the current board position, game history, and the complete set of legal moves. Choose exactly one move from the supplied legal move list. Never invent a move. Return only the requested JSON. Keep commentary to one short sentence and do not reveal internal reasoning."""

CHESS_PREFERRED_MODELS = [
	"gemini-3.5-flash-lite",
	"gemini-3.1-flash-lite",
	"gemini-3.5-flash",
	"gemini-2.5-flash",
]


def _chess_model():
	"""First AI Model on the Google provider, preferring the light chat models."""
	if not frappe.db.exists("AI Provider", "Google"):
		return None

	models = frappe.get_all(
		"AI Model",
		filters={"provider": "Google"},
		pluck="name",
		order_by="creation asc",
	)
	for preferred in CHESS_PREFERRED_MODELS:
		if preferred in models:
			return preferred
	return models[0] if models else None


def create_chess_agent():
	"""
	Idempotent: seed the "HUF Chess Player" Agent.

	This agent plays chess against the user, receiving the board position,
	move history, and legal moves, and returning exactly one move plus an
	optional short comment.

	Provider/model default to the Google/Gemini AI Model records seeded by
	create_demo_ai_models(), following the same "pick a sensible default,
	never hardcode a key" convention. If no Google AI Model is configured yet,
	the agent is seeded disabled so it does not block install; it can be
	reconfigured from the Agent list once a provider/model is available.

	Safe to call on both after_install and after_migrate.
	"""
	fields = {
		"agent_name": CHESS_AGENT_NAME,
		"description": "Plays chess against you, one move at a time.",
		"prompt_mode": "Local",
		"agent_modality": "Text",
		"instructions": CHESS_AGENT_INSTRUCTIONS,
		"is_system": 1,
		"allow_chat": 0,
		"persist_conversation": 0,
		"run_immediately": 1,
		"allow_guest": 0,
	}

	model = _chess_model()
	if model:
		fields["provider"] = "Google"
		fields["model"] = model
		fields["disabled"] = 0
	else:
		fields["disabled"] = 1

	previous_in_seeding = getattr(frappe.flags, "in_seeding", False)
	frappe.flags.in_seeding = True
	try:
		if frappe.db.exists("Agent", CHESS_AGENT_NAME):
			doc = frappe.get_doc("Agent", CHESS_AGENT_NAME)
			for fieldname, value in fields.items():
				doc.set(fieldname, value)
			doc.save(ignore_permissions=True)
			return

		doc = frappe.get_doc({"doctype": "Agent", **fields})
		if not model:
			doc.flags.ignore_mandatory = True
		doc.insert(ignore_permissions=True)
	finally:
		frappe.flags.in_seeding = previous_in_seeding


def create_chess_app():
	"""
	Idempotent: seed the "Chess" HUF App manifest entry.

	Chess is a first-party huf feature, seeded directly following the same
	get_value-check-then-insert-or-update pattern used for other install.py-seeded
	primitives.

	Safe to call on both after_install and after_migrate.
	"""
	app_id = "chess"
	fields = {
		"title": "Chess",
		"description": "Play chess against an AI opponent.",
		"route": "/huf/chess",
		"category": "Play",
		"enabled": 1,
		"sync_status": "Active",
		"source_app": "huf",
		"is_public": 0,
		"agent": CHESS_AGENT_NAME,
		"delivery": "spa-deep-link",
	}

	existing_name = frappe.db.get_value("HUF App", {"app_id": app_id}, "name")
	if existing_name:
		# Same manual-override carve-out as apps_loader.upsert_huf_app: a
		# System Manager's hand-edit to enabled/is_public/agent should survive
		# re-sync on migrate, so updates never touch those fields.
		update_fields = {
			k: v
			for k, v in fields.items()
			if k not in ("enabled", "is_public", "agent")
		}
		frappe.db.set_value("HUF App", existing_name, update_fields)
		return

	doc = frappe.get_doc({"doctype": "HUF App", "app_id": app_id, **fields})
	try:
		doc.insert(ignore_permissions=True)
	except Exception as e:  # noqa: BLE001
		logger.warning(f"Failed to seed Chess HUF App: {e!s}")
