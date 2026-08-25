"""Console entry point for ``huf-acp``.

Reads site and credential configuration from the environment, wires the ACP
server to ``sys.stdin`` / ``sys.stdout``, and runs until EOF or error.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from huf.ai.acp.server import build_acp_server
from huf.ai.acp.transport import AcpTransport


def _setup_logging() -> None:
	level = os.environ.get("HUF_ACP_LOG_LEVEL", "WARNING").upper()
	logging.basicConfig(
		level=getattr(logging, level, logging.WARNING),
		format="%(asctime)s %(levelname)s %(name)s: %(message)s",
		stream=sys.stderr,
	)


async def amain() -> int:
	"""Async main: start the ACP server on stdio."""
	_setup_logging()

	try:
		transport = await AcpTransport.from_stdio()
	except Exception as exc:  # noqa: BLE001
		print(f"huf-acp: failed to open stdio transport: {exc}", file=sys.stderr)
		return 1

	try:
		_ = build_acp_server(transport)
	except ValueError as exc:
		print(f"huf-acp: {exc}", file=sys.stderr)
		return 1

	read_task = transport.start()
	try:
		await read_task
	except asyncio.CancelledError:
		pass
	finally:
		await transport.close()

	return 0


def main() -> int:
	"""Entry point for the ``huf-acp`` console script."""
	try:
		return asyncio.run(amain())
	except KeyboardInterrupt:
		return 0


if __name__ == "__main__":
	sys.exit(main())
