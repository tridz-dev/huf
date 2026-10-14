import { useRef, useState } from 'react';
import { toast } from 'sonner';
import { ArrowLeft, Braces, Loader2, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  HEADER_TYPES, TEMPLATE_CATEGORIES, TEMPLATE_LIMITS, bodyVariableEdgeProblem, buildEditPayload, buildTemplatePayload,
  createTemplate, createTemplateDraft, editTemplate, errorText, extractPlaceholders, templateNameProblem,
  validateTemplateForm, type HeaderType, type TemplateButton, type TemplateButtonType, type TemplateCategory,
  type TemplateDetail, type TemplateForm,
} from '@/services/whatsappApi';
import { TemplatePreview } from './TemplatePreview';
import { insertVariable } from './templateModel';

export type EditorMode = 'create' | 'edit';

interface Props {
  mode: EditorMode;
  gateway?: string;
  /** Required in edit mode: the template being edited. */
  detail?: TemplateDetail;
  isAdmin: boolean;
  onCancel: () => void;
  /** Called with the name of the template (or draft) that was saved. */
  onSaved: (result: { kind: 'submitted' | 'edited' | 'draft'; name: string }) => void;
}

const HEADER_LABEL: Record<HeaderType, string> = { TEXT: 'Text', IMAGE: 'Image', DOCUMENT: 'Document' };

function initialForm(detail?: TemplateDetail) {
  if (!detail) {
    return {
      name: '', category: 'UTILITY' as TemplateCategory, language: 'en_US', body: '', samples: [] as string[],
      headerType: '' as HeaderType | '', header: '', headerSample: '', footer: '', buttons: [] as TemplateButton[],
    };
  }
  const { header, body, footer, buttons } = detail.components;
  return {
    name: detail.template_name,
    category: (TEMPLATE_CATEGORIES.includes(detail.category as TemplateCategory) ? detail.category : 'UTILITY') as TemplateCategory,
    language: detail.language_code,
    body: body.text,
    samples: body.sample_values,
    headerType: (header?.type ?? '') as HeaderType | '',
    header: header?.type === 'TEXT' ? header.text : '',
    // Text header examples are kept; a media header keeps the file already on the template.
    headerSample: header?.type === 'TEXT' ? header.sample : '',
    footer: footer?.text ?? '',
    buttons: buttons.map((b) => ({ ...b })),
  };
}

