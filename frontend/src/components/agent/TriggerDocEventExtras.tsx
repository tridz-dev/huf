import { useEffect, useMemo, useState } from 'react';
import { Control, useFieldArray, useWatch } from 'react-hook-form';
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Plus, Trash2 } from 'lucide-react';
import { getDocTypeMeta } from '@/services/agentApi';

interface TriggerDocEventExtrasProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  control: Control<any>;
}

const STANDARD_FIELDS = ['name', 'owner', 'creation', 'modified', 'docstatus'];

export function TriggerDocEventExtras({ control }: TriggerDocEventExtrasProps) {
  const referenceDoctype = useWatch({ control, name: 'reference_doctype' });
  const fileAttachments = useWatch({ control, name: 'file_attachments' }) || [];
  const [promptFieldOptions, setPromptFieldOptions] = useState<string[]>([]);
  const [childTableOptions, setChildTableOptions] = useState<string[]>([]);
  const { fields, append, remove } = useFieldArray({
    control,
    name: 'file_attachments',
  });

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
          .filter((df: { fieldtype?: string }) => !['Section Break', 'Column Break', 'Tab Break', 'Table'].includes(df.fieldtype || ''))
          .map((df: { fieldname: string }) => df.fieldname);
        setPromptFieldOptions([...STANDARD_FIELDS, ...docFields]);
        setChildTableOptions(
          (meta?.fields || [])
            .filter((df: { fieldtype?: string }) => df.fieldtype === 'Table')
            .map((df: { fieldname: string }) => df.fieldname),
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
    [promptFieldOptions],
  );

  return (
    <div className="space-y-4">
      <FormField
        control={control}
        name="prompt_field"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Prompt Field</FormLabel>
            <Select
              onValueChange={field.onChange}
              value={field.value || ''}
              disabled={!referenceDoctype}
            >
              <FormControl>
                <SelectTrigger>
                  <SelectValue placeholder={referenceDoctype ? 'Select field' : 'Select DocType first'} />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                {promptOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FormDescription>
              Optional field on the reference DocType whose value becomes the user prompt.
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />

      <div className="space-y-3 rounded-lg border p-4">
        <div className="flex items-center justify-between gap-2">
          <div>
            <FormLabel>File Attachments</FormLabel>
            <FormDescription>
              Fetch files from DocFields or child table fields for OCR processing at trigger time.
            </FormDescription>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              append({
                source_type: 'DocField',
                field_name: '',
              })
            }
          >
            <Plus className="mr-1 h-4 w-4" />
            Add
          </Button>
        </div>

        {fields.length === 0 && (
          <p className="text-sm text-muted-foreground">No file attachment mappings configured.</p>
        )}

        {fields.map((row, index) => (
          <div key={row.id} className="grid gap-3 rounded-md border p-3 sm:grid-cols-2">
            <FormField
              control={control}
              name={`file_attachments.${index}.source_type`}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Source Type</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="DocField">DocField</SelectItem>
                      <SelectItem value="Child Table Field">Child Table Field</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={control}
              name={`file_attachments.${index}.field_name`}
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Attach Field Name</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g. attachment" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {fileAttachments[index]?.source_type === 'Child Table Field' && (
              <FormField
                control={control}
                name={`file_attachments.${index}.child_table`}
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Child Table</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value || ''}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select child table" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {childTableOptions.map((table) => (
                          <SelectItem key={table} value={table}>
                            {table}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            <div className="sm:col-span-2 flex justify-end">
              <Button type="button" variant="ghost" size="sm" onClick={() => remove(index)}>
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
