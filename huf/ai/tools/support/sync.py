"""Sync-to-async bridge for tool invocation."""
import asyncio


def _run_coroutine_sync(coro):
	"""Run a coroutine to completion from synchronous code, at the outermost
	sync entry point -- one shared utility rather than a new event loop per
	tool call (the bug the seam audit flagged in the old
	flow_tool_executor.execute(), §3: a fresh ``asyncio.new_event_loop()`` +
	``asyncio.set_event_loop()`` per invocation, unsafe if the calling
	thread ever already has a running loop).
	"""
	try:
		asyncio.get_running_loop()
	except RuntimeError:
		return asyncio.run(coro)

	# Already inside a running loop on this thread (e.g. called from async
	# code) -- run on a fresh thread instead of nesting loops.
	import concurrent.futures

	with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
		return pool.submit(asyncio.run, coro).result()
