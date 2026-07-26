import json, requests, asyncio, random
from types import SimpleNamespace
import frappe
from huf.ai.tool_serializer import serialize_tools

class SimpleResult:
    def __init__(self, final_output, usage=None, new_items=None):
        self.final_output = final_output
        self.usage = usage or {}
        self.new_items = new_items or []

async def _execute_tool_call(tool, args_json):
    return await tool.on_invoke_tool(None, args_json)

def _find_tool(agent, tool_name):
    return next((t for t in agent.tools if t.name == tool_name), None)

async def _post_with_retry(url, headers, payload, max_retries=5):
    """Post request with retry/backoff for 429 errors"""
    delay = 1
    for attempt in range(max_retries):
        try:
            response = await asyncio.to_thread(
                requests.post,
                url,
                headers=headers,
                data=json.dumps(payload)
            )
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            if response.status_code == 429:
                await asyncio.sleep(delay + random.uniform(0, 0.5))
                delay *= 2
                continue
            raise
    raise Exception(f"Failed after {max_retries} retries (rate limit?)")

async def run(agent, enhanced_prompt, provider, model, context=None):
    api_key = frappe.get_doc("AI Provider", provider).get_password("api_key")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    messages = [
        {"role": "system", "content": agent.instructions},
        {"role": "user", "content": enhanced_prompt},
    ]
    
    total_usage = {"input_tokens": 0, "output_tokens": 0}
    all_new_items = []

    MAX_ROUNDS = 10
    for round_num in range(MAX_ROUNDS):
        payload = {"model": model, "messages": messages}
        if getattr(agent, "tools", None):
            payload["tools"] = serialize_tools(agent.tools)

        try:
            response = await _post_with_retry(
                "https://openrouter.ai/api/v1/chat/completions",
                headers,
                payload
            )
            data = response.json()
        except requests.exceptions.RequestException as e:
            return SimpleResult(f"API Error: {e}", total_usage, all_new_items)

        try:
            choice = data["choices"][0]["message"]
            usage = data.get("usage", {})
            
            total_usage["input_tokens"] += usage.get("prompt_tokens", 0)
            total_usage["output_tokens"] += usage.get("completion_tokens", 0)

            messages.append(choice)

            if not choice.get("tool_calls"):
                final_output = choice.get("content", "")
                return SimpleResult(final_output, total_usage, all_new_items)

            tool_calls = choice["tool_calls"]
            tool_results_for_api = []

            for tool_call in tool_calls:
                function_call = tool_call.get("function", {})
                tool_name = function_call.get("name")
                tool_args = function_call.get("arguments", "{}")
                
                all_new_items.append(
                    SimpleNamespace(type="tool_call_item", raw_item=SimpleNamespace(**function_call))
                )

                tool_to_run = _find_tool(agent, tool_name)
                result_content = ''

                if tool_to_run:
                    try:
                        result_content = await _execute_tool_call(tool_to_run, tool_args)
                    except Exception as e:
                        result_content = f"Error executing tool {tool_name}: {e}"
                else:
                    result_content = f"Tool '{tool_name}' not found."

                tool_results_for_api.append({
                    "tool_call_id": tool_call.get("id"),
                    "role": "tool",
                    "name": tool_name,
                    "content": result_content,
                })
                all_new_items.append(SimpleNamespace(
                    type="tool_call_output_item",
                    raw_item={"name": tool_name, "output": result_content}
                ))

            messages.extend(tool_results_for_api)

        except (KeyError, IndexError, TypeError) as e:
            return SimpleResult(str(data.get("error", {}).get("message", e)), total_usage, all_new_items)

    return SimpleResult("Agent stopped after max rounds of tool calls.", total_usage, all_new_items)
