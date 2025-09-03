import frappe
from frappe.utils import now
import json
import requests
# agent_runner.py
from .providers import openrouter




class RunProvider:    
    @staticmethod
    def run(agent_name, enhanced_prompt, provider, model):
        match provider.lower():
            case "openrouter":
                return openrouter.run(agent_name, enhanced_prompt, provider, model)
            case "openai":
                pass
                # return openai.run(agent_name, enhanced_prompt, provider, model)
            case "google":
                pass
                # return google.run(agent_name, enhanced_prompt, provider, model)
            case _:
                raise ValueError(f"Unknown provider: {provider}")
