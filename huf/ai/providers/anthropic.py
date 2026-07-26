# anthropic.py
import json
import asyncio
import frappe
from types import SimpleNamespace
import anthropic
from huf.ai.tool_serializer import serialize_tools

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

def _convert_to_anthropic_tools(agent_tools):
    """Convert Huf tools to Anthropic tools format"""
    if not agent_tools:
        return []
    
    anthropic_tools = []
    
    for tool in agent_tools:
        schema = getattr(tool, 'params_json_schema', {})
        
        tool_definition = {
            "name": tool.name,
            "description": getattr(tool, 'description', ''),
            "input_schema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
        
        if 'properties' in schema:
            for prop_name, prop_details in schema['properties'].items():
                tool_definition["input_schema"]["properties"][prop_name] = {
                    "type": prop_details.get('type', 'string'),
                    "description": prop_details.get('description', '')
                }
        
        if 'required' in schema:
            tool_definition["input_schema"]["required"] = schema['required']
        
        anthropic_tools.append(tool_definition)
    
    return anthropic_tools

async def run(agent, enhanced_prompt, provider, model, context=None):
    try:
        api_key = frappe.get_doc("AI Provider", provider).get_password("api_key")
        if not api_key:
            frappe.throw("API key not configured in AI Provider.")

        client = anthropic.AsyncAnthropic(api_key=api_key)
        
        system_prompt = agent.instructions or ""
        
        # Convert tools to Anthropic format
        anthropic_tools = _convert_to_anthropic_tools(getattr(agent, 'tools', []))
        
        messages = [
            {
                "role": "user",
                "content": enhanced_prompt
            }
        ]
        
        total_usage = {"input_tokens": 0, "output_tokens": 0}
        all_new_items = []

        MAX_ROUNDS = 10
        
        for round_num in range(MAX_ROUNDS):
            params = {
                "model": model.replace("anthropic/", ""),
                "max_tokens": 4096,
                "messages": messages,
            }
            
            if system_prompt.strip():
                params["system"] = system_prompt
            
            if anthropic_tools:
                params["tools"] = anthropic_tools
                params["tool_choice"] = {"type": "auto"}

            try:
                response = await client.messages.create(**params)
            except Exception as e:
                return SimpleResult(f"Anthropic API Error: {str(e)}", total_usage, all_new_items)

            total_usage["input_tokens"] += response.usage.input_tokens
            total_usage["output_tokens"] += response.usage.output_tokens

            tool_uses = [block for block in response.content if block.type == "tool_use"]
            text_blocks = [block for block in response.content if block.type == "text"]
            
            text_content = "".join(block.text for block in text_blocks)

            if tool_uses:
                assistant_message = {
                    "role": "assistant", 
                    "content": response.content  
                }
                
                for tool_use in tool_uses:
                    all_new_items.append(
                        SimpleNamespace(
                            type="tool_call_item", 
                            raw_item=SimpleNamespace(
                                name=tool_use.name,
                                arguments=json.dumps(tool_use.input)
                            )
                        )
                    )

                tool_results = []
                
                for tool_use in tool_uses:
                    tool_name = tool_use.name
                    tool_args = tool_use.input
                    
                    tool_to_run = _find_tool(agent, tool_name)
                    result_content = ''

                    if tool_to_run:
                        try:
                            result_content = await _execute_tool_call(tool_to_run, json.dumps(tool_args))
                        except Exception as e:
                            result_content = f"Error executing tool {tool_name}: {str(e)}"
                    else:
                        result_content = f"Tool '{tool_name}' not found."

                    all_new_items.append(
                        SimpleNamespace(
                            type="tool_call_output_item",
                            raw_item={"name": tool_name, "output": result_content}
                        )
                    )

                    if isinstance(result_content, (dict, list)):
                        result_content = json.dumps(result_content, default=str)
                    
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": str(result_content)
                    })

                messages.append(assistant_message)
                
                if tool_results:
                    messages.append({
                        "role": "user", 
                        "content": tool_results
                    })

            else:
                final_output = text_content
                return SimpleResult(final_output, total_usage, all_new_items)

        return SimpleResult("Agent stopped after max rounds of tool calls.", total_usage, all_new_items)

    except Exception as e:
        frappe.log_error(f"Anthropic Provider Error: {str(e)}", "Anthropic Provider")
        return SimpleResult(f"Anthropic API Error: {str(e)}")