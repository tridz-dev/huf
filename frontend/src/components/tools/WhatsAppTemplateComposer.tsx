import { Plus, Trash2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import type { ButtonParam, HeaderParam } from '@/services/whatsappApi';

export type HeaderKind = 'none' | 'text' | 'image' | 'document' | 'video';

export interface UrlButtonSuffix {
  index: number;
  text: string;
}

/**
 * Structured value the WhatsApp `send_template` action sends to
 * `huf.ai.tools.whatsapp.handle_action`. `parameters` fills the template
 * body's numbered placeholders ({{1}}, {{2}}, ...) in order.
 */
export interface WhatsAppTemplateValue {
  template_name: string;
  language_code: string;
  parameters: string[];
  header_kind: HeaderKind;
  header_value: string;
  url_buttons: UrlButtonSuffix[];
}

export const DEFAULT_WHATSAPP_TEMPLATE_VALUE: WhatsAppTemplateValue = {
  template_name: '',
  language_code: 'en_US',
  parameters: [],
  header_kind: 'none',
  header_value: '',
  url_buttons: [],
};

/** Backend `header_params` for the chosen header: one text value or one media link. */
export function buildHeaderParams(kind: HeaderKind, header: string): HeaderParam[] {
  const v = header.trim();
  if (kind === 'none' || !v) return [];
  return kind === 'text' ? [v] : [{ type: kind, link: v }];
}

/** Backend `button_params` for URL-button suffixes; blank rows are dropped. */
export function buildButtonParams(rows: UrlButtonSuffix[]): ButtonParam[] {
  return rows
    .filter((r) => r.text.trim())
    .map((r) => ({ index: r.index, sub_type: 'url' as const, text: r.text.trim() }));
}

/** Tool arguments for the composer value (header_params / button_params only when set). */
export function buildTemplateArgs(value: WhatsAppTemplateValue): Record<string, unknown> {
  const args: Record<string, unknown> = {
    template_name: value.template_name.trim(),
    language_code: value.language_code.trim() || 'en_US',
    parameters: value.parameters,
  };
  const header = buildHeaderParams(value.header_kind, value.header_value);
  if (header.length) args.header_params = header;
  const buttons = buildButtonParams(value.url_buttons);
  if (buttons.length) args.button_params = buttons;
  return args;
}

const HEADER_LABELS: Record<HeaderKind, string> = {
  none: 'No header variable',
  text: 'Text',
  image: 'Image link',
  document: 'Document link',
  video: 'Video link',
};

interface WhatsAppTemplateComposerProps {
  value: WhatsAppTemplateValue;
  onChange: (value: WhatsAppTemplateValue) => void;
}

/**
 * GW-36: template-name field plus a structured (add/remove row) editor for a
 * WhatsApp template's body parameters, so sending a template message never
 * requires hand-constructing the underlying Graph API `components` JSON.
 */
export function WhatsAppTemplateComposer({ value, onChange }: WhatsAppTemplateComposerProps) {
  const setField = <K extends keyof WhatsAppTemplateValue>(key: K, next: WhatsAppTemplateValue[K]) => {
    onChange({ ...value, [key]: next });
  };

  const setParameter = (index: number, next: string) => {
    const parameters = [...value.parameters];
    parameters[index] = next;
    setField('parameters', parameters);
  };

  const addParameter = () => {
    setField('parameters', [...value.parameters, '']);
  };

  const removeParameter = (index: number) => {
    setField(
      'parameters',
      value.parameters.filter((_, i) => i !== index)
    );
  };

  const setUrlButton = (position: number, text: string) => {
    setField(
      'url_buttons',
      value.url_buttons.map((b, i) => (i === position ? { ...b, text } : b))
    );
  };

  const addUrlButton = () => {
    const next = value.url_buttons.length ? Math.max(...value.url_buttons.map((b) => b.index)) + 1 : 0;
    if (next > 9) return;
    setField('url_buttons', [...value.url_buttons, { index: next, text: '' }]);
  };

  const removeUrlButton = (position: number) => {
    setField(
      'url_buttons',
      value.url_buttons.filter((_, i) => i !== position)
    );
  };

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="whatsapp-template-name">
          Template name<span className="text-destructive"> *</span>
        </Label>
        <Input
          id="whatsapp-template-name"
          placeholder="order_update"
          value={value.template_name}
          onChange={(e) => setField('template_name', e.target.value)}
        />
        <p className="text-xs text-steel">
          Must match an approved template name in your WhatsApp Business Account.
        </p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="whatsapp-template-language">Language code</Label>
        <Input
          id="whatsapp-template-language"
          placeholder="en_US"
          value={value.language_code}
          onChange={(e) => setField('language_code', e.target.value)}
        />
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>Template parameters</Label>
          <Button type="button" variant="outline" size="sm" onClick={addParameter}>
            <Plus className="w-3.5 h-3.5 mr-1" />
            Add parameter
          </Button>
        </div>
        {value.parameters.length === 0 ? (
          <p className="text-xs text-steel border border-dashed rounded p-3 text-center">
            No parameters. Add one for each placeholder ({'{{'}1{'}}'}, {'{{'}2{'}}'}, ...) the template body uses.
          </p>
        ) : (
          <div className="space-y-2">
            {value.parameters.map((param, index) => (
              <div key={index} className="flex items-center gap-2">
                <span className="text-xs font-mono text-steel-soft w-8 shrink-0">{`{{${index + 1}}}`}</span>
                <Input
                  value={param}
                  placeholder={`Value for placeholder ${index + 1}`}
                  onChange={(e) => setParameter(index, e.target.value)}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => removeParameter(index)}
                  aria-label={`Remove parameter ${index + 1}`}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-1.5">
        <Label>Header (optional)</Label>
        <Select
          value={value.header_kind}
          onValueChange={(v) => onChange({ ...value, header_kind: v as HeaderKind, header_value: '' })}
        >
          <SelectTrigger aria-label="Header type"><SelectValue /></SelectTrigger>
          <SelectContent>
            {(Object.keys(HEADER_LABELS) as HeaderKind[]).map((k) => (
              <SelectItem key={k} value={k}>{HEADER_LABELS[k]}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        {value.header_kind !== 'none' && (
          <>
            <Input
              aria-label={value.header_kind === 'text' ? 'Header text' : 'Header media link'}
              value={value.header_value}
              placeholder={value.header_kind === 'text' ? 'Value for the header variable' : 'https://example.com/file'}
              onChange={(e) => setField('header_value', e.target.value)}
            />
            <p className="text-xs text-steel">
              {value.header_kind === 'text'
                ? 'Fills the header variable, up to 60 characters.'
                : 'A public https link to the file WhatsApp should attach.'}
            </p>
          </>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>Link button endings</Label>
          <Button type="button" variant="outline" size="sm" onClick={addUrlButton} disabled={value.url_buttons.length >= 10}>
            <Plus className="w-3.5 h-3.5 mr-1" />
            Add link ending
          </Button>
        </div>
        {value.url_buttons.length === 0 ? (
          <p className="text-xs text-steel border border-dashed rounded p-3 text-center">
            Only needed when a link button's address ends in a variable.
          </p>
        ) : (
          <div className="space-y-2">
            {value.url_buttons.map((b, position) => (
              <div key={position} className="flex items-center gap-2">
                <span className="text-xs text-steel-soft w-16 shrink-0">Button {b.index + 1}</span>
                <Input
                  value={b.text}
                  placeholder="orders/1234"
                  aria-label={`Link ending for button ${b.index + 1}`}
                  onChange={(e) => setUrlButton(position, e.target.value)}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => removeUrlButton(position)}
                  aria-label={`Remove link ending for button ${b.index + 1}`}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
