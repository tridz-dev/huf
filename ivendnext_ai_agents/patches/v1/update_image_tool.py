import frappe

def execute():
    if not frappe.db.exists("Agent Tool Function", {"tool_name": "generate_image"}):
        return
    tool_doc = frappe.get_doc("Agent Tool Function", "generate_image")
    tool_doc.description = "Generate an image from a text description using AI. Use this when the user asks for image creation, visualization, or artwork generation. Do not show the image URL in the output message."
    for param in tool_doc.parameters:
        if param.fieldname == "quality":
            param.description = "Image quality. Default 'auto'. Options vary by model. <a href='https://docs.litellm.ai/docs/image_generation#optional-litellm-fields'>Documentation</a>"
            param.options = "auto"
        if param.fieldname == "size":
            param.description = "Image dimensions. Default 'auto'. Options vary by model. <a href='https://docs.litellm.ai/docs/image_generation#optional-litellm-fields'>Documentation</a>"
            param.options = "auto"
    new_param = {
        "label": "Response Format",
        "fieldname": "response_format",
        "type": "string",
        "required": 0,
        "description": "Response format. Default 'url'",
        "options": "url\nb64_json."
    }
    tool_doc.append("parameters", new_param)
    tool_doc.save()