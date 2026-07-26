import requests
import json
import frappe
import asyncio
from types import SimpleNamespace

class SimpleResult:
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

def _convert_to_gemini_tools(agent_tools):
    """Convert Huf tools to Gemini tools format"""
    if not agent_tools:
        return None
    
    gemini_tools = {
        "function_declarations": []
    }
    
    for tool in agent_tools:
        schema = getattr(tool, 'params_json_schema', {})
        
        function_declaration = {
            "name": tool.name,
            "description": getattr(tool, 'description', ''),
            "parameters": {
                "type": "OBJECT",
                "properties": {},
                "required": []
            }
        }
        
        if 'properties' in schema:
            for prop_name, prop_details in schema['properties'].items():
                function_declaration["parameters"]["properties"][prop_name] = {
                    "type": prop_details.get('type', 'STRING').upper(),
                    "description": prop_details.get('description', '')
                }
        
        if 'required' in schema:
            function_declaration["parameters"]["required"] = schema['required']
        
        gemini_tools["function_declarations"].append(function_declaration)
    
    return gemini_tools

async def run(agent, enhanced_prompt, provider, model, context=None):
    try:
        api_key = frappe.get_doc("AI Provider", provider).get_password("api_key")
        if not api_key:
            frappe.throw("API key not configured in AI Provider.")

        model = model.replace("google/", "").split(":")[0]

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

        headers = {"Content-Type": "application/json"}

        system_prompt = agent.instructions or ""
        full_prompt = f"{system_prompt}\n\n{enhanced_prompt}"

        gemini_tools = _convert_to_gemini_tools(getattr(agent, 'tools', []))

        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": full_prompt}]}
            ],
            "generationConfig": {
                "temperature": getattr(agent, 'temperature', 0.7),
            }
        }


        if gemini_tools:
            payload["tools"] = [gemini_tools]

        total_usage = {"input_tokens": 0, "output_tokens": 0}
        all_new_items = []

        MAX_ROUNDS = 5
        current_contents = payload["contents"]

        for round_num in range(MAX_ROUNDS):
            payload["contents"] = current_contents
            
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                return SimpleResult(
                    f"Gemini API Error: {response.status_code} {response.reason}. {response.text}",
                    total_usage,
                    all_new_items
                )

            data = response.json()
            
            usage_info = data.get("usageMetadata", {})
            total_usage["input_tokens"] += usage_info.get("promptTokenCount", 0)
            total_usage["output_tokens"] += usage_info.get("candidatesTokenCount", 0)

            if "candidates" not in data or not data["candidates"]:
                return SimpleResult(
                    "No response generated from Gemini",
                    total_usage,
                    all_new_items
                )

            candidate = data["candidates"][0]
            content = candidate.get("content", {})
            parts = content.get("parts", [])

            if not parts:
                return SimpleResult(
                    "Empty response from Gemini",
                    total_usage,
                    all_new_items
                )

            function_calls = []
            text_response = ""

            for part in parts:
                if "text" in part:
                    text_response += part["text"]
                elif "functionCall" in part:
                    function_calls.append(part["functionCall"])
                elif "function_call" in part:
                    function_calls.append(part["function_call"])

            if function_calls:
                model_response_parts = []
                for part in parts:
                    if "text" in part:
                        model_response_parts.append({"text": part["text"]})
                    elif "functionCall" in part:
                        model_response_parts.append({"functionCall": part["functionCall"]})
                    elif "function_call" in part:
                        model_response_parts.append({"function_call": part["function_call"]})

                
                current_contents.append({
                    "role": "model",
                    "parts": model_response_parts
                })

                function_responses = []
                
                for func_call in function_calls:
                    function_name = func_call.get("name")
                    function_args = func_call.get("args", {})
                    
                    all_new_items.append(
                        SimpleNamespace(
                            type="tool_call_item", 
                            raw_item=SimpleNamespace(
                                name=function_name,
                                arguments=json.dumps(function_args)
                            )
                        )
                    )

                    tool_to_run = _find_tool(agent, function_name)
                    result_content = ''

                    if tool_to_run:
                        try:
                            result_content = await _execute_tool_call(tool_to_run, json.dumps(function_args))
                        except Exception as e:
                            result_content = f"Error executing tool {function_name}: {str(e)}"
                    else:
                        result_content = f"Tool '{function_name}' not found."

                    all_new_items.append(
                        SimpleNamespace(
                            type="tool_call_output_item",
                            raw_item={"name": function_name, "output": result_content}
                        )
                    )

                    function_responses.append({
                        "functionResponse": {
                            "name": function_name,
                            "response": {"result": result_content}
                        }
                    })

                current_contents.append({
                    "role": "user",
                    "parts": function_responses
                })

            else:
                final_output = text_response
                return SimpleResult(final_output, total_usage, all_new_items)

        return SimpleResult(text_response, total_usage, all_new_items)

    except Exception as e:
        frappe.log_error(f"Gemini Provider Error: {str(e)}", "Gemini Provider")
        return SimpleResult(f"Gemini API Error: {str(e)}")