import React from 'react';

/**
 * Configuration for trigger type fields
 * This makes it easy to add new trigger types and their fields
 */
export type TriggerFieldConfig = {
  field: string;
  type: 'select' | 'input' | 'textarea' | 'custom';
  label: string;
  placeholder?: string;
  options?: string[];
  description?: string;
  required?: boolean;
  render?: (control: any, field: any, formState: any, agentId?: string) => React.ReactNode;
};

export type TriggerTypeConfig = {
  [key: string]: TriggerFieldConfig[];
};

export const triggerFieldsConfig: TriggerTypeConfig = {
  'Schedule': [
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
      type: 'input',
      label: 'Count',
      placeholder: 'Enter count',
      description: 'Run every n intervals',
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
      label: 'Doc Event',
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
        'after_delete'
      ],
      required: true,
    },
    {
      field: 'condition',
      type: 'textarea',
      label: 'Condition (Python)',
      placeholder: "Use 'doc' to reference the document",
      description: 'Optional condition to filter events',
      required: false,
    },
  ],
  'Webhook': [
    {
      field: 'webhook_slug',
      type: 'input',
      label: 'Webhook Slug',
      placeholder: 'e.g. inbound-leads',
      description: 'Identifier for this webhook trigger (stored on the document).',
      required: true,
    },
    {
      field: 'webhook_key',
      type: 'input',
      label: 'Webhook Key',
      placeholder: 'Secret key',
      description: 'Secret credential for this webhook (stored on the document).',
      required: true,
    },
  ],
  'App Event': [
    {
      field: 'app_name',
      type: 'input',
      label: 'App Name',
      placeholder: 'e.g., Slack',
      required: true,
    },
    {
      field: 'event_name',
      type: 'input',
      label: 'Event Name',
      placeholder: 'e.g., message.posted',
      required: true,
    },
  ],
  'Manual': [
    {
      field: 'manual_info',
      type: 'custom',
      label: '',
      render: () => (
        <div className="rounded-lg border p-4 text-sm text-muted-foreground">
          Manual trigger can be run from workflows or flows. No configuration required.
        </div>
      ),
    },
  ],
};
