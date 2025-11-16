import frappe

no_cache = 1


def get_context(context):
	# For static Next.js export, the HTML is wrapped in {% raw %} tags
	# to prevent Jinja from processing the {{ }} characters in JavaScript
	# Frappe will automatically render the docs.html template
	return context