export function TemplateEditor({ mode, gateway, detail, isAdmin, onCancel, onSaved }: Props) {
  const editing = mode === 'edit';
  const [state, setState] = useState(() => initialForm(detail));
  const [busy, setBusy] = useState<'submit' | 'draft' | ''>('');
  const [attempted, setAttempted] = useState(false);
  const [serverError, setServerError] = useState('');
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  const patch = (p: Partial<typeof state>) => setState((s) => ({ ...s, ...p }));
  const { name, category, language, body, samples, headerType, header, headerSample, footer, buttons } = state;
  const holes = extractPlaceholders(body);
  const headerHasVariable = headerType === 'TEXT' && extractPlaceholders(header).length > 0;
  const quickCount = buttons.filter((b) => b.type === 'QUICK_REPLY').length;
  const linkCount = buttons.length - quickCount;
  const hadMedia = editing && (detail?.components.header?.type === 'IMAGE' || detail?.components.header?.type === 'DOCUMENT');

  const form: TemplateForm = {
    name, category, language, body, samples, headerType, header, headerSample, footer, buttons,
    keepExistingMedia: hadMedia && headerType === detail?.components.header?.type,
  };
  const problem = validateTemplateForm(form);
  const nameProblem = editing ? null : templateNameProblem(name);
  const bodyProblem = bodyVariableEdgeProblem(body);

  const previewInput = { headerType, header, headerSample, body, samples, footer, buttons };

  const updateButton = (i: number, p: Partial<TemplateButton>) =>
    setState((s) => ({ ...s, buttons: s.buttons.map((b, idx) => (idx === i ? { ...b, ...p } : b)) }));
  const addButton = (type: TemplateButtonType) => setState((s) => ({ ...s, buttons: [...s.buttons, { type, text: '' }] }));
  const setSample = (i: number, value: string) =>
    setState((s) => {
      const next = [...s.samples];
      while (next.length <= i) next.push('');
      next[i] = value;
      return { ...s, samples: next };
    });

  const addVariable = () => {
    const el = bodyRef.current;
    const res = insertVariable(body, el ? el.selectionStart : null);
    patch({ body: res.body });
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(res.caret, res.caret);
    });
  };

  const run = async (kind: 'submit' | 'draft') => {
    setAttempted(true);
    if (problem) return;
    setServerError('');
    setBusy(kind);
    const valid = { ...form, category };
    let res;
    if (editing && detail && kind === 'submit') {
      res = await editTemplate(detail.name, buildEditPayload(valid));
    } else if (kind === 'draft') {
      res = await createTemplateDraft(gateway ?? '', buildTemplatePayload(valid));
    } else {
      res = await createTemplate(gateway ?? '', buildTemplatePayload(valid));
    }
    setBusy('');
    if (!res.success) return setServerError(errorText(res));
    if (editing) toast.success('Changes sent to WhatsApp for review');
    else if (kind === 'draft') toast.success('Draft saved. An admin will review it.');
    else toast.success('Template sent to WhatsApp for review');
    onSaved({ kind: editing ? 'edited' : kind === 'draft' ? 'draft' : 'submitted', name: res.name });
  };

  const showProblem = attempted && problem;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onCancel}>
          <ArrowLeft className="mr-1.5 h-4 w-4" /> Back to templates
        </Button>
        <h2 className="text-base font-semibold text-ink">{editing ? `Edit ${detail?.template_name}` : 'New template'}</h2>
      </div>
      {editing && (
        <p className="text-xs text-steel">
          Saving sends the template back to WhatsApp for review. The name and language cannot be changed.
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-[1fr_200px_140px]">
            <div className="space-y-1">
              <Label htmlFor="wa-tpl-name">Name</Label>
              <Input
                id="wa-tpl-name" value={name} disabled={editing} className="font-mono" placeholder="order_update"
                onChange={(e) => patch({ name: e.target.value })} aria-invalid={!!nameProblem}
              />
              {nameProblem ? (
                <p role="alert" className="text-[11px] text-destructive">{nameProblem}</p>
              ) : (
                <p className="text-[11px] text-steel">Lowercase letters, digits and underscores.</p>
              )}
            </div>
            <div className="space-y-1">
              <Label>Category</Label>
              <Select value={category} onValueChange={(v) => patch({ category: v as TemplateCategory })}>
                <SelectTrigger aria-label="Category"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="MARKETING">Marketing</SelectItem>
                  <SelectItem value="UTILITY">Utility</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="wa-tpl-lang">Language</Label>
              <Input id="wa-tpl-lang" value={language} disabled={editing} className="font-mono" onChange={(e) => patch({ language: e.target.value })} />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Header (optional)</Label>
            <Select value={headerType || 'none'} onValueChange={(v) => patch({ headerType: v === 'none' ? '' : (v as HeaderType), headerSample: '' })}>
              <SelectTrigger aria-label="Header type" className="w-48"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No header</SelectItem>
                {HEADER_TYPES.map((h) => <SelectItem key={h} value={h}>{HEADER_LABEL[h]}</SelectItem>)}
              </SelectContent>
            </Select>
            {headerType === 'TEXT' && (
              <>
                <Input aria-label="Header text" value={header} onChange={(e) => patch({ header: e.target.value })} placeholder="Order {{1}}" />
                <p className="text-[11px] text-steel">{header.length}/{TEMPLATE_LIMITS.header} characters. One variable, {'{{1}}'}, is allowed.</p>
              </>
            )}
            {headerHasVariable && (
              <Input aria-label="Header example" value={headerSample} onChange={(e) => patch({ headerSample: e.target.value })} placeholder="Example value for {{1}}" />
            )}
            {(headerType === 'IMAGE' || headerType === 'DOCUMENT') && (
              <>
                <Input
                  aria-label="Header media link" value={headerSample} onChange={(e) => patch({ headerSample: e.target.value })}
                  placeholder="https://example.com/sample.png"
                />
                <p className="text-[11px] text-steel">
                  {form.keepExistingMedia
                    ? 'Leave empty to keep the current file, or paste a link to replace it.'
                    : `A public link to a sample ${headerType === 'IMAGE' ? 'image' : 'document'} for review.`}
                </p>
              </>
            )}
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="wa-tpl-body">Message</Label>
              <Button type="button" variant="outline" size="sm" onClick={addVariable}>
                <Braces className="mr-1.5 h-3.5 w-3.5" /> Add variable
              </Button>
            </div>
            <Textarea
              id="wa-tpl-body" ref={bodyRef} rows={6} value={body} onChange={(e) => patch({ body: e.target.value })}
              placeholder="Hi {{1}}, your order {{2}} has shipped." aria-invalid={!!bodyProblem}
            />
            <div className="flex justify-between gap-3 text-[11px]">
              <span className={bodyProblem ? 'text-destructive' : 'text-steel'} role={bodyProblem ? 'alert' : undefined}>
                {bodyProblem ?? 'Variables like {{1}} are replaced with real values when you send.'}
              </span>
              <span className="shrink-0 text-steel">{body.length}/{TEMPLATE_LIMITS.body}</span>
            </div>
          </div>

          {holes.length > 0 && (
            <div className="space-y-2">
              <Label>Example values</Label>
              <p className="text-[11px] text-steel">WhatsApp reviewers use these to understand what each variable stands for.</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {holes.map((n, i) => (
                  <div key={n} className="space-y-1">
                    <Label htmlFor={`wa-tpl-sample-${n}`} className="font-mono text-[11px] text-steel">{`{{${n}}}`}</Label>
                    <Input id={`wa-tpl-sample-${n}`} value={samples[i] ?? ''} onChange={(e) => setSample(i, e.target.value)} />
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-1">
            <Label htmlFor="wa-tpl-footer">Footer (optional)</Label>
            <Input id="wa-tpl-footer" value={footer} onChange={(e) => patch({ footer: e.target.value })} />
            <p className="text-[11px] text-steel">{footer.length}/{TEMPLATE_LIMITS.footer} characters.</p>
          </div>

          <div className="space-y-2">
            <Label>Buttons (optional)</Label>
            {buttons.map((b, i) => (
              <div key={i} className="space-y-1.5 rounded-sm border border-line p-3">
                <div className="flex items-center justify-between text-[11px] uppercase text-steel">
                  <span>{b.type === 'QUICK_REPLY' ? 'Quick reply' : b.type === 'URL' ? 'Link' : 'Phone'}</span>
                  <Button variant="ghost" size="icon" aria-label={`Remove button ${i + 1}`} onClick={() => patch({ buttons: buttons.filter((_, idx) => idx !== i) })}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
                <Input aria-label={`Button ${i + 1} text`} value={b.text} maxLength={TEMPLATE_LIMITS.button} onChange={(e) => updateButton(i, { text: e.target.value })} placeholder="Button text" />
                {b.type === 'URL' && (
                  <>
                    <Input aria-label={`Button ${i + 1} link`} value={b.url ?? ''} onChange={(e) => updateButton(i, { url: e.target.value })} placeholder="https://example.com/track/{{1}}" />
                    {(b.url ?? '').includes('{{') && (
                      <Input aria-label={`Button ${i + 1} example link`} value={b.example ?? ''} onChange={(e) => updateButton(i, { example: e.target.value })} placeholder="https://example.com/track/123" />
                    )}
                  </>
                )}
                {b.type === 'PHONE_NUMBER' && (
                  <Input aria-label={`Button ${i + 1} phone`} value={b.phone_number ?? ''} onChange={(e) => updateButton(i, { phone_number: e.target.value })} placeholder="+15551234567" />
                )}
              </div>
            ))}
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" disabled={quickCount >= TEMPLATE_LIMITS.quickReplies} onClick={() => addButton('QUICK_REPLY')}>
                Add quick reply
              </Button>
              <Button type="button" variant="outline" size="sm" disabled={linkCount >= TEMPLATE_LIMITS.cta} onClick={() => addButton('URL')}>
                Add link
              </Button>
              <Button type="button" variant="outline" size="sm" disabled={linkCount >= TEMPLATE_LIMITS.cta || buttons.some((b) => b.type === 'PHONE_NUMBER')} onClick={() => addButton('PHONE_NUMBER')}>
                Add phone
              </Button>
            </div>
            <p className="text-[11px] text-steel">
              Up to {TEMPLATE_LIMITS.quickReplies} quick replies, or {TEMPLATE_LIMITS.cta} link or phone buttons (one phone at most). Keep quick replies together and links together.
            </p>
          </div>

          {(showProblem || serverError) && (
            <p role="alert" className="text-xs text-destructive">{serverError || problem}</p>
          )}

          <div className="flex flex-wrap justify-end gap-2 border-t border-line pt-4">
            <Button variant="outline" onClick={onCancel}>Cancel</Button>
            {!editing && (
              <Button variant={isAdmin ? 'outline' : 'default'} disabled={!!busy} onClick={() => run('draft')}>
                {busy === 'draft' && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                {isAdmin ? 'Save as draft' : 'Request approval'}
              </Button>
            )}
            {(isAdmin || editing) && (
              <Button disabled={!!busy} onClick={() => run('submit')}>
                {busy === 'submit' && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                {editing ? 'Save and resubmit' : 'Submit for review'}
              </Button>
            )}
          </div>
        </div>

        <aside className="lg:sticky lg:top-4 lg:self-start">
          <p className="mb-2 text-[11px] uppercase tracking-wide text-steel">Preview</p>
          <TemplatePreview input={previewInput} />
        </aside>
      </div>
    </div>
  );
}
