# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Unified LiteLLM Provider Implementation

This module provides a unified interface to 100+ LLM providers via LiteLLM.
It replaces the need for separate provider implementations while maintaining
100% backward compatibility with existing AgentFlo configurations.

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

from agentflo.ai.tool_serializer import serialize_tools


class SimpleResult:
	"""Result structure for provider responses"""

	def __init__(self, final_output, usage=None, new_items=None):
		self.final_output = final_output
		self.usage = usage or {}
		self.new_items = new_items or []


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
	if "/" in model:
		# Already in LiteLLM format
		return model
	
	# Provider prefix mapping for auto-normalization
	provider_prefix_map = {
		"openai": "openai",
		"anthropic": "anthropic",
		"google": "google",
		"gemini": "google",  # Alias
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
		context: Optional context dictionary (may contain agent_name for debugging)
	
	Returns:
		SimpleResult: Result with final_output, usage, and new_items
	"""
	try:
		# Configure LiteLLM to drop unsupported params (for models like gpt-5 that only support temperature=1)
		# This prevents errors when models don't support certain parameters
		litellm.drop_params = True
		
		# Get Agent DocType directly to access temperature/top_p (most reliable source)
		# This ensures we always get the correct values from the Agent DocType
		agent_doc = None
		if context and context.get("agent_name"):
			try:
				agent_doc = frappe.get_doc("Agent", context.get("agent_name"))
			except Exception as e:
				frappe.log_error(f"Could not load Agent DocType: {str(e)}", "LiteLLM Debug")
		
		# Get API key from AI Provider doc (same as current implementation)
		provider_doc = frappe.get_doc("AI Provider", provider)
		api_key = provider_doc.get_password("api_key")
		
		if not api_key:
			frappe.throw("API key not configured in AI Provider.")
		
		# Normalize model name to LiteLLM format
		# USER-FRIENDLY: No changes needed to DocTypes
		# Users can keep existing model names (e.g., "gpt-4-turbo")
		# and we automatically add the provider prefix (e.g., "openai/gpt-4-turbo")
		normalized_model = _normalize_model_name(model, provider)
		
		# Prepare messages
		messages = []
		if agent.instructions:
			messages.append({"role": "system", "content": agent.instructions})
		messages.append({"role": "user", "content": enhanced_prompt})
		
		# Convert tools to OpenAI format (LiteLLM uses this format)
		# This uses your existing serialize_tools() function - no changes needed!
		tools = None
		if getattr(agent, "tools", None):
			tools = serialize_tools(agent.tools)
		
		total_usage = {"input_tokens": 0, "output_tokens": 0}
		all_new_items = []
		
		# Multi-turn tool calling loop
		# Same pattern as your existing providers
		MAX_ROUNDS = getattr(agent, "max_turns", 10) or 10
		
		for round_num in range(MAX_ROUNDS):
			# Prepare completion parameters
			# Get temperature from agent.model_settings (set from Agent DocType)
			# The SDK Agent has model_settings with temperature/top_p from the Frappe DocType
			temperature = None
			top_p = None
			
			# Debug: Log agent structure for troubleshooting (only first round)
			if context and context.get("agent_name") and round_num == 0:
				try:
					debug_info = {
						"has_model_settings": hasattr(agent, "model_settings"),
						"model_settings_type": type(agent.model_settings).__name__ if hasattr(agent, "model_settings") else None,
					}
					if hasattr(agent, "model_settings") and agent.model_settings:
						# Try to get model_settings as dict
						try:
							debug_info["model_settings_dict"] = vars(agent.model_settings)
						except:
							try:
								debug_info["model_settings_dict"] = agent.model_settings.__dict__
							except:
								debug_info["model_settings_dict"] = str(agent.model_settings)
					
					frappe.log_error(
						f"LiteLLM Debug - Agent structure for {context.get('agent_name')}:\n{json.dumps(debug_info, indent=2, default=str)}",
						"LiteLLM Debug"
					)
				except Exception as debug_err:
					frappe.log_error(f"Debug logging error: {str(debug_err)}", "LiteLLM Debug")
			
			# Priority 1: Get from Agent DocType (most reliable - direct from database)
			if agent_doc:
				temperature = agent_doc.temperature
				top_p = agent_doc.top_p
			
			# Priority 2: Try multiple ways to access from agent.model_settings
			if temperature is None and hasattr(agent, "model_settings") and agent.model_settings:
				# Method 1: Direct attribute access
				temperature = getattr(agent.model_settings, "temperature", None)
				top_p = getattr(agent.model_settings, "top_p", None) if top_p is None else top_p
				
				# Method 2: Try dict-like access if it's a dict-like object
				if temperature is None and hasattr(agent.model_settings, "__dict__"):
					temperature = agent.model_settings.__dict__.get("temperature")
				if top_p is None and hasattr(agent.model_settings, "__dict__"):
					top_p = agent.model_settings.__dict__.get("top_p")
				
				# Method 3: Try as dict if it's dict-like
				if temperature is None and isinstance(agent.model_settings, dict):
					temperature = agent.model_settings.get("temperature")
				if top_p is None and isinstance(agent.model_settings, dict):
					top_p = agent.model_settings.get("top_p")
			
			# Priority 3: Fallback - Try direct agent attributes (shouldn't work but helps debug)
			if temperature is None:
				temperature = getattr(agent, "temperature", None)
			if top_p is None:
				top_p = getattr(agent, "top_p", None)
			
			# Final fallback to default if not set (log warning for debugging)
			if temperature is None:
				temperature = 0.7
				if context and context.get("agent_name"):
					frappe.log_error(
						f"⚠️ Temperature not found in agent.model_settings, using default {temperature}. "
						f"Agent: {context.get('agent_name')}. "
						f"agent.model_settings: {agent.model_settings if hasattr(agent, 'model_settings') else 'None'}. "
						f"Check Agent DocType has temperature field set.",
						"LiteLLM Parameter Warning"
					)
			
			completion_kwargs = {
				"model": normalized_model,
				"messages": messages,
				"temperature": temperature,
			}
			
			# Add top_p if specified
			if top_p:
				completion_kwargs["top_p"] = top_p
			
			# Log actual values being used (only first round to avoid spam)
			if context and context.get("agent_name") and round_num == 0:
				frappe.log_error(
					f"LiteLLM Parameters - Model: {normalized_model}, Temperature: {temperature}, TopP: {top_p}, "
					f"Agent: {context.get('agent_name')}",
					"LiteLLM Debug"
				)
			
			# Set API key based on provider
			provider_name = normalized_model.split("/")[0]
			_setup_api_key(provider_name, api_key, completion_kwargs)
			
			# Add tools if available
			if tools:
				completion_kwargs["tools"] = tools
				completion_kwargs["tool_choice"] = "auto"
			
			# Call LiteLLM
			# LiteLLM completion() is synchronous, so we wrap it in asyncio.to_thread
			# to avoid blocking the async event loop
			# LiteLLM has built-in retry logic, but we can add additional context
			try:
				response = await asyncio.to_thread(litellm.completion, **completion_kwargs)
			except InternalServerError as e:
				# OpenAI server error - might be transient
				error_msg = (
					f"OpenAI API server error while processing request with model '{normalized_model}'. "
					f"This may be a temporary issue. Please try again. "
					f"Error details: {str(e)}"
				)
				frappe.log_error(error_msg, "LiteLLM Provider")
				return SimpleResult(error_msg, total_usage, all_new_items)
			except RateLimitError as e:
				# Rate limit error
				error_msg = (
					f"Rate limit exceeded for model '{normalized_model}'. "
					f"Please wait a moment and try again. "
					f"Error details: {str(e)}"
				)
				frappe.log_error(error_msg, "LiteLLM Provider")
				return SimpleResult(error_msg, total_usage, all_new_items)
			except APIError as e:
				# Other API errors
				error_msg = f"API error for model '{normalized_model}': {str(e)}"
				frappe.log_error(error_msg, "LiteLLM Provider")
				return SimpleResult(error_msg, total_usage, all_new_items)
			except Exception as e:
				# General errors
				error_msg = f"LiteLLM error for model '{normalized_model}': {str(e)}"
				frappe.log_error(error_msg, "LiteLLM Provider")
				return SimpleResult(error_msg, total_usage, all_new_items)
			
			# Extract response (OpenAI format - consistent across all providers)
			choice = response.choices[0].message
			
			# Track usage (OpenAI format - consistent)
			usage = response.usage
			total_usage["input_tokens"] += usage.prompt_tokens
			total_usage["output_tokens"] += usage.completion_tokens
			
			# Add assistant message to conversation
			assistant_message = {
				"role": "assistant",
				"content": choice.content,
			}
			
			# Add tool_calls if present
			if hasattr(choice, "tool_calls") and choice.tool_calls:
				assistant_message["tool_calls"] = choice.tool_calls
			
			messages.append(assistant_message)
			
			# Check for tool calls
			if not (hasattr(choice, "tool_calls") and choice.tool_calls):
				# Final response - no more tool calls
				return SimpleResult(
					choice.content or "",
					total_usage,
					all_new_items
				)
			
			# Execute tool calls
			# This is YOUR existing logic - works exactly as-is!
			tool_results = []
			
			for tool_call in choice.tool_calls:
				function_call = tool_call.function
				tool_name = function_call.name
				tool_args = function_call.arguments
				
				# Log tool call (same as your existing providers)
				all_new_items.append(
					SimpleNamespace(
						type="tool_call_item",
						raw_item=SimpleNamespace(
							name=tool_name,
							arguments=tool_args
						)
					)
				)
				
				# Find and execute tool (YOUR existing functions)
				tool_to_run = _find_tool(agent, tool_name)
				result_content = ""
				
				if tool_to_run:
					try:
						result_content = await _execute_tool_call(tool_to_run, tool_args)
					except Exception as e:
						result_content = f"Error executing tool {tool_name}: {str(e)}"
				else:
					result_content = f"Tool '{tool_name}' not found."
				
				# Log tool result (same as your existing providers)
				all_new_items.append(
					SimpleNamespace(
						type="tool_call_output_item",
						raw_item={"name": tool_name, "output": result_content}
					)
				)
				
				# Add tool result to messages (OpenAI format)
				tool_results.append({
					"role": "tool",
					"tool_call_id": tool_call.id,
					"name": tool_name,
					"content": str(result_content)
				})
			
			# Add tool results to conversation
			messages.extend(tool_results)
		
		# Max rounds reached
		return SimpleResult(
			"Agent stopped after max rounds of tool calls.",
			total_usage,
			all_new_items
		)
		
	except Exception as e:
		frappe.log_error(f"LiteLLM Provider Error: {str(e)}", "LiteLLM Provider")
		return SimpleResult(f"LiteLLM Provider Error: {str(e)}")

