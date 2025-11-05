import { Control } from 'react-hook-form';
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
import { Combobox } from '@/components/ui/combobox';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { triggerFieldsConfig } from './TriggerFieldsConfig';

interface TriggerFieldsRendererProps {
  triggerType: string;
  control: Control<any>;
  docTypes: Array<{ name: string }>;
  loadingDocTypes: boolean;
  agentId?: string;
}

/**
 * Reusable component to render trigger fields based on configuration
 * This makes it easy to add new trigger types and fields
 */
export function TriggerFieldsRenderer({
  triggerType,
  control,
  docTypes,
  loadingDocTypes,
  agentId,
}: TriggerFieldsRendererProps) {
  const fields = triggerFieldsConfig[triggerType];
  if (!fields) return null;

  return (
    <div className="space-y-4">
      {fields.map((fieldConfig) => {
        // Custom render function
        if (fieldConfig.type === 'custom' && fieldConfig.render) {
          return (
            <div key={fieldConfig.field}>
              {fieldConfig.render(control, null, null, agentId)}
            </div>
          );
        }

        // Regular form fields
        return (
          <FormField
            key={fieldConfig.field}
            control={control}
            name={fieldConfig.field}
            render={({ field }) => {
              if (fieldConfig.type === 'select') {
                // Use Combobox for reference_doctype (searchable)
                if (fieldConfig.field === 'reference_doctype') {
                  const comboboxOptions = docTypes.map((dt) => ({
                    value: dt.name,
                    label: dt.name,
                  }));

                  return (
                    <FormItem>
                      <FormLabel>{fieldConfig.label}</FormLabel>
                      <FormControl>
                        <Combobox
                          options={comboboxOptions}
                          value={field.value}
                          onValueChange={field.onChange}
                          placeholder={
                            loadingDocTypes
                              ? 'Loading...'
                              : fieldConfig.placeholder || `Select ${fieldConfig.label}`
                          }
                          disabled={loadingDocTypes}
                          searchPlaceholder="Search DocType..."
                          emptyText="No DocType found."
                        />
                      </FormControl>
                      {fieldConfig.description && (
                        <FormDescription>{fieldConfig.description}</FormDescription>
                      )}
                      <FormMessage />
                    </FormItem>
                  );
                }

                // Use regular Select for other select fields
                const options = Array.isArray(fieldConfig.options)
                  ? fieldConfig.options
                  : [];

                return (
                  <FormItem>
                    <FormLabel>{fieldConfig.label}</FormLabel>
                    <Select
                      onValueChange={field.onChange}
                      value={field.value}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue
                            placeholder={fieldConfig.placeholder || `Select ${fieldConfig.label}`}
                          />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {options.map((option) => (
                          <SelectItem key={option} value={option}>
                            {option}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {fieldConfig.description && (
                      <FormDescription>{fieldConfig.description}</FormDescription>
                    )}
                    <FormMessage />
                  </FormItem>
                );
              }

              if (fieldConfig.type === 'input') {
                return (
                  <FormItem>
                    <FormLabel>{fieldConfig.label}</FormLabel>
                    <FormControl>
                      <Input
                        type="text"
                        inputMode={fieldConfig.field === 'interval_count' ? 'numeric' : undefined}
                        placeholder={fieldConfig.placeholder}
                        {...field}
                        value={field.value || ''}
                      />
                    </FormControl>
                    {fieldConfig.description && (
                      <FormDescription>{fieldConfig.description}</FormDescription>
                    )}
                    <FormMessage />
                  </FormItem>
                );
              }

              if (fieldConfig.type === 'textarea') {
                return (
                  <FormItem>
                    <FormLabel>{fieldConfig.label}</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder={fieldConfig.placeholder}
                        className="font-mono resize-y min-h-[100px]"
                        {...field}
                      />
                    </FormControl>
                    {fieldConfig.description && (
                      <FormDescription>{fieldConfig.description}</FormDescription>
                    )}
                    <FormMessage />
                  </FormItem>
                );
              }

              return <div key={fieldConfig.field} />;
            }}
          />
        );
      })}
    </div>
  );
}

