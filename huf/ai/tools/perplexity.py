import os

import frappe
from frappe import _

logger = frappe.logger("huf")


def handle_perplexity_search(query: str, **kwargs):
    """
    Perform a web search using a Perplexity sonar model via LiteLLM.

    Reads the API key from the ``perplexity_api_key`` site_config value,
    falling back to the ``PERPLEXITY_API_KEY`` environment variable.

    Args:
        query: The search query string

    Returns:
        dict: {
            "success": bool,
            "query": str,
            "answer": str,          # Grounded answer text from the sonar model
            "citations": list,      # Source URLs cited by the model
            "model": str,
            "error": str
        }
    """
    site_config = frappe.get_site_config()
    api_key = site_config.get("perplexity_api_key") or os.environ.get("PERPLEXITY_API_KEY")

    if not api_key:
        frappe.throw(
            _(
                "Perplexity Search is not configured. Please set 'perplexity_api_key' "
                "in site config or the PERPLEXITY_API_KEY environment variable."
            )
        )

    try:
        from litellm import completion

        # LiteLLM routes Perplexity credentials via environment variable
        os.environ["PERPLEXITY_API_KEY"] = api_key

        response = completion(
            model="perplexity/sonar",
            messages=[{"role": "user", "content": query}],
        )

        message = response.choices[0].message
        citations = (
            getattr(response, "citations", None)
            or getattr(message, "citations", None)
            or []
        )

        return {
            "success": True,
            "query": query,
            "answer": message.content,
            "citations": citations,
            "model": "perplexity/sonar",
        }
    except Exception as e:
        logger.warning(f"handle_perplexity_search failed: {e!s}")
        return {"success": False, "error": str(e)}
