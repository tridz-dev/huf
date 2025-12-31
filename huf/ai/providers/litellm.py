# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Unified LiteLLM Provider Implementation

This module provides a unified interface to 100+ LLM providers via LiteLLM.
It replaces the need for separate provider implementations while maintaining
100% backward compatibility with existing Huf configurations.

Features:
- Supports all LiteLLM providers (OpenAI, Anthropic, Google, OpenRouter, xAI, Mistral, etc.)
- Unified tool calling format (OpenAI-compatible)
- Built-in retry logic, cost tracking, and error handling
- Automatic model name normalization for seamless migration
"""

import asyncio
import json
import os
from types import SimpleNamespace

import frappe
import litellm
from litellm import InternalServerError, RateLimitError, APIError
from litellm import InternalServerError, RateLimitError, APIError, completion_cost
from litellm.utils import supports_prompt_caching
from huf.ai.tool_serializer import serialize_tools


class SimpleResult:
    """Result structure for provider responses"""

    def __init__(self, final_output, usage=None, new_items=None, cost=0.0):
        self.final_output = final_output
        self.usage = usage or {}
        self.new_items = new_items or []
        self.cost = cost


async def _execute_tool_call(tool, args_json):
    """Execute a tool call and return the result"""
    return await tool.on_invoke_tool(None, args_json)


def _find_tool(agent, tool_name):
    """Find a tool by name in the agent's tools"""
    return next((t for t in agent.tools if t.name == tool_name), None)


def _normalize_model_name(model: str, provider: str) -> str:
    """
    Normalize model name to LiteLLM format.

    If model already has provider prefix (e.g., "openai/gpt-4-turbo"), use as-is.
    Otherwise, infer provider prefix from provider name.

    This allows users to keep existing model names while supporting LiteLLM format.
    """
    provider_lower = provider.lower()
    if provider_lower == "openrouter":
        if model.startswith("openrouter/"):
            return model
        elif "/" in model:
            return f"openrouter/{model}"
        else:
            return f"openrouter/{model}"

    if "/" in model:
        # Already in LiteLLM format
        return model

    # Provider prefix mapping for auto-normalization
    provider_prefix_map = {
        "openai": "openai",
        "anthropic": "anthropic",
        "google": "gemini",
        "gemini": "gemini",
        "deepSeek": "deepSeek",
        "openrouter": "openrouter",
        "xai": "xai",  # Grok
        "grok": "xai",  # Alias
        "mistral": "mistral",
        "alibaba": "dashscope",  # Alibaba uses Dashscope
        "dashscope": "dashscope",
        "cohere": "cohere",
        "perplexity": "perplexity",
        "meta": "meta-llama",
    }

    prefix = provider_prefix_map.get(provider.lower(), provider.lower())
    return f"{prefix}/{model}"


def _setup_api_key(provider_name: str, api_key: str, completion_kwargs: dict):
    """
    Setup API key for LiteLLM based on provider requirements.

    Some providers need environment variables, others accept api_key parameter.
    """
    # Providers that need environment variables (LiteLLM requirement)
    env_var_providers = {
        "openrouter": "OPENROUTER_API_KEY",
        "xai": "XAI_API_KEY",  # Grok
        "deepseek": "DEEPSEEK_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "dashscope": "DASHSCOPE_API_KEY",  # Alibaba
        "google": "GEMINI_API_KEY",  # Alternative to api_key param
        "cohere": "COHERE_API_KEY",
        "perplexity": "PERPLEXITY_API_KEY",
    }

    if provider_name in env_var_providers:
        # Set environment variable for this request
        os.environ[env_var_providers[provider_name]] = api_key
    else:
        # Most providers accept api_key parameter directly
        completion_kwargs["api_key"] = api_key


