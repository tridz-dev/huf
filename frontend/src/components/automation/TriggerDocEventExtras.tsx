import { useEffect, useMemo, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { getDocTypeMeta } from '@/services/agentApi';
import type { AutomationTriggerAttachment } from '@/types/automation.types';

const STANDARD_FIELDS = ['name', 'owner', 'creation', 'modified', 'docstatus'];

export interface TriggerDocEventExtrasProps {
  referenceDoctype?: string;
  promptField?: string;
  promptFieldMode?: string;
  fileAttachments: AutomationTriggerAttachment[];
  onPromptFieldChange: (value: string) => void;
  onPromptFieldModeChange: (value: string) => void;
  onFileAttachmentsChange: (rows: AutomationTriggerAttachment[]) => void;
  disabled?: boolean;
}

/**
 * Doc Event's extra fields: which document field carries the prompt
 * (plus Supplement/Override mode), and which fields/child tables to pull
 * file attachments from. Ports the legacy `TriggerDocEventExtras.tsx`'s
 * field-discovery logic (fetch the chosen DocType's meta, offer its fields
 * as prompt-field options) onto plain controlled props instead of
 * `react-hook-form`.
 */
export function TriggerDocEventExtras({
  referenceDoctype,
  promptField,
  promptFieldMode,
  fileAttachments,
  onPromptFieldChange,
  onPromptFieldModeChange,
  onFileAttachmentsChange,
  disabled,
}: TriggerDocEventExtrasProps) {
  const [promptFieldOptions, setPromptFieldOptions] = useState<string[]>([]);
  const [childTableOptions, setChildTableOptions] = useState<string[]>([]);

  useEffect(() => {
    if (!referenceDoctype) {
      setPromptFieldOptions([]);
      setChildTableOptions([]);
      return;
    }

    let cancelled = false;

    getDocTypeMeta(referenceDoctype)
      .then((meta) => {
        if (cancelled) return;
        const docFields = (meta?.fields || [])
          .filter(
            (df: { fieldtype?: string }) =>
              !['Section Break', 'Column Break', 'Tab Break', 'Table'].includes(df.fieldtype || '')
          )
          .map((df: { fieldname: string }) => df.fieldname);
        setPromptFieldOptions([...STANDARD_FIELDS, ...docFields]);
        setChildTableOptions(
          (meta?.fields || [])
            .filter((df: { fieldtype?: string }) => df.fieldtype === 'Table')
            .map((df: { fieldname: string }) => df.fieldname)
        );
      })
      .catch(() => {
        if (!cancelled) {
          setPromptFieldOptions([]);
          setChildTableOptions([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [referenceDoctype]);

  const promptOptions = useMemo(
    () => promptFieldOptions.map((fieldname) => ({ value: fieldname, label: fieldname })),
    [promptFieldOptions]
  );

  const updateAttachmentRow = (index: number, patch: Partial<AutomationTriggerAttachment>) => {
    const next = fileAttachments.map((row, i) => (i === index ? { ...row, ...patch } : row));
    onFileAttachmentsChange(next);
  };

  const addAttachmentRow = () => {
    onFileAttachmentsChange([
      ...fileAttachments,
      { source_type: 'DocField', field_name: '' } as AutomationTriggerAttachment,
    ]);
  };

  const removeAttachmentRow = (index: number) => {
    onFileAttachmentsChange(fileAttachments.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label>Prompt field</Label>
        <Select
          onValueChange={onPromptFieldChange}
          value={promptField || ''}
          disabled={!referenceDoctype || disabled}
        >
          <SelectTrigger>
            <SelectValue placeholder={referenceDoctype ? 'Select field' : 'Select DocType first'} />
          </SelectTrigger>
          <SelectContent>
            {promptOptions.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-steel-soft">
          The field on the Reference DocType that carries the user&apos;s instructions.
        </p>
      </div>

      <div className="space-y-1.5">
        <Label>Prompt field mode</Label>
        <Select
          onValueChange={onPromptFieldModeChange}
          value={promptFieldMode || ''}
          disabled={!promptField || disabled}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select mode" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="Supplement">Supplement</SelectItem>
            <SelectItem value="Override">Override</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-xs text-steel-soft">
          Supplement adds the field&apos;s value to the automation&apos;s instruction; Override replaces it.
        </p>
      </div>

      <div className="space-y-3 rounded-lg border p-4">
        <div className="flex items-center justify-between gap-2">
          <div>
            <Label>File attachments</Label>
            <p className="text-xs text-steel-soft">Fetch files from specific DocFields or Child Tables.</p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={addAttachmentRow} disabled={disabled}>
            <Plus className="mr-1 h-4 w-4" />
            Add
          </Button>
        </div>

        {fileAttachments.length === 0 && (
          <p className="text-sm font-body text-steel-soft">No file attachment mappings configured.</p>
        )}

        {fileAttachments.map((row, index) => (
          <div key={row.name ?? index} className="grid gap-3 rounded-md border p-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Source type</Label>
              <Select
                onValueChange={(value) => updateAttachmentRow(index, { source_type: value })}
                value={(row.source_type as string) || 'DocField'}
                disabled={disabled}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="DocField">DocField</SelectItem>
                  <SelectItem value="Child Table Field">Child Table Field</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Attach field name</Label>
              <Input
                placeholder="e.g. attachment"
                value={(row.field_name as string) || ''}
                disabled={disabled}
                onChange={(event) => updateAttachmentRow(index, { field_name: event.target.value })}
              />
            </div>

            {row.source_type === 'Child Table Field' && (
              <div className="sm:col-span-2 space-y-1.5">
                <Label>Child table</Label>
                <Select
                  onValueChange={(value) => updateAttachmentRow(index, { child_table: value })}
                  value={(row.child_table as string) || ''}
                  disabled={disabled}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select child table" />
                  </SelectTrigger>
                  <SelectContent>
                    {childTableOptions.map((table) => (
                      <SelectItem key={table} value={table}>
                        {table}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="sm:col-span-2 flex justify-end">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => removeAttachmentRow(index)}
                disabled={disabled}
              >
                <Trash2 className="mr-1 h-4 w-4" />
                Remove
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
