"""Provider-neutral contracts for Huf messaging gateway adapters.

The SDK deliberately contains no Frappe persistence, HTTP endpoint, or provider
implementation.  Provider packages use these contracts before handing verified,
normalized events to Huf's Gateway service.
"""

from huf.ai.gateway_adapters.adapter import GatewayAdapter
from huf.ai.gateway_adapters.conformance import GatewayAdapterConformanceError, assert_adapter_conforms
from huf.ai.gateway_adapters.registry import GatewayAdapterRegistry
from huf.ai.gateway_adapters.types import (
	GatewayCapabilities,
	GatewayCredentialField,
	GatewayCredentialSchema,
	GatewayInboundRequest,
	GatewayReply,
	NormalizedGatewayEvent,
	OutboundDelivery,
)
from huf.ai.gateway_adapters.telegram import TelegramGatewayAdapter
from huf.ai.gateway_adapters.vk import VKGatewayAdapter
from huf.ai.gateway_adapters.wecom import WeComGatewayAdapter
from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter

__all__ = [
	"GatewayAdapter",
	"GatewayAdapterConformanceError",
	"GatewayAdapterRegistry",
	"GatewayCapabilities",
	"GatewayCredentialField",
	"GatewayCredentialSchema",
	"GatewayInboundRequest",
	"GatewayReply",
	"NormalizedGatewayEvent",
	"OutboundDelivery",
	"TelegramGatewayAdapter",
	"VKGatewayAdapter",
	"WeComGatewayAdapter",
	"WhatsAppGatewayAdapter",
	"assert_adapter_conforms",
]