async def run(agent, enhanced_prompt, provider, model, context=None):
    """
    Unified LiteLLM provider implementation.

        Replaces: openai.py, anthropic.py, google.py, openrouter.py

        Uses LiteLLM's unified interface to support:
        - OpenAI models (via OpenAI API or OpenRouter)
        - Anthropic Claude models (via Anthropic API or OpenRouter)
        - Google Gemini models (via Google API or OpenRouter)
        - OpenRouter (for access to 500+ models)
        - 100+ other providers automatically

        Features:
        - Built-in retry logic
        - Cost tracking
        - Unified error handling
        - OpenAI-compatible tool format (works with existing serialize_tools)

        Args:
                agent: Agent object from agents SDK with tools, instructions, model_settings
                enhanced_prompt: User prompt with conversation history
                provider: Provider name (e.g., "OpenAI", "Anthropic", "Google")
                model: Model name (e.g., "gpt-4-turbo", "claude-3-opus-20240229")
                context: Optional context dictionary (contains agent_name for accessing Agent DocType)

        Returns:
                SimpleResult: Result with final_output, usage, and new_items
    """
    try:
        # Configure LiteLLM to drop unsupported params (for models like gpt-5 that only support temperature=1)
        # This prevents errors when models don't support certain parameters
        litellm.drop_params = True

        # Get Agent DocType directly to access temperature/top_p (most reliable source)
        # Each agent has its own temperature, prompt, and settings from the Agent DocType
        agent_doc = None
        if context and context.get("agent_name"):
            try:
                agent_doc = frappe.get_doc("Agent", context.get("agent_name"))
            except Exception:
                # Will fall back to agent.model_settings if DocType load fails
                pass

		# Get API key from AI Provider doc (same as current implementation)
        provider_doc = frappe.get_doc("AI Provider", provider)
        api_key = provider_doc.get_password("api_key")

        if not api_key:
            frappe.throw("API key not configured in AI Provider.")

        normalized_model = _normalize_model_name(model, provider)

        # Check prompt caching configuration
        enable_prompt_caching = False
        cache_control_type = "ephemeral"
        cache_system_message = False
        cache_conversation_history = False
        
        if agent_doc:
            enable_prompt_caching = bool(agent_doc.get("enable_prompt_caching", 0))
            cache_control_type = agent_doc.get("cache_control_type") or "ephemeral"
            cache_system_message = bool(agent_doc.get("cache_system_message", 0))
            cache_conversation_history = bool(agent_doc.get("cache_conversation_history", 0))
        
        # Check if model supports prompt caching
        model_supports_caching = False
        if enable_prompt_caching:
            try:
                model_supports_caching = supports_prompt_caching(model=normalized_model)
            except Exception:
                # If check fails, assume not supported
                model_supports_caching = False
                frappe.log_error(
                    f"Failed to check prompt caching support for model {normalized_model}",
                    "LiteLLM Prompt Caching"
                )

        # Prepare messages with cache_control if enabled
        messages = []
        provider_name = normalized_model.split("/")[0]
        
        if agent.instructions:
            system_content = agent.instructions
            
            # Add cache_control to system message if enabled
            if enable_prompt_caching and model_supports_caching and cache_system_message:
                if provider_name == "anthropic":
                    # Anthropic: content array with cache_control
                    system_content = [
                        {
                            "type": "text",
                            "text": agent.instructions,
                            "cache_control": {"type": cache_control_type}
                        }
                    ]
                elif provider_name in ("openai", "deepseek"):
                    # OpenAI/Deepseek: content array format (LiteLLM handles cache_control)
                    system_content = [
                        {
                            "type": "text",
                            "text": agent.instructions
                        }
                    ]
                    # Note: OpenAI requires messages to be marked for caching
                    # LiteLLM handles this automatically when content is an array
            
            messages.append({"role": "system", "content": system_content})
        
        # Add user message with cache_control if conversation history caching is enabled
        user_content = enhanced_prompt
        if enable_prompt_caching and model_supports_caching and cache_conversation_history:
            if provider_name == "anthropic":
                # Anthropic: content array with cache_control
                user_content = [
                    {
                        "type": "text",
                        "text": enhanced_prompt,
                        "cache_control": {"type": cache_control_type}
                    }
                ]
            elif provider_name in ("openai", "deepseek"):
                # OpenAI/Deepseek: content array format
                user_content = [
                    {
                        "type": "text",
                        "text": enhanced_prompt
                    }
                ]
        
        messages.append({"role": "user", "content": user_content})

        # Convert tools
        tools = None
        if getattr(agent, "tools", None):
            tools = serialize_tools(agent.tools)

        total_usage = {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0}
        total_cost = 0.0
        all_new_items = []

        MAX_ROUNDS = getattr(agent, "max_turns", 10) or 10

        for round_num in range(MAX_ROUNDS):

            # Temperature / Top P
            temperature = None
            top_p = None

            if agent_doc:
                temperature = agent_doc.temperature
                top_p = agent_doc.top_p

            if (
                temperature is None
                and hasattr(agent, "model_settings")
                and agent.model_settings
            ):
                temperature = getattr(agent.model_settings, "temperature", None)
                if top_p is None:
                    top_p = getattr(agent.model_settings, "top_p", None)

            if temperature is None:
                temperature = 0.7

            # Build completion params
            completion_kwargs = {
                "model": normalized_model,
                "messages": messages,
                "temperature": temperature,
            }

            if top_p:
                completion_kwargs["top_p"] = top_p

            provider_name = normalized_model.split("/")[0]
            _setup_api_key(provider_name, api_key, completion_kwargs)

            if tools:
                completion_kwargs["tools"] = tools
                completion_kwargs["tool_choice"] = "auto"

            # LiteLLM call
            try:
                response = await asyncio.to_thread(
                    litellm.completion, **completion_kwargs
                )

                try:
                    current_cost = completion_cost(completion_response=response)
                    total_cost += float(current_cost)
                    
                except Exception:
                    pass

            except InternalServerError as e:
                msg = (
                    f"OpenAI API server error with model '{normalized_model}'. "
                    f"This may be temporary. Details: {str(e)}"
                )
                frappe.log_error(msg, "LiteLLM Provider")
                return SimpleResult(msg, total_usage, all_new_items)

            except RateLimitError as e:
                title = f"LiteLLM RateLimit: {normalized_model}"[:140]

                try:
                    full_trace = frappe.get_traceback()
                except Exception:
                    full_trace = str(e)

                frappe.log_error(full_trace, title)

                msg = (
                    f"Rate limit exceeded for model '{normalized_model}'. "
                    f"Please try again later. Details: {str(e)}"
                )
                frappe.log_error(msg, "LiteLLM Provider")
                return SimpleResult(msg, total_usage, all_new_items)

            except APIError as e:
                msg = f"API error for model '{normalized_model}': {str(e)}"
                frappe.log_error(msg, "LiteLLM Provider")
                return SimpleResult(msg, total_usage, all_new_items)

            except Exception as e:
                msg = f"LiteLLM error for model '{normalized_model}': {str(e)}"
                frappe.log_error(msg, "LiteLLM Provider")
                return SimpleResult(msg, total_usage, all_new_items)

            # Extract response
            choice = response.choices[0].message

            usage = response.usage
            total_usage["input_tokens"] += usage.prompt_tokens
            total_usage["output_tokens"] += usage.completion_tokens
            
            # Track cached tokens if available
            if hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
                cached_tokens = getattr(usage.prompt_tokens_details, "cached_tokens", 0)
                if cached_tokens:
                    total_usage["cached_tokens"] += cached_tokens

            assistant_message = {
                "role": "assistant",
                "content": choice.content,
            }

            if hasattr(choice, "tool_calls") and choice.tool_calls:
                assistant_message["tool_calls"] = choice.tool_calls

            messages.append(assistant_message)

            # No tool call — return final result
            if not (hasattr(choice, "tool_calls") and choice.tool_calls):
                return SimpleResult(
                    choice.content or "", total_usage, all_new_items, cost=total_cost
                )

            # Handle tool calls
            tool_results = []

            for tool_call in choice.tool_calls:
                function_call = tool_call.function
                tool_name = function_call.name
                tool_args = function_call.arguments

                all_new_items.append(
                    SimpleNamespace(
                        type="tool_call_item",
                        raw_item=SimpleNamespace(name=tool_name, arguments=tool_args),
                    )
                )

                tool_to_run = _find_tool(agent, tool_name)
                result_content = ""

                if tool_to_run:
                    try:
                        result_content = await _execute_tool_call(
                            tool_to_run, tool_args
                        )
                    except Exception as e:
                        result_content = f"Error executing tool {tool_name}: {str(e)}"
                else:
                    result_content = f"Tool '{tool_name}' not found."

                all_new_items.append(
                    SimpleNamespace(
                        type="tool_call_output_item",
                        raw_item={"name": tool_name, "output": result_content},
                    )
                )

                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": str(result_content),
                    }
                )

            messages.extend(tool_results)

        return SimpleResult(
            "Agent stopped after max rounds of tool calls.",
            total_usage,
            all_new_items,
            cost=total_cost,
        )

    except Exception as e:
        frappe.log_error(f"LiteLLM Provider Error: {str(e)}", "LiteLLM Provider")
        return SimpleResult(f"LiteLLM Provider Error: {str(e)}")


