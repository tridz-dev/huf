import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';

export interface DirectValues {
  title: string;
  text: string;
  url: string;
}

export const EMPTY_DIRECT: DirectValues = { title: '', text: '', url: '' };

interface PanelProps {
  values: DirectValues;
  onChange: (next: DirectValues) => void;
  disabled?: boolean;
}

export function TextPanel({ values, onChange, disabled }: PanelProps) {
  return (
    <div className="space-y-3">
      <Field label="Title (optional)">
        <Input
          value={values.title}
          onChange={(e) => onChange({ ...values, title: e.target.value })}
          placeholder="Refund policy"
          disabled={disabled}
          data-testid="direct-title"
        />
      </Field>
      <Field label="Content">
        <Textarea
          value={values.text}
          onChange={(e) => onChange({ ...values, text: e.target.value })}
          placeholder="Paste or type the text your agents should know"
          rows={8}
          disabled={disabled}
          data-testid="direct-text"
        />
      </Field>
    </div>
  );
}

export function WebPagePanel({ values, onChange, disabled }: PanelProps) {
  return (
    <Field label="Web address">
      <Input
        value={values.url}
        onChange={(e) => onChange({ ...values, url: e.target.value })}
        placeholder="https://example.com/help"
        disabled={disabled}
        data-testid="direct-url"
      />
    </Field>
  );
}
