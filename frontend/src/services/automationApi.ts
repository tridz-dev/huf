import { call } from '@/lib/frappe-sdk';
import { handleFrappeError } from '@/lib/frappe-error';
import type {
  Automation,
  AutomationTrigger,
  AutomationTriggerAttachment,
  AutomationTriggerSummary,
  DeleteAutomationResponse,
  DeleteTriggerResponse,
  RunAutomationNowResponse,
  ScheduledAutomationSummary,
} from '@/types/automation.types';

// ---------------------------------------------------------------------------
// Automation CRUD / lifecycle
// ---------------------------------------------------------------------------

export interface ListAutomationsParams {
  agent?: string;
  status?: string;
}

/**
 * List Automations visible to the current user.
 */
export async function listAutomations(params: ListAutomationsParams = {}): Promise<Automation[]> {
  try {
    const result = await call.get('huf.ai.automation_api.list_automations', {
      agent: params.agent ?? undefined,
      status: params.status ?? undefined,
    });
    return (result?.message ?? result) as Automation[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching automations');
    return [];
  }
}

/**
 * Get a single Automation.
 */
export async function getAutomation(automation: string): Promise<Automation | undefined> {
  try {
    const result = await call.get('huf.ai.automation_api.get_automation', { automation });
    return (result?.message ?? result) as Automation;
  } catch (error) {
    handleFrappeError(error, 'Error fetching automation');
  }
}

export interface CreateAutomationParams {
  automation_name: string;
  agent: string;
  instruction: string;
  description?: string;
  project?: string;
  model_override?: string;
  run_as_user?: string;
  input_template?: string;
  conversation_mode?: string;
  conversation?: string;
  notify_user?: 0 | 1;
  source_system?: string;
  metadata?: string | Record<string, unknown>;
}

/**
 * Create a new Automation (always starts in Draft status).
 */
export async function createAutomation(params: CreateAutomationParams): Promise<Automation> {
  try {
    const result = await call.post('huf.ai.automation_api.create_automation', {
      automation_name: params.automation_name,
      agent: params.agent,
      instruction: params.instruction,
      description: params.description ?? undefined,
      project: params.project ?? undefined,
      model_override: params.model_override ?? undefined,
      run_as_user: params.run_as_user ?? undefined,
      input_template: params.input_template ?? undefined,
      conversation_mode: params.conversation_mode ?? undefined,
      conversation: params.conversation ?? undefined,
      notify_user: params.notify_user ?? undefined,
      source_system: params.source_system ?? undefined,
      metadata: params.metadata ?? undefined,
    });
    return (result?.message ?? result) as Automation;
  } catch (error) {
    handleFrappeError(error, 'Error creating automation');
    throw error;
  }
}

export interface UpdateAutomationParams {
  automation: string;
  automation_name?: string;
  description?: string;
  status?: string;
  disabled?: 0 | 1;
  agent?: string;
  model_override?: string;
  project?: string;
  run_as_user?: string;
  instruction?: string;
  input_template?: string;
  conversation_mode?: string;
  conversation?: string;
  notify_user?: 0 | 1;
  source_system?: string;
  metadata?: string | Record<string, unknown>;
}

/**
 * Update an existing Automation. Only known, explicit fields are accepted
 * server-side (see huf.ai.automation_service._UPDATABLE_FIELDS).
 */
export async function updateAutomation(params: UpdateAutomationParams): Promise<Automation> {
  try {
    const { automation, ...fields } = params;
    const result = await call.post('huf.ai.automation_api.update_automation', {
      automation,
      ...fields,
    });
    return (result?.message ?? result) as Automation;
  } catch (error) {
    handleFrappeError(error, 'Error updating automation');
    throw error;
  }
}

/**
 * Archive an Automation (status transition, not a destructive delete).
 */
export async function archiveAutomation(automation: string): Promise<Automation> {
  try {
    const result = await call.post('huf.ai.automation_api.archive_automation', { automation });
    return (result?.message ?? result) as Automation;
  } catch (error) {
    handleFrappeError(error, 'Error archiving automation');
    throw error;
  }
}

/**
 * Permanently delete an Automation. Only allowed while Draft or Archived.
 */
export async function deleteAutomation(automation: string): Promise<DeleteAutomationResponse> {
  try {
    const result = await call.post('huf.ai.automation_api.delete_automation', { automation });
    return (result?.message ?? result) as DeleteAutomationResponse;
  } catch (error) {
    handleFrappeError(error, 'Error deleting automation');
    return { success: false };
  }
}

/**
 * Run an Automation immediately (bypassing any trigger/schedule).
 */
export async function runAutomationNow(automation: string): Promise<RunAutomationNowResponse> {
  try {
    const result = await call.post('huf.ai.automation_api.run_automation_now', { automation });
    return (result?.message ?? result) as RunAutomationNowResponse;
  } catch (error) {
    handleFrappeError(error, 'Error running automation');
    throw error;
  }
}

/**
 * Pause an Automation (status -> Paused).
 */
export async function pauseAutomation(automation: string): Promise<Automation> {
  try {
    const result = await call.post('huf.ai.automation_api.pause_automation', { automation });
    return (result?.message ?? result) as Automation;
  } catch (error) {
    handleFrappeError(error, 'Error pausing automation');
    throw error;
  }
}

/**
 * Resume a paused (or draft/error) Automation (status -> Active).
 */
export async function resumeAutomation(automation: string): Promise<Automation> {
  try {
    const result = await call.post('huf.ai.automation_api.resume_automation', { automation });
    return (result?.message ?? result) as Automation;
  } catch (error) {
    handleFrappeError(error, 'Error resuming automation');
    throw error;
  }
}

// ---------------------------------------------------------------------------
// Automation Trigger CRUD
// ---------------------------------------------------------------------------

/**
 * List Automation Trigger rows for an Automation.
 */
export async function listTriggers(automation: string): Promise<AutomationTriggerSummary[]> {
  try {
    const result = await call.get('huf.ai.automation_api.list_triggers', { automation });
    return (result?.message ?? result) as AutomationTriggerSummary[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching triggers');
    return [];
  }
}

export interface CreateTriggerParams {
  automation: string;
  trigger_type: string;
  trigger_name?: string;
  disabled?: 0 | 1;
  // Schedule
  schedule_type?: string;
  cron_expression?: string;
  run_at?: string;
  scheduled_interval?: string;
  timezone?: string;
  start_at?: string;
  end_at?: string;
  misfire_policy?: string;
  interval_count?: number;
  // Doc Event
  reference_doctype?: string;
  doc_event?: string;
  prompt_field?: string;
  prompt_field_mode?: string;
  condition?: string;
  // Doc Event child table. NOTE: as of this writing,
  // huf.ai.automation_api's `_TRIGGER_FIELDS` (both create_trigger and
  // update_trigger use it) does not include `file_attachments`, so this
  // value is silently dropped server-side today -- included here so the
  // client contract is correct once that backend gap is closed. Flagged
  // for a follow-up backend fix; out of scope for this frontend task.
  file_attachments?: AutomationTriggerAttachment[];
  // Webhook
  webhook_slug?: string;
  webhook_key?: string;
  allowed_methods?: string;
  auth_mode?: string;
  signature_header?: string;
  secret?: string;
  response_mode?: string;
  // App Event
  app_name?: string;
  event_name?: string;
  event_source?: string;
  payload_mapping?: string;
  // Shared
  source_system?: string;
  metadata?: string | Record<string, unknown>;
  disabled_reason?: string;
}

/**
 * Create an Automation Trigger for an Automation.
 */
export async function createTrigger(params: CreateTriggerParams): Promise<AutomationTrigger> {
  try {
    const { automation, trigger_type, ...fields } = params;
    const result = await call.post('huf.ai.automation_api.create_trigger', {
      automation,
      trigger_type,
      ...fields,
    });
    return (result?.message ?? result) as AutomationTrigger;
  } catch (error) {
    handleFrappeError(error, 'Error creating trigger');
    throw error;
  }
}

export interface UpdateTriggerParams extends Omit<CreateTriggerParams, 'automation' | 'trigger_type'> {
  trigger: string;
}

/**
 * Update an existing Automation Trigger. `automation` cannot be reassigned
 * through this endpoint (matches huf.ai.automation_api.update_trigger).
 */
export async function updateTrigger(params: UpdateTriggerParams): Promise<AutomationTrigger> {
  try {
    const { trigger, ...fields } = params;
    const result = await call.post('huf.ai.automation_api.update_trigger', {
      trigger,
      ...fields,
    });
    return (result?.message ?? result) as AutomationTrigger;
  } catch (error) {
    handleFrappeError(error, 'Error updating trigger');
    throw error;
  }
}

/**
 * Delete an Automation Trigger.
 */
export async function deleteTrigger(trigger: string): Promise<DeleteTriggerResponse> {
  try {
    const result = await call.post('huf.ai.automation_api.delete_trigger', { trigger });
    return (result?.message ?? result) as DeleteTriggerResponse;
  } catch (error) {
    handleFrappeError(error, 'Error deleting trigger');
    return { success: false };
  }
}

/**
 * List Automations that have at least one enabled Schedule-type
 * Automation Trigger.
 */
export async function listScheduledAutomations(): Promise<ScheduledAutomationSummary[]> {
  try {
    const result = await call.get('huf.ai.automation_api.list_scheduled_automations');
    return (result?.message ?? result) as ScheduledAutomationSummary[];
  } catch (error) {
    handleFrappeError(error, 'Error fetching scheduled automations');
    return [];
  }
}
