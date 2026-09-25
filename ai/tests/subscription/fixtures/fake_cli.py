#!/usr/bin/env python3
"""
Deterministic fake CLI for testing provider adapters.

This standalone script (zero external dependencies beyond Python stdlib) simulates
a non-interactive provider CLI for testing. It supports session creation, resumption,
auth-status checks, and configurable timeout/image/auth-failure scenarios via env vars.

Usage examples:
  ./fake_cli.py -p "hello" --output-format json
  ./fake_cli.py -p "hello" --resume <session-id> --output-format json
  ./fake_cli.py --auth-status
  ./fake_cli.py --image /path/to/image.png -p "describe this"

Environment variables:
  FAKE_CLI_AUTH_STATE          "ready" (default) or "required" for auth-failure simulation
  FAKE_CLI_SLEEP_SECONDS       N: sleep N seconds before responding (for timeout testing)
  FAKE_CLI_FIXED_SESSION_ID    UUID: use this session ID instead of generating one
  FAKE_CLI_SUPPORTS_IMAGES     "0": reject --image flag; "1" (default): accept it
  FAKE_CLI_STATE_DIR           Directory for session state file (default: ~/.fake_cli_state)

Key behaviors matching real CLI findings (from spike):
  - New session (no --resume): returns JSON with session_id, result, usage (exit 0)
  - Resume known session: returns JSON with prior context in result, new session_id (same across resume)
  - Resume unknown session: prints plain-text error to stderr (NOT JSON), exits non-zero
  - --image flag: if supported, includes marker in JSON; if not supported, rejects with JSON error
  - Deterministic: same inputs/env vars produce same outputs (session ID unless FAKE_CLI_FIXED_SESSION_ID)
"""

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path


def get_state_dir():
	"""Get the state directory for session storage."""
	env_dir = os.environ.get('FAKE_CLI_STATE_DIR')
	if env_dir:
		return Path(env_dir)
	return Path.home() / '.fake_cli_state'


def load_sessions():
	"""Load all stored sessions from the state file."""
	state_dir = get_state_dir()
	state_file = state_dir / '.fake_cli_sessions.json'

	if state_file.exists():
		try:
			with open(state_file, 'r') as f:
				return json.load(f)
		except (json.JSONDecodeError, IOError):
			return {}
	return {}


def save_sessions(sessions):
	"""Save sessions to the state file."""
	state_dir = get_state_dir()
	state_dir.mkdir(parents=True, exist_ok=True)
	state_file = state_dir / '.fake_cli_sessions.json'

	with open(state_file, 'w') as f:
		json.dump(sessions, f, indent=2)


def get_or_create_session_id():
	"""Generate a deterministic or fixed session ID."""
	fixed_id = os.environ.get('FAKE_CLI_FIXED_SESSION_ID')
	if fixed_id:
		return fixed_id

	# Generate a deterministic session ID based on timestamp and counter
	# Use UUID v4 for uniqueness but allow override
	return str(uuid.uuid4())


def simulate_auth_check():
	"""Check auth status based on FAKE_CLI_AUTH_STATE."""
	auth_state = os.environ.get('FAKE_CLI_AUTH_STATE', 'ready')
	return {
		'loggedIn': auth_state == 'ready',
		'authMethod': 'claude.ai',
		'apiProvider': 'firstParty',
		'subscriptionType': 'max' if auth_state == 'ready' else None,
	}


def create_response_json(session_id, prompt, prior_context=None, has_image=False):
	"""Create a JSON response matching Claude's real format."""
	# Simulate token counts
	input_tokens = len(prompt.split()) * 2 + (len(prior_context.split()) * 2 if prior_context else 0)
	output_tokens = 6

	result_text = f"HELLO (session: {session_id[-8:]})"
	if prior_context:
		result_text += f" [previous: {prior_context[-20:]}]"
	if has_image:
		result_text += " [image received]"

	return {
		'session_id': session_id,
		'result': result_text,
		'usage': {
			'input_tokens': input_tokens,
			'output_tokens': output_tokens,
			'cache_creation_input_tokens': 1000,
			'cache_read_input_tokens': 500,
		},
		'modelUsage': {
			'claude-opus-5-5': {
				'inputTokens': input_tokens,
				'outputTokens': output_tokens,
				'costUSD': 0.001,
				'contextWindow': 200000,
			}
		},
		'is_error': False,
		'type': 'result',
		'duration_ms': 1500,
	}


