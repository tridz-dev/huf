# Canvas Artifact Server-Side Logic
import frappe

def get_context(context):
    """Server-side context for this canvas page"""
    context.show_sidebar = False
    return context