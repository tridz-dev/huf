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
		
		# Route existing providers to LiteLLM
		# This provides unified handling while maintaining backward compatibility
		litellm_providers = ["openai", "anthropic", "google", "gemini", "openrouter"]
		
		if provider_lower in litellm_providers:
			# Use LiteLLM for these providers
			try:
				from agentflo.ai.providers import litellm
				return litellm.run(agent, enhanced_prompt, provider, model, context=context)
			except ImportError as e:
				# LiteLLM not installed - provide helpful error message
				error_msg = (
					f"LiteLLM package is required but not installed.\n\n"
					f"To install:\n"
					f"1. Run: bench setup requirements\n"
					f"2. Or manually: pip install litellm>=1.0.0\n"
					f"3. Then restart your site: bench restart\n\n"
					f"The litellm package is listed in pyproject.toml dependencies, "
					f"so running 'bench setup requirements' should install it automatically."
				)
				frappe.log_error(
					f"LiteLLM Import Error: {str(e)}\n\n{error_msg}",
					"LiteLLM Provider Error"
				)
				frappe.throw(_(error_msg))
			except Exception as e:
				frappe.log_error(
					frappe.get_traceback(),
					f"LiteLLM Provider Error: {provider}"
				)
				frappe.throw(f"Error running provider {provider} via LiteLLM: {str(e)}")
		
		# For other providers, try to load custom provider module
		# This allows for future custom providers or gradual migration
		try:
			module_path = f"agentflo.ai.providers.{provider_lower}"
			module = frappe.get_module(module_path)
			
			if not hasattr(module, "run"):
				frappe.throw(f"Provider {provider} is missing a run() function")
			
			return module.run(agent, enhanced_prompt, provider, model, context=context)
		except ImportError:
			# Provider module doesn't exist - suggest using LiteLLM format
			frappe.throw(
				f"Provider '{provider}' not found. "
				f"For LiteLLM-supported providers, ensure model name includes provider prefix "
				f"(e.g., 'xai/grok-4' for Grok, 'mistral/mistral-large' for Mistral)."
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Provider Run Error: {provider}")
			frappe.throw(f"Error running provider {provider}")
