import { useState } from 'react';
import { ChevronDown, ChevronUp, Copy, ExternalLink, Phone, Plus, Reply, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import type { TemplateWizardDraft, WizardButton, WizardButtonType } from '../template/draft';
import { WIZARD_LIMITS } from '../template/rules';
import { buttonBlocker } from './draftActions';
import { controlA11y } from './controlA11y';
import { Field, Section, type FieldApi } from './fields';
import { expandUrlExample } from './urlExample';

const KINDS: { type: WizardButtonType; label: string; Icon: typeof Reply }[] = [
  { type: 'QUICK_REPLY', label: 'Custom reply', Icon: Reply },
  { type: 'URL', label: 'Visit website', Icon: ExternalLink },
  { type: 'PHONE_NUMBER', label: 'Call phone number', Icon: Phone },
  { type: 'COPY_CODE', label: 'Copy offer code', Icon: Copy },
];

interface Props {
  draft: TemplateWizardDraft;
  field: FieldApi;
  onAdd: (type: WizardButtonType) => void;
  onMove: (index: number, by: -1 | 1) => void;
  onRemove: (index: number) => void;
  onChange: (index: number, patch: Partial<WizardButton>) => void;
}

function ButtonFields({ button, index, field, onChange }: { button: WizardButton; index: number; field: FieldApi; onChange: Props['onChange'] }) {
  const [expandedNote, setExpandedNote] = useState('');
  const text = (name: keyof WizardButton, label: string, placeholder: string, hint?: string, max?: number) => {
    const path = `buttons.${index}.${name}`;
    const id = `tpl-btn-${index}-${name}`;
    const error = field.error(path);
    const value = String(button[name]);
    return (
      <Field id={id} label={label} error={error} hint={name === 'urlExample' && expandedNote ? expandedNote : hint} counter={max ? { length: value.length, max } : undefined}>
        <Input
          {...controlA11y(id, error)}
          value={value}
          placeholder={placeholder}
          onChange={(e) => {
            if (name === 'urlExample') setExpandedNote('');
            onChange(index, { [name]: e.target.value });
          }}
          onBlur={() => {
            if (name === 'urlExample') {
              const full = expandUrlExample(button.url, value);
              if (full !== value) {
                onChange(index, { urlExample: full });
                setExpandedNote(`Expanded to the full link: ${full}`);
              }
            }
            field.touch(path);
          }}
        />
      </Field>
    );
  };
  const dynamicUrl = button.type === 'URL' && button.url.includes('{{');
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {text('text', 'Button text', 'Shop now', undefined, WIZARD_LIMITS.buttonText)}
      {button.type === 'URL' && text('url', 'Website link', 'https://example.com/orders/{{1}}', 'End the link with {{1}} to add a value per message.')}
      {dynamicUrl && text('urlExample', 'Example link', 'https://example.com/orders/123')}
      {button.type === 'PHONE_NUMBER' && text('phoneNumber', 'Phone number', '+15551234567', 'International format.')}
      {button.type === 'COPY_CODE' && text('codeExample', 'Example code', 'SAVE20', 'Letters and digits only.')}
    </div>
  );
}

export function ButtonsSection({ draft, field, onAdd, onMove, onRemove, onChange }: Props) {
  const groupError = field.error('buttons');
  const n = draft.buttons.length;
  return (
    <Section title="Buttons" description="Optional. Up to 10 buttons. Replies stay together, up to 2 website buttons, 1 phone button and 1 offer code.">
      {draft.buttons.map((b, i) => {
        const meta = KINDS.find((k) => k.type === b.type) ?? KINDS[0];
        return (
          <div key={b.id} className="space-y-3 rounded-md border border-line p-3" role="group" aria-label={`Button ${i + 1}: ${meta.label}`}>
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-xs font-medium text-ink">
                <meta.Icon className="h-3.5 w-3.5" aria-hidden /> {meta.label}
              </span>
              <span className="flex items-center">
                <Button type="button" variant="ghost" size="icon" className="h-7 w-7" disabled={i === 0} aria-label={`Move button ${i + 1} up`} onClick={() => onMove(i, -1)}>
                  <ChevronUp className="h-4 w-4" aria-hidden />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="h-7 w-7" disabled={i === n - 1} aria-label={`Move button ${i + 1} down`} onClick={() => onMove(i, 1)}>
                  <ChevronDown className="h-4 w-4" aria-hidden />
                </Button>
                <Button type="button" variant="ghost" size="icon" className="h-7 w-7" aria-label={`Remove button ${i + 1}`} onClick={() => onRemove(i)}>
                  <Trash2 className="h-4 w-4" aria-hidden />
                </Button>
              </span>
            </div>
            <ButtonFields button={b} index={i} field={field} onChange={onChange} />
          </div>
        );
      })}

      <div className="flex min-h-4 items-center justify-between gap-3">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="outline" size="sm" disabled={n >= WIZARD_LIMITS.buttonsTotal}>
              <Plus className="mr-1.5 h-3.5 w-3.5" aria-hidden /> Add button
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {KINDS.map(({ type, label, Icon }) => {
              const blocker = buttonBlocker(draft, type);
              return (
                <DropdownMenuItem key={type} disabled={!!blocker} onSelect={() => onAdd(type)}>
                  <Icon className="mr-2 h-4 w-4" aria-hidden /> {label}
                  {blocker && <span className="ml-2 text-[11px] text-steel">{blocker}</span>}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>
        <span className="text-[11px] text-steel">{n}/{WIZARD_LIMITS.buttonsTotal}</span>
      </div>
      {groupError && <p role="alert" className="text-[11px] text-destructive">{groupError}</p>}
    </Section>
  );
}
