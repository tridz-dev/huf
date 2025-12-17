import frappe
import requests
import json
from frappe import _
from frappe.utils.file_manager import get_file_path

def execute_provider_tool(provider=None, tool_type=None, tool_name=None, kwargs=None, file_doc=None):
    """
    Generic executor that finds a configured AI Provider Tool and runs it.
    """
    # 1. Find the Tool Configuration
    filters = {"enabled": 1}
    if tool_name:
        filters["provider_tool_name"] = tool_name
    elif provider and tool_type:
        filters["provider"] = provider
        filters["provider_tool_type"] = tool_type
    else:
        frappe.log_error("Provider Handler", "Missing provider/tool_type or tool_name")
        return {"success": False, "error": "Missing configuration to identify the tool."}

    tool_doc_name = frappe.db.get_value("AI Provider Tool", filters, "name")
    
    if not tool_doc_name:
        # Passively return None so calling functions know no tool was found (and can error out gracefully)
        return None

    tool_doc = frappe.get_doc("AI Provider Tool", tool_doc_name)

    # 2. Resolve API Key
    # Priority: Tool specific key > Provider parent key
    api_key = tool_doc.get_password("api_key")
    if not api_key and tool_doc.provider:
        provider_doc = frappe.get_doc("AI Provider", tool_doc.provider)
        api_key = provider_doc.get_password("api_key")

    if not api_key and tool_doc.select_ydlu != "None":
        return {"success": False, "error": f"API Key missing for tool {tool_doc.name}"}

    # 3. Build Headers
    headers = {}
    if tool_doc.select_ydlu == "Bearer Token":
        headers["Authorization"] = f"Bearer {api_key}"
    elif tool_doc.select_ydlu == "API Key Header":
        # Defaulting to 'x-api-key', but allowing override via static_params if needed
        headers["x-api-key"] = api_key

    # 4. Build Payload (Merge Static Params + Runtime Args)
    payload = {}
    if tool_doc.static_params:
        try:
            static_data = json.loads(tool_doc.static_params)
            if isinstance(static_data, dict):
                payload.update(static_data)
        except Exception:
            frappe.log_error("JSON Error", f"Invalid Static Params in {tool_doc.name}")

    if kwargs:
        payload.update(kwargs)

    # Explicit Model Override
    if tool_doc.model:
        payload["model"] = tool_doc.model

    # 5. Handle Files (Specifically for Speech to Text)
    files = None
    opened_file = None
    
    if file_doc and tool_doc.file_param:
        try:
            # If we have a file_doc, we try to get the path
            file_path = get_file_path(file_doc.file_name)
            opened_file = open(file_path, 'rb')
            files = {tool_doc.file_param: (file_doc.file_name, opened_file)}
        except Exception:
            # Fallback if file is remote (S3/URL)
            if hasattr(file_doc, 'file_url') and file_doc.file_url.startswith('http'):
                try:
                    r = requests.get(file_doc.file_url, timeout=10)
                    files = {tool_doc.file_param: (file_doc.file_name or "audio.wav", r.content)}
                except Exception as e:
                    return {"success": False, "error": f"Failed to download remote file: {str(e)}"}
            else:
                 return {"success": False, "error": "Could not locate file path on server."}

    # 6. Execute Request
    try:
        method = tool_doc.method.upper()
        
        # Requests logic: 'data' for form-data (when files exist), 'json' otherwise
        if files:
            # When sending files, other payload data must be form-fields (data=payload)
            response = requests.request(method, tool_doc.api_url, headers=headers, data=payload, files=files, timeout=60)
        else:
            response = requests.request(method, tool_doc.api_url, headers=headers, json=payload, timeout=60)
        
        if opened_file:
            opened_file.close()

        if response.status_code >= 400:
            return {"success": False, "error": f"API Error ({response.status_code}): {response.text}"}

        res_data = response.json()

    except Exception as e:
        if opened_file: opened_file.close()
        return {"success": False, "error": f"Request Failed: {str(e)}"}

    # 7. Extract Result via Response Path
    # If path is "text", we look for data["text"]
    result = res_data
    if tool_doc.response_path:
        try:
            for key in tool_doc.response_path.split('.'):
                if isinstance(result, list) and key.isdigit():
                    result = result[int(key)]
                else:
                    result = result.get(key)
        except Exception:
            # If path extraction fails, return full response for debugging
            pass

    return {"success": True, "result": result, "raw": res_data}