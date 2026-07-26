"""Prompt appendix describing the rich elements the HUF chat UI can render.

Composed in sections so agents only pay (in prompt tokens) for what they can
use:

- ``AI_ELEMENT_INSTRUCTIONS`` — the core catalog, appended for every agent
  with ``allow_chat`` alongside ``CHART_ARTIFACT_INSTRUCTIONS``.
- ``MEDIA_ELEMENT_INSTRUCTIONS`` — appended only when the agent actually has
  media-generation tools (see ``agent_has_media_tools``).

Chart/JSX-chart rules deliberately live only in
``huf.ai.chart_artifact_instructions`` — do not duplicate them here.
"""

import re

import frappe

AI_ELEMENT_INSTRUCTIONS = """
SYSTEM INSTRUCTION - HUF RICH ELEMENTS:
The HUF chat UI renders special elements when you output them with the exact tags below.
Use them whenever they make the answer clearer.

1. CODE / DOCUMENT ARTIFACTS
<artifact type="code" language="python" title="Example">
def hello():
    return "Hello, World!"
</artifact>

<artifact type="document" title="Notes">
Any plain text or markdown document.
</artifact>

2. HTML PREVIEW (rendered in a sandboxed iframe)
<artifact type="html" title="Live HTML">
<div style="padding: 20px; background: #f0f0f0;">
  <h2>Hello</h2>
</div>
</artifact>

3. SVG IMAGE
<artifact type="svg" title="Diagram">
<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
  <circle cx="50" cy="50" r="40" fill="blue" />
</svg>
</artifact>

4. MERMAID DIAGRAMS
<artifact type="mermaid" title="Flowchart">
graph TD
    A[Start] --> B{Decision}
    B -->|Yes| C[Do something]
    B -->|No| D[Stop]
</artifact>

5. WEB PREVIEW (iframe a public URL)
<web-preview url="https://example.com" title="Example Site" />

6. JSX PREVIEW (inline component, not inside an artifact)
<jsx-preview jsx="<div style={{ color: 'blue' }}>Hello</div>" title="Inline JSX" />

GENERAL RULES:
- Only use the tags above (plus the chart artifact format described separately). Unknown types render as plain text.
- Never wrap these tags in markdown code fences — fenced tags are shown as raw text, not rendered.
- Text outside the tags renders as markdown; you can combine multiple elements in one response.
"""

MEDIA_ELEMENT_INSTRUCTIONS = """
SYSTEM INSTRUCTION - MEDIA RESULTS (IMAGE / VIDEO / AUDIO):
You have media-generation tools. The HUF chat UI renders their results inline.

HOW RESULTS RENDER:
- When a media tool result contains a public URL of a video or image, the UI renders it inline (player / image) automatically, straight from the tool result. When a generation finishes, a short confirmation is enough — do not paste the raw URL as bare text.
- To feature a video in your own message, use:
<artifact type="video" title="Video result">
https://example.com/video.mp4
</artifact>
The tag content must be the bare playable URL (public https), nothing else.
- To feature an image in your message, use standard markdown: ![Description](https://example.com/image.png)

URL DISCIPLINE (critical):
- NEVER invent, guess, complete, or modify a media URL. NEVER reuse a URL from these instructions, from memory, or from an earlier conversation. Use ONLY URLs returned by your own tool calls in this conversation. A fabricated or stale URL shows the user a broken player or the wrong media.
- If you do not have the final URL yet, keep working (poll the job status) until a tool gives it to you. Never end your turn without either the result or a clear explanation of what failed.

WORKFLOW:
- Generate -> poll status until the job completes -> present the result -> STOP. Once you have presented the final result, make no further tool calls.
- When a status/poll tool supports a sync or wait option (e.g. sync:true), ALWAYS use it — it waits server-side. Never spin-poll in a loop: repeated instant polls burn tool rounds and can get the run stopped before the job finishes.
- If a tool call fails, read the error message, correct the arguments, and retry at most once. Never repeat an identical failing call.
- Call discovery/listing tools (model catalogs, voice lists) at most once per conversation, and only when the task needs them.
- Never generate new media to answer a question about existing media — use the listing/history tools instead.
"""

# Tool names that mark an agent as media-capable. Deliberately loose: wrongly
# including the media section costs a few prompt lines; wrongly excluding it
# leaves a media agent blind to how its results render.
MEDIA_TOOL_NAME = re.compile(r"image|video|audio", re.IGNORECASE)


def agent_has_media_tools(agent_doc) -> bool:
	"""True when the agent can generate media, so MEDIA_ELEMENT_INSTRUCTIONS apply.

	Checks native Agent Tool Function names and the enabled tool names of every
	linked MCP server. Any failure degrades to False (section skipped) — prompt
	assembly must never break a run.
	"""
	try:
		for row in agent_doc.get("agent_tool") or []:
			tool_name = frappe.db.get_value("Agent Tool Function", row.tool, "tool_name") or row.tool
			if MEDIA_TOOL_NAME.search(tool_name):
				return True

		for link in agent_doc.get("agent_mcp_server") or []:
			if not link.enabled:
				continue
			for tool_name in frappe.get_all(
				"MCP Server Tool",
				filters={"parent": link.mcp_server, "enabled": 1},
				pluck="tool_name",
			):
				if MEDIA_TOOL_NAME.search(tool_name or ""):
					return True
	except Exception:
		frappe.log_error("agent_has_media_tools failed", "AI Element Instructions")

	return False
