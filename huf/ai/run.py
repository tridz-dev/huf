import frappe
from frappe import _


class RunProvider:
    """
    Central routing layer for AI providers.
    Routes existing providers (OpenAI, Anthropic, Google, OpenRouter) to LiteLLM
    for unified handling while maintaining backward compatibility.

    New providers can be added via LiteLLM without code changes - just create
    AI Provider and AI Model documents with the correct format.
    """

    @staticmethod
    def run(agent, enhanced_prompt, provider, model, context=None):
        provider_lower = provider.lower()
        original_exception = None

        # 1. Default: Try to run via Unified LiteLLM Provider
        # This supports OpenAI, Anthropic, Google, and 100+ others automatically.
        try:
            from huf.ai.providers import litellm
            return litellm.run(agent, enhanced_prompt, provider, model, context=context)

        except ImportError as e:
            # Handle case where litellm package is missing
            if "litellm" in str(e):
                error_msg = (
                    "LiteLLM package is required but not installed.\n\n"
                    "To install:\n"
                    "1. Run: bench setup requirements\n"
                    "2. Or manually: pip install litellm>=1.0.0\n"
                    "3. Then restart your site: bench restart\n\n"
                    "The litellm package is listed in pyproject.toml dependencies, "
                    "so running 'bench setup requirements' should install it automatically."
                )
                frappe.log_error(
                    f"LiteLLM Import Error: {str(e)}\n\n{error_msg}",
                    "LiteLLM Provider Error",
                )
                frappe.throw(_(error_msg))
            # Some other ImportError: re-raise
            raise

        except Exception as e:
            # Generic error from LiteLLM: log it, but allow fallback to custom provider
            frappe.log_error(
                frappe.get_traceback(),
                f"LiteLLM Provider Error: {provider}",
            )
            original_exception = e

        # 2. For other providers, try to load custom provider module
        # This allows for future custom providers or gradual migration
        try:
            module_path = f"huf.ai.providers.{provider_lower}"
            module = frappe.get_module(module_path)
        except ImportError:
            # Provider module doesn't exist - suggest using LiteLLM format
            frappe.throw(
                _(
                    "Provider '{provider}' not found. "
                    "For LiteLLM-supported providers, ensure model name includes provider prefix "
                    "(e.g., 'xai/grok-4' for Grok, 'mistral/mistral-large' for Mistral)."
                ).format(provider=provider)
            )

        if not hasattr(module, "run"):
            frappe.throw(_(f"Provider {provider} is missing a run() function"))

        try:
            return module.run(agent, enhanced_prompt, provider, model, context=context)
        except Exception:
            # If custom module existed but failed, raise the original LiteLLM error if present
            if original_exception:
                raise original_exception
            raise

    @staticmethod
    def run_stream(agent, enhanced_prompt, provider, model, context=None):
        """
        Streaming version of run() - yields chunks instead of returning final result.

        Routes streaming requests to LiteLLM for supported providers.
        """
        try:
            from huf.ai.providers import litellm
            return litellm.run_stream(
                agent, enhanced_prompt, provider, model, context=context
            )
        except ImportError as e:
            error_msg = (
                "LiteLLM package is required for streaming but not installed.\n\n"
                "To install:\n"
                "1. Run: bench setup requirements\n"
                "2. Or manually: pip install litellm>=1.0.0\n"
                "3. Then restart your site: bench restart"
            )
            frappe.log_error(
                f"LiteLLM Import Error: {str(e)}\n\n{error_msg}",
                "LiteLLM Streaming Error",
            )
            frappe.throw(_(error_msg))
        except Exception as e:
            frappe.log_error(
                frappe.get_traceback(),
                f"LiteLLM Streaming Error: {provider}",
            )
            frappe.throw(_(f"Error streaming from provider {provider}: {str(e)}"))

        # For other providers, streaming not yet supported
        # frappe.throw(
        #     _("Streaming not yet supported for provider '{provider}'. "
        #       "Please use run() for non-streaming requests.").format(provider=provider)
        # )
