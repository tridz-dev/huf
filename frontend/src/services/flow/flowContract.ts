import type { BackendContract, BackendNode } from '../flowApi';

// ─── Contract defaults ────────────────────────────────────────────────

/**
 * A permissive, empty-blast-radius default contract. The graph-IR `contract` is
 * required on every graph (input/output schema, applies_when, permission envelope,
 * limits) but the canvas has no way to derive a real permission envelope or I/O schema
 * for a hand-drawn Flow -- that derivation is `huf.ai.graph.permissions.compute_static_envelope`'s
 * job, run server-side against the actual node configs once the tool/agent registry is
 * reachable. This default keeps a freshly drawn Flow schema-valid (empty envelope,
 * generous but finite limits) until a real permission-authoring UI exists; a Flow that
 * needs elevated read/write/http/code permissions still has to have those added to its
 * `contract.permission_envelope` by hand today.
 */
export function defaultContract(): BackendContract {
    return {
        input_schema: { type: 'object' },
        output_schema: { type: 'object' },
        applies_when: [],
        permission_envelope: { read: [], write: [], http: 'none', code: 'none' },
        limits: {
            max_nodes: 200,
            max_rows: 10_000,
            max_output_bytes: 1_000_000,
            max_parallel_calls: 4,
            max_foreach_iterations: 1_000,
            max_external_calls: 200,
            max_writes: 100,
            max_wall_time_ms: 5 * 60 * 1000,
            fail_closed: true,
        },
    };
}

/**
 * A non-cryptographic, deterministic placeholder fingerprint. The graph-IR schema only
 * checks the *shape* of `fingerprint` (64 lowercase hex chars, graph-ir.md section 7) --
 * it does not itself recompute and compare it against the graph's canonical form, so a
 * stable placeholder is schema-valid. A real content-addressed fingerprint (matching
 * `huf.ai.procedure.versioning.compute_fingerprint`'s algorithm) is intentionally left
 * as backend-computed, not duplicated in the frontend.
 */
export function placeholderFingerprint(seed: string): string {
    let h1 = 0xdeadbeef;
    let h2 = 0x41c6ce57;
    for (let i = 0; i < seed.length; i++) {
        const ch = seed.charCodeAt(i);
        h1 = Math.imul(h1 ^ ch, 2654435761);
        h2 = Math.imul(h2 ^ ch, 1597334677);
    }
    h1 = (h1 ^ (h1 >>> 16)) >>> 0;
    h2 = (h2 ^ (h2 >>> 16)) >>> 0;
    const hex = (h1.toString(16).padStart(8, '0') + h2.toString(16).padStart(8, '0')).repeat(4);
    return hex.slice(0, 64);
}

/** Default contract plus the envelope surfaces the graph's own nodes require. */
export function deriveContract(nodes: BackendNode[]): BackendContract {
    const contract = defaultContract();
    const toolIds = new Set(
        nodes.filter((n) => n.type === 'tool.call').map((n) => n.config.tool_id).filter((t): t is string => typeof t === 'string')
    );
    if (toolIds.has('http_request')) contract.permission_envelope.http = ['http_request'];
    if (toolIds.has('run_python')) contract.permission_envelope.code = ['run_python'];
    const writes = new Set(
        nodes.filter((n) => n.type === 'doc.create').map((n) => n.config.doctype).filter((d): d is string => typeof d === 'string' && d !== '')
    );
    contract.permission_envelope.write = [...writes].sort().map((doctype) => ({ doctype }));
    return contract;
}
