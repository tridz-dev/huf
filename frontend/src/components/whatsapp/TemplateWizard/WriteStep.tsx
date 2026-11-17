import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import type { TemplateWizardDraft, WizardButton, WizardButtonType, WizardHeader } from '../template/draft';
import { WIZARD_LIMITS } from '../template/rules';
import type { VariableType } from '../template/variables';
import { BodySection } from './BodySection';
import { ButtonsSection } from './ButtonsSection';
import { ttlLabel } from './draftActions';
import { controlA11y } from './controlA11y';
import { Field, Section, type FieldApi } from './fields';
import { HeaderSection } from './HeaderSection';
import { SamplesPanel } from './SamplesPanel';
import { SetupSection } from './SetupSection';
import { CardsSection, type CardActions } from './CardsSection';

const TTL_CHOICES = [30, 60, 300, 900, 1800, 3600, 7200, 21600, 43200];
const DEFAULT_TTL = 3600;

interface Props {
  draft: TemplateWizardDraft;
  field: FieldApi;
  lockIdentity: boolean;
  editsLeft?: number | null;
  onChange: (patch: Partial<TemplateWizardDraft>) => void;
  onVariableType: (to: VariableType) => void;
  onHeader: (patch: Partial<WizardHeader>) => void;
  onSample: (key: string, value: string) => void;
  onAddButton: (type: WizardButtonType) => void;
  onMoveButton: (index: number, by: -1 | 1) => void;
  onRemoveButton: (index: number) => void;
  onButton: (index: number, patch: Partial<WizardButton>) => void;
  cardActions: CardActions;
}

export function WriteStep(p: Props) {
  const { draft, field } = p;
  const footerError = field.error('footer');
  const ttlError = field.error('ttl');
  const ttl = draft.ttl;
  const choices = ttl !== null && !TTL_CHOICES.includes(ttl) ? [...TTL_CHOICES, ttl].sort((a, b) => a - b) : TTL_CHOICES;

  if (draft.category === 'AUTHENTICATION') {
    const expiryError = field.error('codeExpiryMinutes');
    const buttonError = field.error('otpButtonText');
    return (
      <>
        <SetupSection draft={draft} field={field} locked={p.lockIdentity} onChange={p.onChange} onVariableType={p.onVariableType} />
        <Section title="One-time password" description="WhatsApp fixes the wording of these messages. You can only choose the options below.">
          <div className="flex items-center gap-3">
            <Switch
              id="tpl-otp-security"
              checked={draft.securityRecommendation}
              onCheckedChange={(on) => p.onChange({ securityRecommendation: on })}
            />
            <Label htmlFor="tpl-otp-security">Add security recommendation (do not share this code)</Label>
          </div>
          <div className="flex items-center gap-3">
            <Switch
              id="tpl-otp-expiry-on"
              checked={draft.codeExpiryMinutes !== null}
              onCheckedChange={(on) => p.onChange({ codeExpiryMinutes: on ? 10 : null })}
            />
            <Label htmlFor="tpl-otp-expiry-on">Show code expiry in minutes</Label>
            {draft.codeExpiryMinutes !== null && (
              <Input
                aria-label="Code expiry in minutes"
                type="number"
                min={WIZARD_LIMITS.otpExpiryMin}
                max={WIZARD_LIMITS.otpExpiryMax}
                className="w-24"
                value={draft.codeExpiryMinutes}
                onChange={(e) => p.onChange({ codeExpiryMinutes: Number(e.target.value) })}
              />
            )}
          </div>
          {expiryError && <p role="alert" className="text-[11px] text-destructive">{expiryError}</p>}
          <Field id="tpl-otp-button" label="Copy code button label" error={buttonError} counter={{ length: draft.otpButtonText.length, max: WIZARD_LIMITS.buttonText }}>
            <Input
              {...controlA11y('tpl-otp-button', buttonError)}
              value={draft.otpButtonText}
              onChange={(e) => p.onChange({ otpButtonText: e.target.value })}
              onBlur={() => field.touch('otpButtonText')}
            />
          </Field>
        </Section>
      </>
    );
  }

  if (draft.carousel) {
    return (
      <>
        <SetupSection draft={draft} field={field} locked={p.lockIdentity} onChange={p.onChange} onVariableType={p.onVariableType} />
        <BodySection draft={draft} field={field} onBody={(body) => p.onChange({ body })} />
        <SamplesPanel draft={draft} field={field} onSample={p.onSample} />
        <CardsSection draft={draft} field={field} {...p.cardActions} />
      </>
    );
  }

  return (
    <>
      {p.editsLeft != null && (
        <p className="rounded-md border border-line bg-paper-deep px-3 py-2 text-xs text-steel">
          WhatsApp limits how often an approved template can be edited. Edits left: {p.editsLeft}.
        </p>
      )}
      <SetupSection draft={draft} field={field} locked={p.lockIdentity} onChange={p.onChange} onVariableType={p.onVariableType} />
      <HeaderSection draft={draft} field={field} onHeader={p.onHeader} />
      <BodySection draft={draft} field={field} onBody={(body) => p.onChange({ body })} />
      <SamplesPanel draft={draft} field={field} onSample={p.onSample} />
      <Section title="Footer" description="Optional. A short line under the message.">
        <Field id="tpl-footer" label="Footer text" error={footerError} counter={{ length: draft.footer.length, max: WIZARD_LIMITS.footer }}>
          <Input
            {...controlA11y('tpl-footer', footerError)}
            value={draft.footer}
            onChange={(e) => p.onChange({ footer: e.target.value })}
            onBlur={() => field.touch('footer')}
          />
        </Field>
      </Section>
      <ButtonsSection draft={draft} field={field} onAdd={p.onAddButton} onMove={p.onMoveButton} onRemove={p.onRemoveButton} onChange={p.onButton} />
      {draft.category === 'UTILITY' && (
        <Section title="Message expiry">
          <div className="flex items-center gap-3">
            <Switch
              id="tpl-ttl-on"
              checked={ttl !== null}
              onCheckedChange={(on) => p.onChange({ ttl: on ? DEFAULT_TTL : null })}
            />
            <Label htmlFor="tpl-ttl-on">Message expires after</Label>
            {ttl !== null && (
              <Select value={String(ttl)} onValueChange={(v) => p.onChange({ ttl: Number(v) })}>
                <SelectTrigger aria-label="Expiry time" className="w-36"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {choices.map((s) => <SelectItem key={s} value={String(s)}>{ttlLabel(s)}</SelectItem>)}
                </SelectContent>
              </Select>
            )}
          </div>
          <p id="tpl-ttl-note" role={ttlError ? 'alert' : undefined} className={ttlError ? 'text-[11px] text-destructive' : 'text-[11px] text-steel'}>
            {ttlError ?? 'If WhatsApp cannot deliver the message in time, it is dropped instead of arriving late.'}
          </p>
        </Section>
      )}
    </>
  );
}
