import type { AutomationTriggerType } from '@/types/automation.types';

/**
 * Config-driven field metadata for the automation-scoped trigger editor.
 *
 * Mirrors the shape of the legacy Agent Trigger's
 * `components/agent/TriggerFieldsConfig.tsx`, but this copy is intentionally
 * NOT shared with it: the legacy file is scoped to the old `Agent Trigger`
 * doctype's field set (a superset that includes cron/timezone/misfire-policy
 * fields this pass deliberately does not surface -- see this track's
 * CONTEXT.md non-goals). Keep the two in sync by hand if a shared field's
 * label/options change; do not re-merge them.
 */
export type TriggerFieldType = 'select' | 'input' | 'textarea' | 'number';

export interface TriggerFieldConfig {
  field: string;
  type: TriggerFieldType;
  label: string;
  placeholder?: string;
  options?: string[];
  description?: string;
  required?: boolean;
}

export type TriggerTypeFieldConfig = Record<string, TriggerFieldConfig[]>;

/**
 * Declarative fields for the trigger types (or the parts of a trigger type)
 * that don't need bespoke UI. Doc Event's `prompt_field` /
 * `prompt_field_mode` / `file_attachments` and all of Webhook are rendered
 * by dedicated components instead (they need data fetched from the chosen
 * DocType, or server-generated read-only values) -- see
 * `TriggerDocEventExtras.tsx` and `TriggerEditor.tsx`.
 */
export const triggerFieldsConfig: TriggerTypeFieldConfig = {
  Schedule: [
    {
      field: 'scheduled_interval',
      type: 'select',
      label: 'Interval',
      placeholder: 'Select interval',
      options: ['Hourly', 'Daily', 'Weekly', 'Monthly', 'Yearly'],
      required: true,
    },
    {
      field: 'interval_count',
      type: 'number',
      label: 'Every',
      placeholder: '1',
      description: 'Run every N intervals (e.g. every 2 Weeks).',
      required: true,
    },
  ],
  'Doc Event': [
    {
      field: 'reference_doctype',
      type: 'select',
      label: 'DocType',
      placeholder: 'Select DocType',
      required: true,
    },
    {
      field: 'doc_event',
      type: 'select',
      label: 'Doc event',
      placeholder: 'Select event',
      options: [
        'before_insert',
        'after_insert',
        'validate',
        'before_save',
        'after_save',
        'before_submit',
        'on_submit',
        'on_update',
        'after_submit',
        'on_cancel',
        'before_rename',
        'after_rename',
        'on_trash',
        'after_delete',
      ],
      required: true,
    },
    {
      field: 'condition',
      type: 'textarea',
      label: 'Condition (Python, optional)',
      placeholder: "Use 'doc' to reference the document, e.g. doc.status == 'Approved'",
      description: 'Only run when this expression evaluates truthy. Leave blank to always run.',
      required: false,
    },
  ],
  'App Event': [
    {
      field: 'app_name',
      type: 'input',
      label: 'App name',
      placeholder: 'e.g. Slack',
      required: true,
    },
    {
      field: 'event_name',
      type: 'input',
      label: 'Event name',
      placeholder: 'e.g. message.posted',
      required: true,
    },
  ],
};

/** One-line help copy per trigger type, shown under the type selector. */
export const triggerTypeHelpText: Record<AutomationTriggerType, string> = {
  Schedule: 'Runs automatically on a repeating schedule.',
  'Doc Event': 'Runs when a document is created, saved, or changes state.',
  Webhook: 'Runs when an external service calls a generated URL.',
  'App Event': 'Runs when another part of the system reports a named event.',
  Manual: 'This automation only runs when triggered manually (Run now, from chat, or by another automation).',
};

export const AUTOMATION_TRIGGER_TYPES: AutomationTriggerType[] = [
  'Schedule',
  'Doc Event',
  'Webhook',
  'App Event',
  'Manual',
];
