# Modules listed in MODULES are imported once by hooks.register_all(); each
# module registers its own gateway hook handlers at import time. The
# coordinator owns this list. Entries are dotted module names.
MODULES = (
	"huf.ai.gateways.reliability",
	"huf.ai.gateways.identity",
	"huf.ai.gateways.safety",
	"huf.ai.gateways.health",
	"huf.ai.gateways.privacy",
	"huf.ai.gateways.slack_shortcuts",
	"huf.ai.gateways.help_feedback",
	"huf.ai.gateways.approvals",
	"huf.ai.gateways.teams_tenant",
	"huf.ai.gateways.teams_refs",
	"huf.ai.gateways.teams_identity",
	"huf.ai.gateways.teams_help",
	"huf.ai.gateways.teams_privacy",
	"huf.ai.gateways.teams_actions",
)
