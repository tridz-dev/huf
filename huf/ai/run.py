import frappe
from frappe import _


async def _await_tagged(coro, provider_path):
    """Await a provider coroutine and tag the result with the path that served it.

    RunProvider.run() is itself `async def` and awaits the provider directly
    for the primary LiteLLM path (see below), so this wrapper is only used for
    the custom-provider fallback branch, where a coroutine object has no
    __dict__ and assigning `.provider_path` to it directly would raise
    AttributeError. Wrapping defers that assignment until the real result
    exists, after the coroutine has been awaited.
    """
    result = await coro
    try:
        result.provider_path = provider_path
    except (AttributeError, TypeError):
        # Marking is observability, never a reason to fail a run.
        pass
    return result


class RunProvider:
    """
    Central routing layer for AI providers.
    Routes existing providers (OpenAI, Anthropic, Google, OpenRouter) to LiteLLM
    for unified handling while maintaining backward compatibility.

    New providers can be added via LiteLLM without code changes - just create
    AI Provider and AI Model documents with the correct format.
    """

    @staticmethod
    async def run(agent, enhanced_prompt, provider, model, context=None):
        provider_lower = provider.lower()
        original_exception = None

        # 1. Default: Try to run via Unified LiteLLM Provider
        # This supports OpenAI, Anthropic, Google, and 100+ others automatically.
        try:
            from huf.ai.providers import litellm
            result = await litellm.run(agent, enhanced_prompt, provider, model, context=context)
            try:
                result.provider_path = "litellm"
            except (AttributeError, TypeError):
                # Marking is observability, never a reason to fail a run.
                pass
            return result

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
            return await _await_tagged(
                module.run(agent, enhanced_prompt, provider, model, context=context),
                "legacy_fallback",
            )
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

        Deliberately left as a plain (non-async) `def`, unlike `run()`: this does
        NOT share run()'s former unawaited-coroutine bug (see ST-R5.9). `litellm.
        run_stream()` is an `async def` function whose body contains `yield`,
        making it an async-generator function. Calling an async-generator
        function does not execute any of its body and does not need `await` --
        it synchronously returns an async-generator object, with all real work
        deferred until the caller does `async for chunk in stream`. The one
        caller (`huf/ai/agent_integration.py`, `stream = RunProvider.run_stream(...)`
        followed by `async for` over it) already consumes it that way, so no
        change is needed here.
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
