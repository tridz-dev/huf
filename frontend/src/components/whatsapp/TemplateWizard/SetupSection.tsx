import { useMemo, useState } from 'react';
import { Combobox } from '@/components/ui/combobox';
import { Input } from '@/components/ui/input';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Button } from '@/components/ui/button';
import type { TemplateWizardDraft } from '../template/draft';
import { TEMPLATE_LOCALES } from '../template/locales';
import { slugifyName, WIZARD_LIMITS } from '../template/rules';
import type { VariableType } from '../template/variables';
import { controlA11y } from './controlA11y';
import { Field, Section, type FieldApi } from './fields';

interface Props {
  draft: TemplateWizardDraft;
  field: FieldApi;
  locked: boolean;
  onChange: (patch: Partial<TemplateWizardDraft>) => void;
  onVariableType: (to: VariableType) => void;
}

export function SetupSection({ draft, field, locked, onChange, onVariableType }: Props) {
  const [search, setSearch] = useState('');
  const nameError = field.error('name');
  const languageError = field.error('language');
  const slug = slugifyName(draft.name);
  const options = useMemo(() => {
    const q = search.trim().toLowerCase();
    return TEMPLATE_LOCALES.filter((l) => !q || l.label.toLowerCase().includes(q) || l.code.toLowerCase().includes(q)).map((l) => ({
      value: l.code,
      label: l.label,
      subtitle: l.code,
    }));
  }, [search]);

  return (
    <Section title="Name and language">
      <Field
        id="tpl-name"
        label="Template name"
        error={nameError}
        hint={locked ? 'The name cannot be changed after the template is created.' : 'Lowercase letters, digits and underscores, for example order_update.'}
        counter={{ length: draft.name.length, max: WIZARD_LIMITS.name }}
        labelExtra={
          !locked && slug && slug !== draft.name ? (
            <Button type="button" variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => onChange({ name: slug })}>
              Use {slug}
            </Button>
          ) : null
        }
      >
        <Input
          {...controlA11y('tpl-name', nameError)}
          value={draft.name}
          disabled={locked}
          className="font-mono"
          onChange={(e) => onChange({ name: e.target.value })}
          onBlur={() => field.touch('name')}
        />
      </Field>

      <Field id="tpl-language" label="Language" error={languageError} hint={locked ? 'The language cannot be changed after the template is created.' : undefined}>
        <Combobox
          id="tpl-language"
          options={options}
          value={draft.language}
          disabled={locked}
          shouldFilter={false}
          onSearchChange={setSearch}
          onValueChange={(code) => {
            if (code) onChange({ language: code });
            field.touch('language');
          }}
          searchPlaceholder="Search languages"
          emptyText="No language found."
        />
      </Field>

      <div className="space-y-1.5">
        <span id="tpl-vartype-label" className="text-sm font-medium text-ink">Variable type</span>
        <ToggleGroup
          type="single"
          variant="outline"
          aria-labelledby="tpl-vartype-label"
          value={draft.variableType}
          className="justify-start"
          onValueChange={(v) => v && onVariableType(v as VariableType)}
        >
          <ToggleGroupItem value="number" aria-label="Number variables">Number</ToggleGroupItem>
          <ToggleGroupItem value="name" aria-label="Name variables">Name</ToggleGroupItem>
        </ToggleGroup>
        <p className="text-[11px] text-steel">
          {draft.variableType === 'number' ? 'Variables look like {{1}}, {{2}}.' : 'Variables look like {{first_name}}.'} Switching renames the ones you have already added.
        </p>
      </div>
    </Section>
  );
}
