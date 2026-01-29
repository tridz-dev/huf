"""SSE Page Renderer for Agent Streaming.

This module provides Server-Sent Events (SSE) streaming for Huf agents.
Allows real-time streaming of agent responses without modifying existing DocTypes.
"""

import asyncio
import json
from typing import Generator
import urllib.parse

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer
from werkzeug.wrappers import Response

from huf.ai.agent_integration import run_agent_stream


class AgentStreamRenderer(BaseRenderer):
	"""Page renderer that handles SSE streaming for agents.

	Routes:
	- `/huf/stream/<agent_name>` - SSE endpoint that streams agent responses
	- `/huf/stream` - HTML page with EventSource client for testing
	"""

	def can_render(self) -> bool:
		"""Determine if this renderer should handle the current path."""
		return self.path == "huf/stream" or self.path.startswith("huf/stream/")

	def render(self):
		"""Render either HTML page or SSE stream based on path."""
		# Check if agent_name is in form_dict (from rule /huf/stream/<path:agent_name>)
		agent_name = frappe.form_dict.get("agent_name")
		
		# Fallback: Extract from path
		if not agent_name and self.path.startswith("huf/stream/"):
			parts = self.path.split("/")
			if len(parts) >= 3:
				agent_name = parts[2]
		
		if agent_name:
			try:
				agent_name = urllib.parse.unquote(agent_name)
			except Exception:
				pass
			return self._render_agent_stream(agent_name)
			
		elif self.path == "huf/stream":
			return self._render_html_page()
		else:
			return self._render_error("Invalid path format. Expected: /huf/stream/<agent_name>")

	def _render_agent_stream(self, agent_name: str):
		"""Generate SSE stream for agent response."""
		# Get prompt from query parameters or request body
		prompt = frappe.form_dict.get("prompt") or frappe.form_dict.get("message", "")
		
		if not prompt:
			# Try to get from POST body
			try:
				if frappe.request.method == "POST":
					body = frappe.request.get_json(force=True) or {}
					prompt = body.get("prompt") or body.get("message", "")
			except Exception:
				pass
		
		if not prompt:
			def error_generator() -> Generator[str, None, None]:
				error_data = {"type": "error", "error": "Prompt parameter required"}
				yield f"data: {json.dumps(error_data)}\n\n"
			
			return Response(
				error_generator(),
				mimetype="text/event-stream",
				headers={
					"Cache-Control": "no-cache",
					"Connection": "keep-alive",
					"X-Accel-Buffering": "no",
				},
			)
		
		# Get agent configuration
		try:
			agent_doc = frappe.get_doc("Agent", agent_name)
			provider = agent_doc.provider
			model_doc = frappe.get_doc("AI Model", agent_doc.model)
			model = model_doc.model_name
		except frappe.DoesNotExistError:
			def error_generator() -> Generator[str, None, None]:
				error_data = {"type": "error", "error": f"Agent '{agent_name}' not found"}
				yield f"data: {json.dumps(error_data)}\n\n"
			
			return Response(
				error_generator(),
				mimetype="text/event-stream",
				headers={
					"Cache-Control": "no-cache",
					"Connection": "keep-alive",
					"X-Accel-Buffering": "no",
				},
			)
		except Exception as e:
			def error_generator() -> Generator[str, None, None]:
				error_data = {"type": "error", "error": f"Error loading agent: {str(e)}"}
				yield f"data: {json.dumps(error_data)}\n\n"
			
			return Response(
				error_generator(),
				mimetype="text/event-stream",
				headers={
					"Cache-Control": "no-cache",
					"Connection": "keep-alive",
					"X-Accel-Buffering": "no",
				},
			)
		
		# Get optional parameters
		channel_id = frappe.form_dict.get("channel_id", "sse_stream")
		external_id = frappe.form_dict.get("external_id") or frappe.session.user
		
		conversation_id = frappe.form_dict.get("conversation_id") or frappe.form_dict.get("conversation")
		if not conversation_id:
			try:
				if frappe.request.method == "POST":
					body = frappe.request.get_json(force=True) or {}
					conversation_id = body.get("conversation_id") or body.get("conversation")
			except Exception:
				pass
		
		# Create async generator wrapper
		def stream_generator() -> Generator[str, None, None]:
			"""Wrapper to convert async generator to sync generator for Werkzeug Response."""
			loop = None
			try:
				# Try to get existing event loop
				try:
					loop = asyncio.get_event_loop()
				except RuntimeError:
					loop = asyncio.new_event_loop()
					asyncio.set_event_loop(loop)
				
				# Create async generator
				async_gen = run_agent_stream(
					agent_name=agent_name,
					prompt=prompt,
					provider=provider,
					model=model,
					channel_id=channel_id,
					external_id=external_id,
					conversation_id=conversation_id
				)
				
				# Convert async generator to sync
				while True:
					try:
						chunk = loop.run_until_complete(async_gen.__anext__())
						yield f"data: {json.dumps(chunk)}\n\n"
						
						# Check if stream is complete
						if chunk.get("type") in ("complete", "error"):
							break
					except StopAsyncIteration:
						break
					except Exception as e:
						error_data = {"type": "error", "error": str(e)}
						yield f"data: {json.dumps(error_data)}\n\n"
						break
			except Exception as e:
				error_data = {"type": "error", "error": f"Stream setup error: {str(e)}"}
				yield f"data: {json.dumps(error_data)}\n\n"
			finally:
				# Don't close loop if it was already running
				if loop and loop != asyncio.get_event_loop():
					try:
						loop.close()
					except Exception:
						pass
		
		response = Response(
			stream_generator(),
			mimetype="text/event-stream",
			headers={
				"Cache-Control": "no-cache",
				"Connection": "keep-alive",
				"X-Accel-Buffering": "no",
			},
		)
		
		return response

	def _render_error(self, error_message: str):
		"""Render error response."""
		error_data = {"error": error_message}
		json_response = json.dumps(error_data, indent=2)
		headers = {"Content-Type": "application/json; charset=utf-8"}
		return self.build_response(json_response, headers=headers, http_status_code=400)

	def _render_html_page(self):
		"""Render HTML page with EventSource client for testing."""
		html_content = """<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="UTF-8">
	<meta name="viewport" content="width=device-width, initial-scale=1.0">
	<title>Huf Streaming Demo</title>
	<style>
		body {
			font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
			max-width: 900px;
			margin: 0 auto;
			padding: 20px;
			background-color: #f5f5f5;
		}
		.container {
			background: white;
			padding: 2rem;
			border-radius: 8px;
			box-shadow: 0 2px 8px rgba(0,0,0,0.1);
		}
		h1 {
			margin-top: 0;
			color: #333;
		}
		.form-group {
			margin-bottom: 15px;
		}
		label {
			display: block;
			margin-bottom: 5px;
			font-weight: bold;
			color: #555;
		}
		input, textarea {
			width: 100%;
			padding: 10px;
			font-size: 16px;
			border: 1px solid #ddd;
			border-radius: 4px;
			box-sizing: border-box;
		}
		textarea {
			min-height: 100px;
			resize: vertical;
		}
		button {
			background-color: #007bff;
			color: white;
			border: none;
			padding: 10px 20px;
			border-radius: 4px;
			cursor: pointer;
			font-size: 16px;
			margin-right: 10px;
		}
		button:hover {
			background-color: #0056b3;
		}
		button:disabled {
			background-color: #6c757d;
			cursor: not-allowed;
		}
		#response {
			margin-top: 20px;
			padding: 15px;
			border: 1px solid #ddd;
			border-radius: 4px;
			min-height: 200px;
			background-color: #f9f9f9;
			white-space: pre-wrap;
			font-family: 'Courier New', monospace;
			font-size: 14px;
			line-height: 1.6;
		}
		.status {
			padding: 10px;
			margin-bottom: 10px;
			border-radius: 4px;
			font-weight: bold;
		}
		.status.streaming {
			background-color: #d4edda;
			color: #155724;
		}
		.status.error {
			background-color: #f8d7da;
			color: #721c24;
		}
		.status.complete {
			background-color: #d1ecf1;
			color: #0c5460;
		}
	</style>
</head>
<body>
	<div class="container">
		<h1>Huf Streaming Demo</h1>
		
		<div id="status"></div>
		
		<div class="form-group">
			<label for="agent-name">Agent Name:</label>
			<input type="text" id="agent-name" placeholder="Enter agent name..." />
		</div>
		
		<div class="form-group">
			<label for="prompt-input">Message:</label>
			<textarea id="prompt-input" placeholder="Enter your message...">Hello! Can you help me?</textarea>
		</div>
		
		<button id="stream-btn" onclick="streamResponse()">Stream Response</button>
		<button onclick="stopStream()">Stop</button>
		
		<div id="response"></div>
	</div>

	<script>
		let eventSource = null;
		const responseDiv = document.getElementById('response');
		const statusDiv = document.getElementById('status');
		const promptInput = document.getElementById('prompt-input');
		const agentNameInput = document.getElementById('agent-name');
		const streamBtn = document.getElementById('stream-btn');

		function updateStatus(message, type = '') {
			statusDiv.textContent = message;
			statusDiv.className = 'status ' + type;
		}

		function streamResponse() {
			const agentName = agentNameInput.value.trim();
			const prompt = promptInput.value.trim();
			
			if (!agentName) {
				alert('Please enter an agent name');
				return;
			}
			
			if (!prompt) {
				alert('Please enter a message');
				return;
			}

			// Close existing connection
			if (eventSource) {
				eventSource.close();
			}

			// Clear previous response
			responseDiv.textContent = '';
			updateStatus('Connecting...', 'streaming');
			streamBtn.disabled = true;

			// Create SSE connection
			const encodedPrompt = encodeURIComponent(prompt);
			const url = `/huf/stream/${encodeURIComponent(agentName)}?prompt=${encodedPrompt}`;
			eventSource = new EventSource(url);

			// Handle streaming deltas
			eventSource.onmessage = function(event) {
				try {
					const data = JSON.parse(event.data);
					
					if (data.type === 'delta') {
						// Update response with accumulated content
						responseDiv.textContent = data.full_response || '';
						updateStatus('Streaming...', 'streaming');
					} else if (data.type === 'tool_call') {
						// Show tool call info
						const toolName = data.tool_call?.function?.name || 'Unknown';
					} else if (data.type === 'complete') {
						// Handle completion
						responseDiv.textContent = data.full_response || responseDiv.textContent;
						updateStatus('Completed', 'complete');
						eventSource.close();
						streamBtn.disabled = false;
					}
				} catch (e) {
					console.error('Error parsing event:', e);
				}
			};

			// Handle errors
			eventSource.onerror = function(error) {
				console.error('SSE Error:', error);
				
				// Try to parse error from last message
				try {
					const lastEvent = eventSource.lastEventId;
					// Error might be in the data
				} catch (e) {
					// Ignore
				}
				
				updateStatus('Connection error', 'error');
				eventSource.close();
				streamBtn.disabled = false;
			};
		}

		function stopStream() {
			if (eventSource) {
				eventSource.close();
				eventSource = null;
				updateStatus('Stopped', '');
				streamBtn.disabled = false;
			}
		}
	</script>
</body>
</html>"""

		headers = {"Content-Type": "text/html; charset=utf-8"}
		return self.build_response(html_content, headers=headers)

