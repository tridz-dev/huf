import json, requests, asyncio
import frappe
from agentflo.ai.tool_serializer import serialize_tools


async def run(agent, enhanced_prompt, provider, model):
    def _sync_call():
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": agent.instructions},
                {"role": "user", "content": enhanced_prompt},
            ],
        }

        if getattr(agent, "tools", None) and len(agent.tools) > 0:
            payload["tools"] = serialize_tools(agent.tools)
        api_key = frappe.get_doc("AI Provider", provider).get_password("api_key")
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(payload),
        )
        data = response.json()

        try:
            choice = data["choices"][0]["message"]

            if "tool_calls" in choice:
                tool_calls = choice["tool_calls"]
                return execute_tool_calls(agent, tool_calls)

            return choice.get("content", "")

        except (KeyError, IndexError, TypeError):
            return data.get("error", {}).get("message", str(data))

    return await asyncio.to_thread(_sync_call)



def execute_tool_calls(agent, tool_calls: list):
    """
    Run the tool functions returned by the model.
    """
    results = []

    for call in tool_calls:
        try:
            fn_name = call["function"]["name"]
            args = call["function"].get("arguments", "{}")
            args_dict = json.loads(args) if isinstance(args, str) else args

            tool = next((t for t in agent.tools if t.name == fn_name), None)
            if not tool:
                results.append({
                    "id": call.get("id"),
                    "name": fn_name,
                    "error": f"Tool {fn_name} not found"
                })
                continue

            result = asyncio.run(tool.on_invoke_tool(None, json.dumps(args_dict)))

            results.append({
                "id": call.get("id"),
                "name": fn_name,
                "args": args_dict,
                "result": result
            })

        except Exception as e:
            results.append({
                "id": call.get("id"),
                "error": str(e)
            })

    return json.dumps(results, default=str)
