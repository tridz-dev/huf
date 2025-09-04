import json, requests, asyncio

async def run(agent, enhanced_prompt, provider, model):
    def _sync_call():
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": "Bearer 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", 
                "Content-Type": "application/json"
            },
            data=json.dumps({
                "model": model,
                "messages": [
                    {"role": "user", "content": enhanced_prompt}
                ]
            })
        )
        data = response.json()

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return data.get("error", {}).get("message", str(data))

    return await asyncio.to_thread(_sync_call)
