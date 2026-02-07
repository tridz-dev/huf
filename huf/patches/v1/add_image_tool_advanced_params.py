import frappe

def execute():
    """
    Add aspect_ratio and image_size parameters to the generate_image tool.
    These parameters enable better control over image generation, especially for Google/Gemini models.
    """
    if not frappe.db.exists("Agent Tool Function", {"tool_name": "generate_image"}):
        return
    
    tool_doc = frappe.get_doc("Agent Tool Function", "generate_image")
    
    # Check if parameters already exist
    existing_fieldnames = [param.fieldname for param in tool_doc.parameters]
    
    # Add aspect_ratio parameter if not exists
    if "aspect_ratio" not in existing_fieldnames:
        aspect_ratio_param = {
            "label": "Aspect Ratio",
            "fieldname": "aspect_ratio",
            "type": "string",
            "required": 0,
            "description": "Aspect ratio for the image (e.g., '16:9', '9:16', '1:1'). Supported by Google/Gemini models. Overrides size parameter when used.",
            "options": "16:9\n9:16\n1:1\n4:3\n3:4"
        }
        tool_doc.append("parameters", aspect_ratio_param)
    
    # Add image_size parameter if not exists
    if "image_size" not in existing_fieldnames:
        image_size_param = {
            "label": "Image Size",
            "fieldname": "image_size",
            "type": "string",
            "required": 0,
            "description": "Image resolution quality (e.g., '2K', '4K', '1K'). Supported by Google/Gemini models. Higher resolution improves text readability in generated images.",
            "options": "1K\n2K\n4K"
        }
        tool_doc.append("parameters", image_size_param)
    
    tool_doc.save()
    frappe.db.commit()
    print("Successfully added aspect_ratio and image_size parameters to generate_image tool")
