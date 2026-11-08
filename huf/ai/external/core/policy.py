from __future__ import annotations

READ_TOOL_TYPES = frozenset(
	{
		"Get List",
		"Get Document",
		"Get Multiple Documents",
		"Get Value",
		"Get Report Result",
		"GET",
		"Get Conversation Data",
		"Load Conversation Data",
		"Search Memory Records",
		"Get Memory Record",
		"Perplexity Search",
	}
)

COMMUNICATE_TOOL_TYPES = frozenset({"Send Email", "POST"})

COMMUNICATE_PATH_HINTS = (
	"whatsapp",
	"telegram",
	"slack",
	"email",
	"messenger",
	"gmail",
	"discord",
	"teams",
	"raven",
	"google_chat",
	"helpdesk",
)

ALLOW = "Allow"
REQUIRES_APPROVAL = "Requires Approval"
DENY = "Deny"

_DECISIONS = {
	ALLOW: "allow",
	REQUIRES_APPROVAL: "approve",
	DENY: "deny",
}


def classify_tool(tool_type: str | None, function_path: str | None = None) -> str:
	"""Return "read", "write" or "communicate" for a tool.

	Unknown or missing tool types are treated as "write", never "read".
	"""
	if tool_type in COMMUNICATE_TOOL_TYPES:
		return "communicate"
	# Path hints are plain substring matches, so they can over-match. That is deliberate:
	# a hinted path is classed as "communicate" even when the tool type says read or write,
	# so a false positive lands on the stricter policy (deny by default) rather than letting
	# an outbound message slip through as a read or an ordinary write.
	if function_path:
		path = function_path.lower()
		if any(hint in path for hint in COMMUNICATE_PATH_HINTS):
			return "communicate"
	if tool_type in READ_TOOL_TYPES:
		return "read"
	return "write"


def decide(policy: dict, action_class: str) -> str:
	"""Return "allow", "approve" or "deny" for an action class under a policy.

	Missing keys, unknown classes and unknown policy values resolve to "deny".
	"""
	if not isinstance(policy, dict):
		return "deny"
	value = policy.get(f"{action_class}_policy")
	if not isinstance(value, str):
		return "deny"
	return _DECISIONS.get(value, "deny")
