import { Plus, Trash2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';

/**
 * Structured value the WhatsApp `send_template` action sends to
 * `huf.ai.tools.whatsapp.handle_action`. `parameters` fills the template
 * body's numbered placeholders ({{1}}, {{2}}, ...) in order.
 */
export interface WhatsAppTemplateValue {
  template_name: string;
  language_code: string;
  parameters: string[];
}

export const DEFAULT_WHATSAPP_TEMPLATE_VALUE: WhatsAppTemplateValue = {
  template_name: '',
  language_code: 'en_US',
  parameters: [],
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
    </div>
  );
}
