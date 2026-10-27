# Modules listed in MODULES are imported once by hooks.register_all(); each
# module registers its own gateway hook handlers at import time. The
# coordinator owns this list. Entries are dotted module names.
MODULES = (
	"huf.ai.gateways.reliability",
	"huf.ai.gateways.identity",
	"huf.ai.gateways.safety",
	"huf.ai.gateways.health",
	"huf.ai.gateways.privacy",
)
