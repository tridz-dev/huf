import { useEffect, useState } from 'react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { errorText, listTemplates, type WhatsAppTemplate } from '@/services/whatsappApi';
import { SendTemplateDialog } from './SendTemplateDialog';

/** Pick an approved template for a gateway, then fill it in the send dialog (optionally for a known number). */
export function TemplateSend({ gateway, to = '' }: { gateway?: string; to?: string }) {
  const [templates, setTemplates] = useState<WhatsAppTemplate[]>([]);
  const [error, setError] = useState('');
  const [chosen, setChosen] = useState<WhatsAppTemplate | null>(null);

  useEffect(() => {
    if (!gateway) return;
    let live = true;
    void listTemplates(gateway, 'APPROVED').then((res) => {
      if (!live) return;
      if (res.success) { setTemplates(res.templates); setError(''); } else setError(errorText(res));
    });
    return () => { live = false; };
  }, [gateway]);

  return (
    <div className="space-y-1">
      <Select
        value=""
        onValueChange={(v) => setChosen(templates.find((t) => (t.template_name || t.name) === v) ?? null)}
        disabled={!gateway || templates.length === 0}
      >
        <SelectTrigger aria-label="Send a template">
          <SelectValue placeholder={templates.length === 0 && !error ? 'No approved templates' : 'Send a template...'} />
        </SelectTrigger>
        <SelectContent>
          {templates.map((t) => {
            const id = t.template_name || t.name;
            return <SelectItem key={t.name} value={id}>{id}</SelectItem>;
          })}
        </SelectContent>
      </Select>
      {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
      <SendTemplateDialog template={chosen} onClose={() => setChosen(null)} gateway={gateway} initialTo={to} />
    </div>
  );
}
