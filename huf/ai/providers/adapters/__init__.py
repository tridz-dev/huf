import frappe
from huf.ai.providers.adapters.base import BaseSubscriptionAdapter
from huf.ai.providers.adapters.mock import MockSubscriptionAdapter
from huf.ai.providers.adapters.openai import OpenAISubscriptionAdapter
from huf.ai.providers.adapters.openai_community import OpenAICommunitySubscriptionAdapter
from huf.ai.providers.adapters.kimi_community import KimiCommunitySubscriptionAdapter

ADAPTER_REGISTRY = {
    "mock_subscription": MockSubscriptionAdapter,
    "openai_subscription": OpenAISubscriptionAdapter,
    "openai_community_subscription": OpenAICommunitySubscriptionAdapter,
    "kimi_community_subscription": KimiCommunitySubscriptionAdapter,
}

def get_adapter(adapter_type: str) -> BaseSubscriptionAdapter:
    if adapter_type in ADAPTER_REGISTRY:
        adapter_cls = ADAPTER_REGISTRY[adapter_type]
        return adapter_cls()

    frappe.throw(f"Subscription adapter type '{adapter_type}' is not registered.")
