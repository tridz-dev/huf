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

/** How one compiled step's argument was bound, for the review dialog. */
export interface ProcedureProposalArgBinding {
  /** 'input' = from a declared input field, 'step' = from a prior step's output, 'constant' = fixed value. */
  source: 'input' | 'step' | 'constant';
  /** Input field name, source step id, or the literal constant value depending on `source`. */
  value: unknown;
}

/** One compiled step in the proposed procedure graph, for readable rendering. */
export interface ProcedureProposalStep {
  id?: string;
  tool?: string;
  name?: string;
  args?: Record<string, ProcedureProposalArgBinding | unknown>;
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
  steps?: ProcedureProposalStep[];
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
