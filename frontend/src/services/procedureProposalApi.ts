import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

// ─── Run -> Procedure proposal (huf.ai.procedure_proposal) ─────────────
//
// Two-step flow for turning a completed Agent Run into a deterministic
// Procedure: `propose_procedure_from_run` is a read-only PREVIEW (nothing
// is saved), `accept_procedure_proposal` actually creates the Procedure as
// a Draft. This mirrors the Flow -> Procedure conversion pattern in
// flowApi.ts (`analyzeFlowConversion` / `convertFlowToProcedure`), but the
// source here is a single Agent Run's tool-call trace rather than a Flow
// graph.

/**
 * A reference to another value in the graph, as emitted by the backend compiler:
 * `{"$from": "input.city"}` (a field the user supplies when running the procedure) or
 * `{"$from": "step2_search_web"}` (an earlier node's recorded output). Any other value in
 * a node's `config.input` is a literal constant baked into the procedure.
 */
export interface ProcedureGraphRef {
  $from: string;
}

/**
 * One node of the compiled graph. The backend emits `type: "tool.call"` nodes carrying
 * `config.tool_id` / `config.input`, chained by `next`, terminating in a single
 * `type: "output"` node -- see huf/ai/procedure_proposal.py::compile_procedure_from_trace.
 */
export interface ProcedureProposalNode {
  id: string;
  type: string;
  next?: string;
  config?: {
    tool_id?: string;
    input?: Record<string, ProcedureGraphRef | unknown>;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

/** Detected input field for the proposed procedure. */
export interface ProcedureProposalInputField {
  name: string;
  type?: string;
  description?: string;
  required?: boolean;
  [key: string]: unknown;
}

/** The compiled graph as returned by the backend -- shape mirrors the shared graph-IR
 * used by Flow/Procedure definitions (huf/ai/graph/graph_ir.schema.json), but this
 * dialog treats it as opaque/readable data, never as something to edit structurally. */
export type ProcedureProposalGraph = {
  entry?: string;
  nodes?: ProcedureProposalNode[];
  [key: string]: unknown;
};

/** Preview response from `propose_procedure_from_run`. Nothing is saved yet. */
export interface ProcedureProposal {
  proposable: boolean;
  /** Present (and the whole point) when `proposable` is false -- an honest, non-error explanation. */
  reason?: string;
  procedure_graph?: ProcedureProposalGraph;
  input_schema?: ProcedureProposalInputField[] | Record<string, unknown>;
  step_count?: number;
  source_run?: string;
}

/** Result of actually creating the procedure from an accepted proposal. */
export interface ProcedureProposalAcceptResult {
  name: string;
  procedure_id: string;
  version: number;
  status: string;
}

/** Read-only preview: can this Agent Run become a deterministic procedure, and what
 * would it look like? Creates nothing. */
export async function proposeProcedureFromRun(agentRunName: string): Promise<ProcedureProposal> {
  try {
    const result = await call.get('huf.ai.procedure_proposal.propose_procedure_from_run', {
      agent_run_name: agentRunName,
    });
    return result.message as ProcedureProposal;
  } catch (error) {
    handleFrappeError(error, `Error proposing a procedure from run ${agentRunName}`);
    throw error;
  }
}

/** Accepts a previously previewed proposal, creating the Procedure as a Draft. Never
 * activates it -- the caller still has to review and enable it elsewhere. */
export async function acceptProcedureProposal(
  agentRunName: string,
  procedureGraph: ProcedureProposalGraph,
  procedureName: string
): Promise<ProcedureProposalAcceptResult> {
  try {
    const result = await call.post('huf.ai.procedure_proposal.accept_procedure_proposal', {
      agent_run_name: agentRunName,
      procedure_graph: JSON.stringify(procedureGraph),
      procedure_name: procedureName,
    });
    return result.message as ProcedureProposalAcceptResult;
  } catch (error) {
    handleFrappeError(error, 'Error accepting the procedure proposal');
    throw error;
  }
}
