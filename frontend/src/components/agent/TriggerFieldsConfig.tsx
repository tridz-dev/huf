import React from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Copy } from 'lucide-react';
import { toast } from 'sonner';

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
      field: 'webhook_url',
      type: 'custom',
      label: 'Webhook URL',
      render: (_control, _field, _formState, agentId?: string) => {
        return (
          <div className="space-y-2">
            <Label>Webhook URL</Label>
            <div className="flex gap-2">
              <Input
                value={`https://api.hufai.com/agent/${agentId}/webhook/${Date.now()}`}
                readOnly
                className="flex-1 font-mono text-sm"
              />
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={() => {
                  const url = `https://api.hufai.com/agent/${agentId}/webhook/${Date.now()}`;
                  navigator.clipboard.writeText(url);
                  toast.success('Webhook URL copied to clipboard');
                }}
              >
                <Copy className="w-4 h-4" />
              </Button>
            </div>
            <p className="text-sm text-muted-foreground">Auto-generated webhook endpoint</p>
          </div>
        );
      },
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

