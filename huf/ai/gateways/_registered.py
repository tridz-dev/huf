# Modules listed in MODULES are imported once by hooks.register_all(); each
# module registers its own gateway hook handlers at import time. The
# coordinator owns this list. Entries are dotted module names.
MODULES = (
	"huf.ai.gateways.reliability",
	"huf.ai.gateways.slack.identity",
	"huf.ai.gateways.safety",
	"huf.ai.gateways.health",
	"huf.ai.gateways.slack.privacy",
	"huf.ai.gateways.slack.shortcuts",
	"huf.ai.gateways.slack.attachments",
	"huf.ai.gateways.help_feedback",
	"huf.ai.gateways.approvals",
	"huf.ai.gateways.teams.tenant",
	"huf.ai.gateways.teams.refs",
	"huf.ai.gateways.teams.identity",
	"huf.ai.gateways.teams.messaging.help",
	"huf.ai.gateways.teams.messaging.privacy",
	"huf.ai.gateways.teams.actions",
	"huf.ai.gateways.teams.identity_confirm",
)
