import { db, call } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { handleFrappeError } from '@/lib/frappe-error';

/** Outcome of the "create a procedure from this flow on save" checkbox, as recorded on
 * the Flow Definition doc. `get_flow_definition`/`save_flow_definition` don't expose
 * these fields, so they're read straight off the doctype via the SDK. */
export interface FlowConversionStatus {
    auto_convert_to_procedure: boolean;
    /** Human-readable outcome of the last conversion attempt (success or refusal reason). */
    conversion_note: string | null;
    /** Name of the Draft Agent Procedure created/refreshed from this flow, if any. */
    converted_procedure: string | null;
}

/** Fetch the current auto-convert checkbox value and the outcome of the last conversion
 * attempt (set asynchronously by the backend after save -- see flow_definition.py's
 * _maybe_convert_to_procedure). */
export async function getFlowConversionStatus(flowId: string): Promise<FlowConversionStatus> {
    try {
        const doc = await db.getDoc(doctype['Flow Definition'], flowId);
        return {
            auto_convert_to_procedure: Boolean(doc.auto_convert_to_procedure),
            conversion_note: (doc.conversion_note as string) || null,
            converted_procedure: (doc.converted_procedure as string) || null,
        };
    } catch (error) {
        handleFrappeError(error, `Error fetching conversion status for flow ${flowId}`);
    }
}

/** Toggle the "create a procedure from this flow on save" checkbox */
export async function updateFlowAutoConvert(flowId: string, autoConvert: boolean): Promise<void> {
    try {
        await db.updateDoc(doctype['Flow Definition'], flowId, {
            auto_convert_to_procedure: autoConvert ? 1 : 0,
        });
    } catch (error) {
        handleFrappeError(error, `Error updating flow ${flowId}`);
    }
}

// ─── Flow -> Procedure conversion ───────────────────────────────────────

/** Preview of converting a flow into a deterministic procedure */
export interface FlowConversionAnalysis {
    convertible: boolean;
    reason?: string;
    reads?: string[];
    writes?: string[];
    atomic_operations?: number;
    estimated_round_trip_reduction_pct?: number;
}

/** Result of actually creating the procedure from a flow */
export interface FlowConversionResult extends FlowConversionAnalysis {
    name: string;
    procedure_id: string;
    version: number;
    status: string;
    tier: string;
}

/** Read-only preview: is this flow convertible, and what would it look like? Creates nothing. */
export async function analyzeFlowConversion(flowId: string): Promise<FlowConversionAnalysis> {
    try {
        const result = await call.get('huf.ai.flow.api.analyze_flow_conversion', {
            flow_id: flowId,
        });
        return result.message as FlowConversionAnalysis;
    } catch (error) {
        handleFrappeError(error, `Error analyzing flow ${flowId} for conversion`);
    }
}

/** Convert a deterministic flow into a Draft procedure. Never activates it. */
export async function convertFlowToProcedure(flowId: string): Promise<FlowConversionResult> {
    try {
        const result = await call.post('huf.ai.flow.api.convert_flow_to_procedure', {
            flow_id: flowId,
        });
        return result.message as FlowConversionResult;
    } catch (error) {
        handleFrappeError(error, `Error converting flow ${flowId} to a procedure`);
    }
}
