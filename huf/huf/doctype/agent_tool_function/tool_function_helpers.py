"""Static helpers for Agent Tool Function (moved verbatim from agent_tool_function.py)."""

import frappe


# OTP delivery must never be reachable by an agent (an LLM could exfiltrate or abuse codes).
OTP_TOOL_DENYLIST = [
	"huf.ai.whatsapp.otp.send_otp",
	"huf.ai.whatsapp.otp.get_otp_status",
]


def is_otp_tool_path(function_path):
	"""True when ``function_path`` is, or resolves (alias / re-export) to, an OTP function."""
	path = (function_path or "").strip()
	if not path:
		return False
	if path in OTP_TOOL_DENYLIST:
		return True
	try:
		func = frappe.get_attr(path)
	except Exception:
		return False
	return f"{getattr(func, '__module__', '')}.{getattr(func, '__name__', '')}" in OTP_TOOL_DENYLIST


# Identifier parameters the built-in document operations use (see huf/ai/tools/functions.py and
# prepare_function_params). They are arguments to the operation, not fields of the
# reference DocType, so they must not be checked against the DocType meta.
RESERVED_IDENTIFIER_PARAMS = {
	"Get Document": {"document_id"},
	"Get Multiple Documents": {"document_ids"},
	"Update Document": {"document_id"},
	"Update Multiple Documents": {"document_id"},
	"Delete Document": {"document_id"},
	"Delete Multiple Documents": {"document_ids"},
	"Submit Document": {"document_id"},
	"Cancel Document": {"document_id"},
	"Get Amended Document": {"document_id"},
	"Attach File to Document": {"document_id"},
}


def _json_schema_type(param_type):
	"""Map a stored Agent Function Params `type` value to a valid JSON Schema type.

	"float" is offered in the doctype's Select field for UX familiarity but is not a
	valid JSON Schema type (json-schema.org only defines number/integer/string/boolean/
	object/array/null); LLM providers reject or mishandle tool schemas containing it.
	"""
	if param_type == "float":
		return "number"
	return param_type
