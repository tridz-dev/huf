# Copyright (c) 2026, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Provider-Aware Reasoning Layer Primitive

Translates portable Agent reasoning policies (mode, effort, budget_tokens, summary)
into provider-native parameters for LiteLLM (OpenAI reasoning_effort, Anthropic thinking, etc.),
while detecting capabilities and recording resolution/fallback telemetry.
"""

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional
import json
import frappe
import litellm


@dataclass
class ReasoningPolicy:
    """Portable user/agent reasoning intent."""
    mode: str = "auto"          # "auto", "off", "on"
    effort: str = "auto"        # "auto", "low", "medium", "high"
    budget_tokens: Optional[int] = None
    summary: str = "none"       # "none", "concise", "detailed"

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ReasoningPolicy":
        if not data:
            return cls()
        return cls(
            mode=str(data.get("reasoning_mode") or data.get("mode") or "auto").lower(),
            effort=str(data.get("reasoning_effort") or data.get("effort") or "auto").lower(),
            budget_tokens=data.get("reasoning_budget_tokens") or data.get("budget_tokens"),
            summary=str(data.get("reasoning_summary") or data.get("summary") or "none").lower(),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "effort": self.effort,
            "budget_tokens": self.budget_tokens,
            "summary": self.summary,
        }


@dataclass
class ReasoningCapabilities:
    """Model/Provider capability metadata."""
    supports_reasoning: bool = False
    supports_thinking_blocks: bool = False
    supported_efforts: List[str] = field(default_factory=lambda: ["low", "medium", "high"])
    raw_override: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supports_reasoning": self.supports_reasoning,
            "supports_thinking_blocks": self.supports_thinking_blocks,
            "supported_efforts": self.supported_efforts,
            "raw_override": self.raw_override,
        }


@dataclass
class ReasoningResolution:
    """Structured result of reasoning policy resolution."""
    requested: Dict[str, Any]
    resolved: Dict[str, Any]
    fallback: Optional[Dict[str, Any]] = None
    provider: str = ""
    model_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requested": self.requested,
            "resolved": self.resolved,
            "fallback": self.fallback,
            "provider": self.provider,
            "model_name": self.model_name,
        }


def detect_model_capabilities(
    model_name: str,
    provider: Optional[str] = None,
    ai_model_doc: Optional[Any] = None,
) -> ReasoningCapabilities:
    """
    Detect reasoning capabilities for a given model using LiteLLM inspection
    and optional AI Model doc overrides.
    """
    supports_reasoning = False
    supports_thinking_blocks = False
    raw_override = None

    # Check AI Model DocType overrides if provided
    if ai_model_doc:
        if getattr(ai_model_doc, "supports_reasoning", None):
            supports_reasoning = True
        if getattr(ai_model_doc, "reasoning_config_override", None):
            try:
                raw_override = json.loads(ai_model_doc.reasoning_config_override) if isinstance(ai_model_doc.reasoning_config_override, str) else ai_model_doc.reasoning_config_override
            except Exception:
                pass

    # Check LiteLLM automatic detection if not explicitly set by admin doc
    if not supports_reasoning and model_name:
        try:
            supports_reasoning = bool(litellm.supports_reasoning(model=model_name))
        except Exception:
            # Fallback heuristic based on model names
            mn = model_name.lower()
            if any(k in mn for k in ("o1", "o3", "deepseek-r1", "claude-3-7", "gemini-2.0-flash-thinking", "grok-3")):
                supports_reasoning = True

    # Determine provider family for thinking blocks (e.g. Anthropic)
    prov_lower = (provider or "").lower()
    mn_lower = (model_name or "").lower()
    if "anthropic" in prov_lower or "claude" in mn_lower:
        supports_thinking_blocks = True

    if raw_override and isinstance(raw_override, dict):
        if "supports_reasoning" in raw_override:
            supports_reasoning = bool(raw_override["supports_reasoning"])
        if "supports_thinking_blocks" in raw_override:
            supports_thinking_blocks = bool(raw_override["supports_thinking_blocks"])

    return ReasoningCapabilities(
        supports_reasoning=supports_reasoning,
        supports_thinking_blocks=supports_thinking_blocks,
        raw_override=raw_override,
    )


def resolve_reasoning(
    policy: ReasoningPolicy,
    capabilities: ReasoningCapabilities,
    provider: str = "",
    model_name: str = "",
) -> ReasoningResolution:
    """
    Resolve requested portable reasoning policy into native LiteLLM parameters.
    """
    requested_dict = policy.to_dict()
    resolved_native: Dict[str, Any] = {}
    fallback: Optional[Dict[str, Any]] = None

    prov_lower = (provider or "").lower()
    mn_lower = (model_name or "").lower()
    is_anthropic = "anthropic" in prov_lower or "claude" in mn_lower

    if policy.mode == "off":
        return ReasoningResolution(
            requested=requested_dict,
            resolved={},
            fallback=None,
            provider=provider,
            model_name=model_name,
        )

    # If explicit reasoning mode ON, but model does not support reasoning
    if policy.mode == "on" and not capabilities.supports_reasoning:
        fallback = {
            "reason": "model_does_not_support_reasoning",
            "action": "disabled",
        }
        return ReasoningResolution(
            requested=requested_dict,
            resolved={},
            fallback=fallback,
            provider=provider,
            model_name=model_name,
        )

    # Mode is "on" or "auto" (and model supports reasoning if mode is auto)
    if policy.mode in ("on", "auto") and capabilities.supports_reasoning:
        if is_anthropic:
            budget = policy.budget_tokens or 4096
            resolved_native["thinking"] = {
                "type": "enabled",
                "budget_tokens": budget,
            }
            # For Anthropic thinking, modify_params helps handle missing blocks gracefully
            resolved_native["modify_params"] = True
        else:
            # Standard OpenAI / DeepSeek / LiteLLM reasoning_effort
            if policy.effort in ("low", "medium", "high"):
                if policy.effort in capabilities.supported_efforts:
                    resolved_native["reasoning_effort"] = policy.effort
                elif capabilities.supported_efforts:
                    # Requested effort isn't supported by this model; fall back to
                    # its closest supported tier instead of silently sending an
                    # unsupported value.
                    resolved_native["reasoning_effort"] = capabilities.supported_efforts[
                        len(capabilities.supported_efforts) // 2
                    ]
            elif policy.mode == "on":
                resolved_native["reasoning_effort"] = (
                    "medium" if "medium" in capabilities.supported_efforts else capabilities.supported_efforts[0]
                ) if capabilities.supported_efforts else "medium"

            if policy.summary in ("concise", "detailed"):
                resolved_native["reasoning_summary"] = policy.summary

    return ReasoningResolution(
        requested=requested_dict,
        resolved=resolved_native,
        fallback=fallback,
        provider=provider,
        model_name=model_name,
    )


def build_reasoning_kwargs(resolution: ReasoningResolution) -> Dict[str, Any]:
    """
    Produce clean completion_kwargs dict from a ReasoningResolution.
    """
    if not resolution or not resolution.resolved:
        return {}
    
    kwargs = {}
    resolved = resolution.resolved
    
    if "reasoning_effort" in resolved:
        kwargs["reasoning_effort"] = resolved["reasoning_effort"]
    if "thinking" in resolved:
        kwargs["thinking"] = resolved["thinking"]
    if "modify_params" in resolved:
        kwargs["modify_params"] = resolved["modify_params"]
    if "reasoning_summary" in resolved:
        kwargs["reasoning_summary"] = resolved["reasoning_summary"]
        
    return kwargs