async def run_stream(agent, enhanced_prompt, provider, model, context=None):
    """
    Streaming version of LiteLLM provider implementation.

    Yields chunks of the response as they arrive from the LLM.
    For tool calls, buffers the complete tool call before yielding.

    Args:
            agent: Agent object from agents SDK with tools, instructions, model_settings
            enhanced_prompt: User prompt with conversation history
            provider: Provider name (e.g., "OpenAI", "Anthropic", "Google")
            model: Model name (e.g., "gpt-4-turbo", "claude-3-opus-20240229")
            context: Optional context dictionary (contains agent_name for accessing Agent DocType)

    Yields:
            dict: Streaming chunks with structure:
                    - type: "delta" | "complete" | "tool_call" | "error"
                    - content: str (for delta)
                    - full_response: str (accumulated response)
                    - tool_call: dict (for tool_call type)
                    - error: str (for error type)
    """
    try:
        litellm.drop_params = True

        # Get Agent DocType for settings
        agent_doc = None
        if context and context.get("agent_name"):
            try:
                agent_doc = frappe.get_doc("Agent", context.get("agent_name"))
            except Exception:
                pass

        # Get API key
        provider_doc = frappe.get_doc("AI Provider", provider)
        api_key = provider_doc.get_password("api_key")

        if not api_key:
            yield {"type": "error", "error": "API key not configured in AI Provider."}
            return

        normalized_model = _normalize_model_name(model, provider)

        # Check prompt caching configuration
        enable_prompt_caching = False
        cache_control_type = "ephemeral"
        cache_system_message = False
        cache_conversation_history = False
        
        if agent_doc:
            enable_prompt_caching = bool(agent_doc.get("enable_prompt_caching", 0))
            cache_control_type = agent_doc.get("cache_control_type") or "ephemeral"
            cache_system_message = bool(agent_doc.get("cache_system_message", 0))
            cache_conversation_history = bool(agent_doc.get("cache_conversation_history", 0))
        
        # Check if model supports prompt caching
        model_supports_caching = False
        if enable_prompt_caching:
            try:
                model_supports_caching = supports_prompt_caching(model=normalized_model)
            except Exception:
                model_supports_caching = False
                frappe.log_error(
                    f"Failed to check prompt caching support for model {normalized_model}",
                    "LiteLLM Prompt Caching"
                )

        # Prepare messages with cache_control if enabled
        messages = []
        provider_name = normalized_model.split("/")[0]
        
        if agent.instructions:
            system_content = agent.instructions
            
            if enable_prompt_caching and model_supports_caching and cache_system_message:
                if provider_name == "anthropic":
                    system_content = [
                        {
                            "type": "text",
                            "text": agent.instructions,
                            "cache_control": {"type": cache_control_type}
                        }
                    ]
                elif provider_name in ("openai", "deepseek"):
                    system_content = [
                        {
                            "type": "text",
                            "text": agent.instructions
                        }
                    ]
            
            messages.append({"role": "system", "content": system_content})
        
        user_content = enhanced_prompt
        if enable_prompt_caching and model_supports_caching and cache_conversation_history:
            if provider_name == "anthropic":
                user_content = [
                    {
                        "type": "text",
                        "text": enhanced_prompt,
                        "cache_control": {"type": cache_control_type}
                    }
                ]
            elif provider_name in ("openai", "deepseek"):
                user_content = [
                    {
                        "type": "text",
                        "text": enhanced_prompt
                    }
                ]
        
        messages.append({"role": "user", "content": user_content})

        # Convert tools to OpenAI format
        tools = None
        if getattr(agent, "tools", None):
            tools = serialize_tools(agent.tools)

        # Get temperature and top_p
        temperature = None
        top_p = None

        if agent_doc:
            temperature = agent_doc.temperature
            top_p = agent_doc.top_p

        if (
            temperature is None
            and hasattr(agent, "model_settings")
            and agent.model_settings
        ):
            temperature = getattr(agent.model_settings, "temperature", None)
            top_p = (
                getattr(agent.model_settings, "top_p", None) if top_p is None else top_p
            )

        if temperature is None:
            temperature = 0.7

        completion_kwargs = {
            "model": normalized_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,  # Enable streaming
        }

        if top_p:
            completion_kwargs["top_p"] = top_p

        provider_name = normalized_model.split("/")[0]
        _setup_api_key(provider_name, api_key, completion_kwargs)

        if tools:
            completion_kwargs["tools"] = tools
            completion_kwargs["tool_choice"] = "auto"

        # Stream response
        full_response = ""
        MAX_ROUNDS = getattr(agent, "max_turns", 10) or 10

        for round_num in range(MAX_ROUNDS):
            try:
                # Use LiteLLM completion with stream=True
                # LiteLLM completion() supports streaming when stream=True
                stream = await asyncio.to_thread(
                    litellm.completion, **completion_kwargs
                )

                # Buffer for tool calls
                current_tool_calls = {}
                streaming_content = ""

                # Process streaming chunks
                for chunk in stream:
                    if not chunk.choices:
                        continue

                    delta = chunk.choices[0].delta

                    # Handle content delta
                    if hasattr(delta, "content") and delta.content:
                        streaming_content += delta.content
                        full_response += delta.content

                        yield {
                            "type": "delta",
                            "content": delta.content,
                            "full_response": full_response,
                        }

                    # Handle tool call delta
                    if hasattr(delta, "tool_calls") and delta.tool_calls:
                        for tool_call_delta in delta.tool_calls:
                            idx = tool_call_delta.index

                            if idx not in current_tool_calls:
                                current_tool_calls[idx] = {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                }

                            tc = current_tool_calls[idx]

                            if tool_call_delta.id:
                                tc["id"] = tool_call_delta.id

                            if hasattr(tool_call_delta, "function"):
                                if tool_call_delta.function.name:
                                    tc["function"][
                                        "name"
                                    ] = tool_call_delta.function.name
                                if tool_call_delta.function.arguments:
                                    tc["function"][
                                        "arguments"
                                    ] += tool_call_delta.function.arguments

                    # Check if chunk is complete
                    if chunk.choices[0].finish_reason:
                        finish_reason = chunk.choices[0].finish_reason

                        # If tool calls are present, execute them
                        if finish_reason == "tool_calls" and current_tool_calls:
                            # Yield tool calls
                            tool_calls_list = list(current_tool_calls.values())
                            for tool_call in tool_calls_list:
                                yield {
                                    "type": "tool_call",
                                    "tool_call": tool_call,
                                }

                            # Execute tool calls
                            tool_results = []
                            for tool_call in tool_calls_list:
                                function_call = tool_call["function"]
                                tool_name = function_call["name"]
                                tool_args = function_call["arguments"]

                                tool_to_run = _find_tool(agent, tool_name)
                                result_content = ""

                                if tool_to_run:
                                    try:
                                        result_content = await _execute_tool_call(
                                            tool_to_run, tool_args
                                        )
                                    except Exception as e:
                                        result_content = f"Error executing tool {tool_name}: {str(e)}"
                                else:
                                    result_content = f"Tool '{tool_name}' not found."

                                tool_results.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tool_call["id"],
                                        "name": tool_name,
                                        "content": str(result_content),
                                    }
                                )

                            # Add tool results to messages and continue
                            messages.append(
                                {
                                    "role": "assistant",
                                    "content": streaming_content,
                                    "tool_calls": tool_calls_list,
                                }
                            )
                            messages.extend(tool_results)

                            # Reset for next round
                            streaming_content = ""
                            current_tool_calls = {}
                            break

                        # Final response - no more tool calls
                        if finish_reason == "stop":
                            yield {
                                "type": "complete",
                                "full_response": full_response,
                            }
                            return

            except InternalServerError as e:
                yield {"type": "error", "error": f"OpenAI API server error: {str(e)}"}
                return
            except RateLimitError as e:
                yield {"type": "error", "error": f"Rate limit exceeded: {str(e)}"}
                return
            except APIError as e:
                yield {"type": "error", "error": f"API error: {str(e)}"}
                return
            except Exception as e:
                yield {"type": "error", "error": f"LiteLLM error: {str(e)}"}
                return

        # Max rounds reached
        yield {
            "type": "complete",
            "full_response": full_response or "Agent stopped after max rounds.",
        }

    except Exception as e:
        frappe.log_error(f"LiteLLM Streaming Error: {str(e)}", "LiteLLM Streaming")
        yield {"type": "error", "error": f"LiteLLM Streaming Error: {str(e)}"}
