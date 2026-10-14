import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  errorText, extractPlaceholders, sendTemplateMessage, type ButtonParam, type HeaderParam, type WhatsAppTemplate,
} from '@/services/whatsappApi';
import { TemplatePreview } from './TemplatePreview';
import { rowToPreviewInput } from './templateModel';

export function SendTemplateDialog({ template, onClose, gateway, initialTo = '' }: { template: WhatsAppTemplate | null; onClose: () => void; gateway?: string; initialTo?: string }) {
  const [to, setTo] = useState(initialTo);
  useEffect(() => { if (template) setTo(initialTo); }, [template, initialTo]);
  const [params, setParams] = useState<string[]>([]);
  const [headerValue, setHeaderValue] = useState('');
  const [urlSuffixes, setUrlSuffixes] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const holes = extractPlaceholders(template?.template || '');
  const headerType = template?.header_type || '';
  const headerNeedsText = headerType === 'TEXT' && extractPlaceholders(template?.header || '').length > 0;
  const headerNeedsMedia = headerType === 'IMAGE' || headerType === 'DOCUMENT';
  const dynamicUrlButtons = (template?.buttons ?? [])
    .map((b, index) => ({ b, index }))
    .filter(({ b }) => b.button_type === 'Visit Website' && b.url_type === 'Dynamic');

  const send = async () => {
    if (!template || !gateway) return;
    setBusy(true);
    setErr('');
    const header_params: HeaderParam[] = headerNeedsText
      ? [headerValue]
      : headerNeedsMedia && headerValue.trim()
        ? [{ type: headerType === 'IMAGE' ? 'image' : 'document', link: headerValue.trim() }]
        : [];
    const button_params: ButtonParam[] = dynamicUrlButtons.map(({ index }) => ({ index, sub_type: 'url', text: urlSuffixes[index] ?? '' }));
    const res = await sendTemplateMessage({
      gateway_name: gateway,
      to,
      template_name: template.template_name || template.name,
      body_params: holes.map((_, i) => params[i] ?? ''),
      header_params,
      button_params,
    });
    setBusy(false);
    if (res.success) {
      toast.success('Template sent');
      setParams([]); setHeaderValue(''); setUrlSuffixes({});
      onClose();
    } else setErr(errorText(res));
  };

  const preview = template
    ? { ...rowToPreviewInput(template, holes.map((_, i) => params[i] ?? '')), headerSample: headerValue }
    : null;

  return (
    <Dialog open={!!template} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Send template</DialogTitle>
          <DialogDescription className="font-mono">{template?.template_name}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-5 md:grid-cols-[1fr_300px]">
          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="wa-send-to">Recipient</Label>
              <Input id="wa-send-to" value={to} onChange={(e) => setTo(e.target.value)} placeholder="+15551234567" className="font-mono" />
            </div>
            {headerNeedsText && (
              <div className="space-y-1">
                <Label htmlFor="wa-send-header">Header value</Label>
                <Input id="wa-send-header" value={headerValue} onChange={(e) => setHeaderValue(e.target.value)} />
              </div>
            )}
            {headerNeedsMedia && (
              <div className="space-y-1">
                <Label htmlFor="wa-send-header">{headerType === 'IMAGE' ? 'Header image link' : 'Header document link'}</Label>
                <Input id="wa-send-header" value={headerValue} onChange={(e) => setHeaderValue(e.target.value)} placeholder="https://example.com/file" />
              </div>
            )}
            {holes.map((n, i) => (
              <div key={n} className="space-y-1">
                <Label htmlFor={`wa-send-p-${n}`}>{`{{${n}}}`}</Label>
                <Input id={`wa-send-p-${n}`} value={params[i] ?? ''} onChange={(e) => setParams((p) => { const next = [...p]; next[i] = e.target.value; return next; })} />
              </div>
            ))}
            {dynamicUrlButtons.map(({ b, index }) => (
              <div key={index} className="space-y-1">
                <Label htmlFor={`wa-send-url-${index}`}>{`${b.button_label || 'Link'} (end of link)`}</Label>
                <Input id={`wa-send-url-${index}`} value={urlSuffixes[index] ?? ''} onChange={(e) => setUrlSuffixes((u) => ({ ...u, [index]: e.target.value }))} />
              </div>
            ))}
            {err && <p role="alert" className="text-xs text-destructive">{err}</p>}
          </div>
          {preview && <TemplatePreview input={preview} />}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={send} disabled={busy || !to.trim()}>{busy && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}Send</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
