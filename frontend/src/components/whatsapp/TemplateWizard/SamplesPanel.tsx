import { Input } from '@/components/ui/input';
import type { TemplateWizardDraft } from '../template/draft';
import { sampleVariables } from './draftActions';
import { controlA11y } from './controlA11y';
import { Field, Section, type FieldApi } from './fields';

interface Props {
  draft: TemplateWizardDraft;
  field: FieldApi;
  onSample: (key: string, value: string) => void;
}

export function SamplesPanel({ draft, field, onSample }: Props) {
  const vars = sampleVariables(draft);
  if (vars.length === 0) return null;
  return (
    <Section title="Variable samples" description="Samples are only used for review. They aren't sent to your customers. Don't include customer information.">
      {vars.map(({ key, token, where }) => {
        const path = `samples.${key}`;
        const id = `tpl-sample-${key.replace(/\W/g, '-')}`;
        const raw = field.error(path);
        const error = raw && !(draft.samples[key] ?? '').trim() ? 'Add a sample' : raw;
        return (
          <Field key={key} id={id} label={<>{where} <span className="font-mono text-steel">{`{{${token}}}`}</span></>} error={error}>
            <Input
              {...controlA11y(id, error)}
              value={draft.samples[key] ?? ''}
              onChange={(e) => onSample(key, e.target.value)}
              onBlur={() => field.touch(path)}
            />
          </Field>
        );
      })}
    </Section>
  );
}
