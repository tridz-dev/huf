from agents import Runner

async def run(agent, enhanced_prompt, provider, model, context=None):
    return await Runner.run(agent, enhanced_prompt, max_turns=8, context=context or {})
