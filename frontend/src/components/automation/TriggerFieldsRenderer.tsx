import { Label } from '@/components/ui/label';
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
import { triggerFieldsConfig, type TriggerFieldConfig } from './TriggerFieldsConfig';

export interface TriggerFieldsRendererProps {
  triggerType: string;
  values: Record<string, unknown>;
  onFieldChange: (field: string, value: string | number | undefined) => void;
  docTypes: Array<{ name: string }>;
  loadingDocTypes: boolean;
  disabled?: boolean;
}

/**
 * Renders the declarative fields for a trigger type (see
 * `triggerFieldsConfig`). Plain controlled inputs -- this editor is not tied
 * to a single `react-hook-form` instance because an Automation can hold 0-N
 * triggers on one page (`AutomationFormPage.tsx`), each with its own
 * independent field state living in the parent's trigger-rows array.
 */
export function TriggerFieldsRenderer({
  triggerType,
  values,
  onFieldChange,
  docTypes,
  loadingDocTypes,
  disabled,
}: TriggerFieldsRendererProps) {
  const fields = triggerFieldsConfig[triggerType];
  if (!fields) return null;

  return (
    <div className="space-y-4">
      {fields.map((fieldConfig) => (
        <TriggerField
          key={fieldConfig.field}
          config={fieldConfig}
          value={values[fieldConfig.field]}
          onChange={(value) => onFieldChange(fieldConfig.field, value)}
          docTypes={docTypes}
          loadingDocTypes={loadingDocTypes}
          disabled={disabled}
        />
      ))}
    </div>
  );
}

function TriggerField({
  config,
  value,
  onChange,
  docTypes,
  loadingDocTypes,
  disabled,
}: {
  config: TriggerFieldConfig;
  value: unknown;
  onChange: (value: string | number | undefined) => void;
  docTypes: Array<{ name: string }>;
  loadingDocTypes: boolean;
  disabled?: boolean;
}) {
  const stringValue = typeof value === 'string' || typeof value === 'number' ? String(value) : '';

  if (config.type === 'select' && config.field === 'reference_doctype') {
    const options = docTypes.map((dt) => ({ value: dt.name, label: dt.name }));
    return (
      <div className="space-y-1.5">
        <Label>{config.label}</Label>
        <Combobox
          options={options}
          value={stringValue}
          onValueChange={onChange}
          placeholder={loadingDocTypes ? 'Loading...' : config.placeholder || `Select ${config.label}`}
          disabled={loadingDocTypes || disabled}
          searchPlaceholder="Search DocType..."
          emptyText="No DocType found."
        />
        {config.description && <p className="text-xs text-steel-soft">{config.description}</p>}
      </div>
    );
  }

  if (config.type === 'select') {
    const options = config.options ?? [];
    return (
      <div className="space-y-1.5">
        <Label>{config.label}</Label>
        <Select onValueChange={onChange} value={stringValue} disabled={disabled}>
          <SelectTrigger>
            <SelectValue placeholder={config.placeholder || `Select ${config.label}`} />
          </SelectTrigger>
          <SelectContent>
            {options.map((option) => (
              <SelectItem key={option} value={option}>
                {option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {config.description && <p className="text-xs text-steel-soft">{config.description}</p>}
      </div>
    );
  }

  if (config.type === 'number') {
    return (
      <div className="space-y-1.5">
        <Label>{config.label}</Label>
        <Input
          type="number"
          min={1}
          inputMode="numeric"
          placeholder={config.placeholder}
          value={stringValue}
          disabled={disabled}
          onChange={(event) => {
            const raw = event.target.value;
            onChange(raw === '' ? undefined : Number(raw));
          }}
        />
        {config.description && <p className="text-xs text-steel-soft">{config.description}</p>}
      </div>
    );
  }

  if (config.type === 'textarea') {
    return (
      <div className="space-y-1.5">
        <Label>{config.label}</Label>
        <Textarea
          className="font-mono resize-y min-h-[100px]"
          placeholder={config.placeholder}
          value={stringValue}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        />
        {config.description && <p className="text-xs text-steel-soft">{config.description}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <Label>{config.label}</Label>
      <Input
        type="text"
        placeholder={config.placeholder}
        value={stringValue}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
      {config.description && <p className="text-xs text-steel-soft">{config.description}</p>}
    </div>
  );
}
