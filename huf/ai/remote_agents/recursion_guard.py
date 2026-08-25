"""
V1 recursion/loop guard for Huf's remote-agent-invocation paths (HTTP federation in PR #661,
and this track's ACP paths).

Addresses opus-5-low review finding P0.8 (2026-08-25): nothing today stops agent A calling a
connection that resolves back to the same Huf site, or two sites calling each other in a cycle.

Design, deliberately simple for V1 ("good enough", not the final word):

- Every outbound remote-agent call carries a call chain: an ordered list of hop identifiers,
  each hop identifying (site, agent) that has already been entered for this logical request.
- A hop identifier is caller-supplied and protocol-agnostic on purpose — for HTTP federation it's
  naturally `(site_base_url, agent_id)`; for ACP it'll be `(connection_name-or-process-identity,
  agent_id)`. This module does not know or care which protocol is calling it.
- Before making a new outbound call, the caller asks `guard.check_and_extend(chain, next_hop)`:
    - rejects (RemoteAgentRecursionError) if `next_hop` already appears anywhere in `chain`
      (cycle, including immediate self-call: A -> A)
    - rejects if extending the chain would exceed `MAX_HOPS`
    - otherwise returns the new, extended chain to attach to the outbound request
- The chain travels with the request (as a request header for HTTP, or a field in the ACP
  session/new params for ACP) so the *next* hop in the chain can perform the same check with full
  history, not just knowledge of its own single caller. This is what catches indirect cycles
  (A -> B -> C -> A), not just direct self-calls.

Not covered by V1 (documented, not solved here):
- No cryptographic integrity on the chain — a malicious remote site could truncate/forge the
  chain it received before relaying a further call. Sufficient for cooperating Huf-federated
  instances (the realistic V1 threat model: accidental misconfiguration, not adversarial relay
  hardening) but not a defense against a hostile remote agent lying about hop history. If that
  threat model becomes real, the chain needs signing — flagged for a future pass, not built now.
- No cross-process shared state — this is a pure function over the chain the caller passes in,
  it does not maintain a server-side call registry. Good enough because the chain travels with
  the request; a registry would add real complexity (expiry, cleanup, distributed storage) for
  marginal benefit over a self-carried, bounded-length chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from huf.ai.remote_agents.exceptions import RemoteAgentRecursionError

MAX_HOPS = 8  # generous enough for any legitimate fan-out depth Huf's design anticipates today


@dataclass(frozen=True)
class CallChain:
	"""
	Immutable ordered record of hops a logical remote-agent-invocation request has already
	passed through. `hops` is a tuple of opaque string identifiers - callers decide the format
	(e.g. f"{site_base_url}|{agent_id}"); this module treats them as opaque.
	"""

	hops: tuple[str, ...] = field(default_factory=tuple)

	@classmethod
	def start(cls, origin_hop: str) -> CallChain:
		"""A fresh chain for a request originating at `origin_hop` (the first caller)."""
		return cls(hops=(origin_hop,))

	def extended(self, next_hop: str) -> CallChain:
		return CallChain(hops=(*self.hops, next_hop))

	def to_header_value(self) -> str:
		"""Serialize for transport (e.g. an HTTP header, or a plain string field in an ACP
		session/new params dict). Simple comma-join is sufficient - hop identifiers are expected
		to be opaque tokens, not free text; callers are responsible for choosing a hop-id format
		with no embedded commas."""
		return ",".join(self.hops)

	@classmethod
	def from_header_value(cls, value: str | None) -> CallChain:
		"""Parse an incoming chain from transport. Empty/missing value means this is the origin
		of a new logical request - returns an empty chain, NOT an error (a request with no prior
		chain is not itself a recursion signal; it's the normal case for every top-level call)."""
		if not value:
			return cls(hops=())
		return cls(hops=tuple(h for h in value.split(",") if h))


def check_and_extend(chain: CallChain, next_hop: str, max_hops: int = MAX_HOPS) -> CallChain:
	"""
	The single entry point callers should use before making an outbound remote-agent call.

	Raises RemoteAgentRecursionError if `next_hop` already appears in `chain` (direct or
	indirect cycle - covers A->A and A->B->C->A alike, since the full chain is checked, not just
	the immediate predecessor) or if extending would exceed `max_hops`.

	Returns the new chain to attach to the outbound request on success.
	"""
	if next_hop in chain.hops:
		raise RemoteAgentRecursionError(
			f"Recursive remote-agent call detected: {next_hop!r} already appears in the call "
			f"chain {list(chain.hops)!r}. Refusing to call it again.",
			chain=list(chain.hops),
			attempted_hop=next_hop,
		)

	if len(chain.hops) >= max_hops:
		raise RemoteAgentRecursionError(
			f"Remote-agent call chain exceeds the maximum allowed depth ({max_hops}). "
			f"Chain so far: {list(chain.hops)!r}. This is almost always a misconfigured "
			f"loop, not a legitimate deep fan-out - refusing to extend further.",
			chain=list(chain.hops),
			attempted_hop=next_hop,
		)

	return chain.extended(next_hop)
