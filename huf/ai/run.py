import frappe
from frappe import _
from types import SimpleNamespace


class RunProvider:
    """
    Central routing layer for AI providers.
    Routes existing providers (OpenAI, Anthropic, Google, OpenRouter) to LiteLLM
    for unified handling while maintaining backward compatibility, or to native
    subscription adapters when a subscription connection is specified/active.
    """

    @staticmethod
    def _get_subscription_connection(context, provider=None, model=None):
        """
        Resolve an active AI Provider Connection for this run.

        Precedence:
        1. ``subscription_connection`` object or name passed in context.
        2. ``subscription_connection_name`` passed in context.
        3. Auto-discover an active connection for the provider + current user +
           model when none is explicitly supplied.
        """
        if not context:
            context = {}

        connection = context.get("subscription_connection")
        connection_name = context.get("subscription_connection_name")

        if not connection and connection_name:
            if frappe.db.exists("AI Provider Connection", connection_name):
                connection = frappe.get_doc("AI Provider Connection", connection_name)

        if connection:
            if isinstance(connection, str):
                if frappe.db.exists("AI Provider Connection", connection):
                    connection = frappe.get_doc("AI Provider Connection", connection)
                else:
                    return None

            if hasattr(connection, "check_and_refresh"):
                if connection.check_and_refresh():
                    return connection
                frappe.throw(
                    _(
                        "Subscription connection '{0}' is expired or inactive. Please re-authorize."
                    ).format(connection.name)
                )
            return connection

        # Auto-discover active subscription connection for provider/user/model.
        if provider:
            user = context.get("user") or frappe.session.user
            filters = {
                "provider": provider,
                "user": user,
                "is_active": 1,
            }
            connections = frappe.get_all(
                "AI Provider Connection",
                filters=filters,
                fields=["name"],
                order_by="modified desc",
                limit_page_length=10,
            )
            for conn_row in connections:
                try:
                    conn_doc = frappe.get_doc("AI Provider Connection", conn_row.name)
                except Exception:
                    continue
                if not conn_doc.is_active_connection():
                    continue
                if model and not conn_doc.matches_model(model):
                    continue
                if conn_doc.check_and_refresh():
                    return conn_doc

        return None

    @staticmethod
    def _normalize_subscription_result(result):
        """
        Convert a subscription adapter dict result into a HUF-compatible result
        object with ``final_output``, ``usage``, ``new_items`` and ``cost``.
        """
        if result is None:
            return SimpleNamespace(final_output="", usage={}, new_items=[], cost=0.0)

        if not isinstance(result, dict):
            return result

        usage = result.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}

        return SimpleNamespace(
            final_output=result.get("response", ""),
            usage=usage,
            new_items=result.get("new_items") or [],
            cost=result.get("cost", 0.0),
            metadata={k: v for k, v in result.items() if k not in ("response", "usage", "new_items", "cost")},
        )

    @staticmethod
    async def _normalize_subscription_stream(stream):
        """
        Compatibility wrapper for subscription adapters that emit raw chunks
        without a ``type`` field.  Infers HUF chunk types where possible.
        """
        full_response = ""
        async for chunk in stream:
            if not isinstance(chunk, dict):
                continue

            chunk_type = chunk.get("type")
            if not chunk_type:
                if chunk.get("finish_reason") == "stop":
                    chunk_type = "complete"
                else:
                    chunk_type = "delta"
                chunk = dict(chunk)
                chunk["type"] = chunk_type

            if chunk_type == "delta":
                full_response += chunk.get("content", "")
                chunk.setdefault("full_response", full_response)
                yield chunk
            elif chunk_type == "complete":
                chunk.setdefault("full_response", full_response)
                yield chunk
            else:
                yield chunk

    @staticmethod
    def run(agent, enhanced_prompt, provider, model, context=None):
        sub_conn = RunProvider._get_subscription_connection(context, provider, model)
        if sub_conn:
            from huf.ai.providers.adapters import get_adapter
            adapter = get_adapter(sub_conn.adapter_type)
            result = adapter.run(
                connection_doc=sub_conn,
                agent=agent,
                enhanced_prompt=enhanced_prompt,
                model=model,
                context=context,
            )
            return RunProvider._normalize_subscription_result(result)

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

        Routes streaming requests to LiteLLM for supported providers or to native
        subscription adapters when a subscription connection is specified/active.
        """
        sub_conn = RunProvider._get_subscription_connection(context, provider, model)
        if sub_conn:
            from huf.ai.providers.adapters import get_adapter
            adapter = get_adapter(sub_conn.adapter_type)
            stream = adapter.stream_response(
                connection_doc=sub_conn,
                agent=agent,
                enhanced_prompt=enhanced_prompt,
                model=model,
                context=context,
            )
            return RunProvider._normalize_subscription_stream(stream)

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
