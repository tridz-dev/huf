import frappe

class RunProvider:
    @staticmethod
    def run(agent, enhanced_prompt, provider, model):
        provider = provider.lower()

        try:
            module_path = f"agentflo.ai.providers.{provider}"
            module = frappe.get_module(module_path)

            if not hasattr(module, "run"):
                frappe.throw(f"Provider {provider} is missing a run() function")

            return module.run(agent, enhanced_prompt, provider, model)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Provider Run Error: {provider}")
            frappe.throw(f"Error running provider {provider}")
