from types import SimpleNamespace

from huf.ai.decision.persistence import make_frappe_telemetry_sink
from huf.ai.decision.telemetry import DecisionCall
from huf.ai.decision.types import DecisionIdentity, DecisionUsage


def test_frappe_sink_persists_normalized_identity_and_usage():
    calls = []
    frappe = SimpleNamespace(get_doc=lambda values: SimpleNamespace(insert=lambda **kwargs: calls.append((values, kwargs))))
    call = DecisionCall(
        status="success", policy_id="support_urgency", policy_version="v1", policy_fingerprint="abc123",
        surface="playground", backend_adapter="jev_system_one",
        requested_identity=DecisionIdentity(canonical_model="Jev 1.13"),
        resolved_identity=DecisionIdentity(canonical_model="Jev 1.13", canonical_version="1.13", provider="OpenCode Zen", deployment="Jev 1.13 Free @ OpenCode Zen", provider_model_id="jev-1.13-free"),
        requested_model="Jev 1.13", requested_model_version="1.13", resolved_model="Jev 1.13", resolved_model_version="1.13",
        candidate_ids=(), candidate_source=None, candidate_resolver_id=None,
        answers={"is_urgent": {"value": True}}, usage=DecisionUsage(input_tokens=10, output_tokens=2),
    )
    make_frappe_telemetry_sink(frappe_module=frappe)(call)
    values, kwargs = calls[0]
    assert values["decision_model"] == "Jev 1.13"
    assert values["decision_provider"] == "OpenCode Zen"
    assert values["input_tokens"] == 10
    assert kwargs == {"ignore_permissions": True}
