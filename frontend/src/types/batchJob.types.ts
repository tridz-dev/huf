export type BatchJobProvider = 'OpenAI' | 'Anthropic' | 'Gemini';

export type BatchJobStatus =
  | 'Pending'
  | 'Submitted'
  | 'In Progress'
  | 'Completed'
  | 'Failed'
  | 'Cancelled'
  | 'Expired';

/**
 * Batch Job document from Frappe -- a single async batch submission created
 * for a Schedule trigger running in Batch execution mode. See
 * `TriggerScheduleExtras` for where a trigger opts into this.
 */
export interface BatchJobDoc {
  name: string;
  agent: string;
  provider?: BatchJobProvider | string;
  status?: BatchJobStatus | string;
  provider_batch_id?: string;
  request_count?: number;
  submitted_at?: string | null;
  completed_at?: string | null;
  result_summary?: Record<string, unknown> | string | null;
  estimated_cost?: number | null;
  error_message?: string | null;
  agent_trigger?: string | null;
  creation?: string;
  modified?: string;
}
