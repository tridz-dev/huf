import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type { SampleSource } from '@/lib/flow-test/testModel';

const NS = 'huf.ai.flow.testrun.step_test_api';

/** One piece of the data a step receives: what the flow starts with, an earlier step's result, or the loop item. */
export interface StepTestPart {
  key: string;
  title: string;
  kind: 'input' | 'step' | 'item';
  source: SampleSource;
  value: unknown;
  shortened: boolean;
  ran_at: string | null;
}

export interface StepSampleInput {
  input: Record<string, unknown>;
  steps: Record<string, unknown>;
  item?: unknown;
}

export interface StepTestInfo {
  flow_id: string;
  node_id: string;
  kind: string;
  effect: 'reads' | 'changes' | 'sends';
  calls_ai: boolean;
  simulated: boolean;
  approval: boolean;
  trigger: boolean;
  trigger_kind: 'webhook' | 'schedule' | 'doc-event' | 'unset' | null;
  doctype?: string | null;
  parts: StepTestPart[];
  sample_input: StepSampleInput;
}

export interface ApprovalPreview {
  title: string;
  note: string;
  facts: { label: string; value: string }[];
  who_can_decide: string;
}

export interface StepTestResult {
  status: 'success' | 'failed';
  mode: 'real' | 'simulated' | 'preview';
  output: unknown;
  output_shortened: boolean;
  /** The 8 KB, secrets-hidden copy that "Pin this output" stores. */
  pin_value: unknown;
  duration_ms: number;
  error: string | null;
  fix_hint: string | null;
  tested_at: string;
  effect: 'reads' | 'changes' | 'sends';
  calls_ai: boolean;
  summary: string | null;
  preview: ApprovalPreview | null;
  goes_to: string | null;
  branch: 'Yes' | 'No' | null;
  /** Things worth knowing about this answer (a source with no sample). */
  warnings: string[];
}

/** A slow step (AI, web reads, loops) answers at once with a token; the page then asks `getStepTestResult` once a second. */
export interface StepTestPending {
  status: 'running';
  token: string;
  poll_after_ms: number;
  wait_up_to_s: number;
}

export const isStepTestPending = (value: StepTestResult | StepTestPending): value is StepTestPending => value.status === 'running';

export interface RecentDocument {
  name: string;
  title: string;
  modified: string;
}

export async function getStepTestInfo(flowId: string, nodeId: string): Promise<StepTestInfo> {
  try {
    const result = await call.post(`${NS}.get_step_test_info`, { flow_id: flowId, node_id: nodeId });
    return result.message as StepTestInfo;
  } catch (error) {
    handleFrappeError(error, 'Could not load the sample data for this step');
  }
}

export async function testStep(flowId: string, nodeId: string, sampleInput?: StepSampleInput | Record<string, unknown>): Promise<StepTestResult | StepTestPending> {
  try {
    const result = await call.post(`${NS}.test_step`, { flow_id: flowId, node_id: nodeId, ...(sampleInput ? { sample_input: sampleInput } : {}) });
    return result.message as StepTestResult | StepTestPending;
  } catch (error) {
    handleFrappeError(error, 'The test could not run');
  }
}

export async function getStepTestResult(token: string): Promise<StepTestResult | StepTestPending> {
  try {
    const result = await call.post(`${NS}.get_step_test_result`, { token });
    return result.message as StepTestResult | StepTestPending;
  } catch (error) {
    handleFrappeError(error, 'The test could not run');
  }
}

export async function listRecentDocuments(flowId: string, nodeId: string): Promise<{ doctype: string; documents: RecentDocument[] }> {
  try {
    const result = await call.post(`${NS}.list_recent_documents`, { flow_id: flowId, node_id: nodeId });
    return result.message as { doctype: string; documents: RecentDocument[] };
  } catch (error) {
    handleFrappeError(error, 'Could not load recent documents');
  }
}

export async function getDocumentSample(flowId: string, nodeId: string, docname: string): Promise<{ sample: Record<string, unknown>; shortened: boolean }> {
  try {
    const result = await call.post(`${NS}.get_document_sample`, { flow_id: flowId, node_id: nodeId, docname });
    return result.message as { sample: Record<string, unknown>; shortened: boolean };
  } catch (error) {
    handleFrappeError(error, 'Could not open that document');
  }
}
