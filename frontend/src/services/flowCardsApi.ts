import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';

/** What starts a flow, as the Flows list receives it (no secrets: the webhook secret never comes with it). */
export interface FlowCardTrigger {
    type: 'webhook' | 'schedule' | 'doc-event' | 'unset';
    method?: string;
    cron?: string;
    doctype?: string;
    event?: string;
}

export interface FlowCardStep {
    /** Backend node type, e.g. `condition`, `tool.call`. */
    type: string;
    tool_id?: string;
}

export interface FlowCardLastRun {
    /** Stored run status: Queued, Running, Waiting Approval, Waiting User, Waiting Code, Success, Failed. */
    status: string;
    stale: boolean;
    /** UTC ISO time the run finished (or started, or last changed). */
    at: string | null;
    /** Title of the step a failed run stopped at. */
    failed_step?: string;
}

export interface FlowCard {
    flow_id: string;
    flow_name: string;
    description: string;
    category: string;
    status: 'Draft' | 'Active' | 'Archived';
    modified: string | null;
    trigger: FlowCardTrigger;
    steps: FlowCardStep[];
    step_count: number;
    last_run: FlowCardLastRun | null;
}

export type FlowListSort = 'recent' | 'name' | 'oldest';

export interface FlowCardsQuery {
    search?: string;
    status?: string;
    category?: string;
    sort?: FlowListSort;
    limit?: number;
    start?: number;
}

/** One page of flows with everything a list card shows. */
export async function listFlowCards(query: FlowCardsQuery = {}): Promise<{ items: FlowCard[]; total: number }> {
    try {
        const result = await call.get('huf.ai.flow.flow_cards.list_flow_cards', { ...query });
        return result.message as { items: FlowCard[]; total: number };
    } catch (error) {
        handleFrappeError(error, 'Error fetching flows');
    }
}

/** Categories that flows already use. */
export async function listFlowCategories(): Promise<string[]> {
    try {
        const result = await call.get('huf.ai.flow.flow_cards.list_flow_categories');
        return (result.message as string[]) ?? [];
    } catch {
        return [];
    }
}

/** A step of the new flow that cannot work until something is set up. */
export interface NeedsSetup {
    node_id: string;
    title: string;
    what: string;
    service?: string;
}

export interface CreatedFlow {
    flow_id: string;
    flow_name: string;
    needs_setup: NeedsSetup[];
}

/** Copy a flow into a new draft ("<name> (copy)") with a fresh webhook secret. */
export async function cloneFlow(flowId: string): Promise<CreatedFlow> {
    try {
        const result = await call.post('huf.ai.flow.clone.clone_flow', { flow_id: flowId });
        return result.message as CreatedFlow;
    } catch (error) {
        handleFrappeError(error, `Error copying flow ${flowId}`);
    }
}

/** Start a new draft from a template's steps. */
export async function createFlowFromTemplate(input: {
    name: string;
    description: string;
    category: string;
    definition: unknown;
}): Promise<CreatedFlow> {
    try {
        const result = await call.post('huf.ai.flow.clone.create_flow_from_template', {
            name: input.name,
            description: input.description,
            category: input.category,
            definition_json: JSON.stringify(input.definition),
        });
        return result.message as CreatedFlow;
    } catch (error) {
        handleFrappeError(error, 'Error creating the flow from a template');
    }
}