def create_jsonl_response(session_id, prompt, prior_context=None, has_image=False):
	"""Create a JSONL response matching Codex's format (as alternative).

	Not currently used by default, but available for future Codex adapter tests.
	"""
	input_tokens = len(prompt.split()) * 2
	output_tokens = 6

	result_text = f"HELLO (session: {session_id[-8:]})"
	if prior_context:
		result_text += f" [previous: {prior_context[-20:]}]"
	if has_image:
		result_text += " [image received]"

	lines = [
		json.dumps({'type': 'thread.started', 'thread_id': session_id}),
		json.dumps({'type': 'turn.started'}),
		json.dumps({
			'type': 'item.completed',
			'item': {'id': 'item_0', 'type': 'agent_message', 'text': result_text}
		}),
		json.dumps({
			'type': 'turn.completed',
			'usage': {
				'input_tokens': input_tokens,
				'output_tokens': output_tokens,
				'cached_input_tokens': 500,
			}
		}),
	]
	return '\n'.join(lines)


def main():
	parser = argparse.ArgumentParser(
		description='Deterministic fake provider CLI for testing adapters'
	)

	parser.add_argument('-p', '--print', dest='prompt', help='Prompt text (non-interactive mode)')
	parser.add_argument('-r', '--resume', dest='resume', help='Resume a session by ID')
	parser.add_argument('--session-id', dest='session_id', help='Explicit session ID (for idempotency)')
	parser.add_argument('--output-format', choices=['json', 'text'], default='text',
					help='Output format')
	parser.add_argument('--auth-status', action='store_true', help='Print auth status')
	parser.add_argument('--image', dest='image', help='Image file path for vision input')
	parser.add_argument('--state-dir', help='Directory for session state')

	args = parser.parse_args()

	# Handle --state-dir override
	if args.state_dir:
		os.environ['FAKE_CLI_STATE_DIR'] = args.state_dir

	# Handle --auth-status
	if args.auth_status:
		status = simulate_auth_check()
		if status['loggedIn']:
			print(json.dumps(status))
			sys.exit(0)
		else:
			# Auth required: still print JSON for auth status, but flag not-ready
			print(json.dumps(status))
			sys.exit(1)

	# Simulate timeout if requested
	sleep_sec = os.environ.get('FAKE_CLI_SLEEP_SECONDS')
	if sleep_sec:
		try:
			time.sleep(float(sleep_sec))
		except (ValueError, TypeError):
			pass

	# Check if we support images
	supports_images = os.environ.get('FAKE_CLI_SUPPORTS_IMAGES', '1') == '1'

	# Handle image flag
	if args.image:
		if not supports_images:
			# Image not supported: return JSON error to stdout (not stderr)
			error_response = {
				'is_error': True,
				'type': 'error',
				'error': 'This provider does not support image input.',
			}
			print(json.dumps(error_response))
			sys.exit(1)
		# Image is supported and provided; include marker in response below

	# Validate auth state
	auth_state = os.environ.get('FAKE_CLI_AUTH_STATE', 'ready')
	if auth_state == 'required':
		# Auth required: print plain text error to stderr, exit non-zero
		print('Error: Authentication required. Please run: fake_cli auth login', file=sys.stderr)
		sys.exit(1)

	# Require a prompt in non-auth-status mode
	if not args.prompt:
		parser.print_help(file=sys.stderr)
		sys.exit(1)

	# Load/generate session ID
	sessions = load_sessions()

	if args.resume:
		# Resume mode: check if session exists
		resume_id = args.resume

		if resume_id not in sessions:
			# Unknown session: plain-text error to stderr (matching real CLI behavior)
			print(
				f'Error: --resume requires a valid session ID. Provided value "{resume_id}" '
				f'is not a UUID and does not match any session.',
				file=sys.stderr
			)
			sys.exit(1)

		# Known session: retrieve prior context and return new turn
		session_data = sessions[resume_id]
		session_id = resume_id  # Session ID stays stable across resume
		prior_result = session_data.get('last_result', '')

		# Generate response
		response = None
		if args.output_format == 'json':
			response = create_response_json(
				session_id, args.prompt, prior_context=prior_result, has_image=bool(args.image)
			)
			print(json.dumps(response))
		else:
			# Text format
			response_text = f"HELLO (session: {session_id[-8:]}) [previous: {prior_result[-20:]}]"
			print(response_text)
			response = {'result': response_text}

		# Update session with new result
		session_data['last_result'] = response.get('result', 'HELLO') if isinstance(response, dict) else 'HELLO'
		session_data['turns'] = session_data.get('turns', 0) + 1
		sessions[resume_id] = session_data
		save_sessions(sessions)

		sys.exit(0)

	else:
		# New session mode
		if args.session_id:
			session_id = args.session_id
		else:
			session_id = get_or_create_session_id()

		# Generate response
		response = None
		if args.output_format == 'json':
			response = create_response_json(session_id, args.prompt, has_image=bool(args.image))
			print(json.dumps(response))
		else:
			# Text format
			response_text = f"HELLO (session: {session_id[-8:]})"
			print(response_text)
			response = {'result': response_text}

		# Store session
		sessions[session_id] = {
			'created': time.time(),
			'last_result': response.get('result', 'HELLO') if isinstance(response, dict) else 'HELLO',
			'turns': 1,
		}
		save_sessions(sessions)

		sys.exit(0)


if __name__ == '__main__':
	main()
