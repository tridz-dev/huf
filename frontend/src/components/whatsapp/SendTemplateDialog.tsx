import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  errorText, extractPlaceholders, getTemplate, sendTemplateMessage, type ButtonParam, type CarouselCardDef,
  type CarouselCardParam, type HeaderParam, type WhatsAppTemplate,
} from '@/services/whatsappApi';
import { TemplatePreview } from './TemplatePreview';
import { rowToPreviewInput } from './templateModel';

export function SendTemplateDialog({ template, onClose, gateway, initialTo = '' }: { template: WhatsAppTemplate | null; onClose: () => void; gateway?: string; initialTo?: string }) {
  const [to, setTo] = useState(initialTo);
  useEffect(() => { if (template) setTo(initialTo); }, [template, initialTo]);
  const [params, setParams] = useState<string[]>([]);
  const [headerValue, setHeaderValue] = useState('');
  const [urlSuffixes, setUrlSuffixes] = useState<Record<number, string>>({});
  const [cards, setCards] = useState<CarouselCardDef[]>([]);
  const [cardValues, setCardValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  // Carousel cards are not on the list row: read them from the template detail.
  useEffect(() => {
    setCards([]); setCardValues({});
    if (!template?.name) return;
    let live = true;
    Promise.resolve(getTemplate(template.name))
      .then((d) => { if (live && d?.success !== false) setCards(d?.components?.carousel ?? []); })
      .catch(() => undefined);
    return () => { live = false; };
  }, [template?.name]);
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
    const v = (k: string) => (cardValues[k] ?? '').trim();
    const carousel_params: CarouselCardParam[] = cards.map((card, i) => ({
      header: { type: card.header_type === 'VIDEO' ? 'video' : 'image', link: v(`${i}:h`) },
      body: card.body_vars.map((_, j) => cardValues[`${i}:b${j}`] ?? ''),
      buttons: card.buttons
        .map((b, index) => ({ b, index }))
        .filter(({ b }) => b.type === 'QUICK_REPLY' || b.dynamic)
        .map(({ b, index }) => ({
          index, sub_type: b.type === 'QUICK_REPLY' ? 'quick_reply' as const : 'url' as const, text: cardValues[`${i}:u${index}`] ?? '',
        })),
    }));
    const res = await sendTemplateMessage({
      gateway_name: gateway,
      to,
      template_name: template.template_name || template.name,
      body_params: holes.map((_, i) => params[i] ?? ''),
      header_params,
      button_params,
      ...(cards.length ? { carousel_params } : {}),
    });
    setBusy(false);
    if (res.success) {
      toast.success('Template sent');
      setParams([]); setHeaderValue(''); setUrlSuffixes({}); setCardValues({});
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
            {cards.map((card, i) => (
              <fieldset key={i} className="space-y-1 rounded-md border p-2">
                <legend className="px-1 text-xs font-medium">{`Card ${i + 1}`}</legend>
                <Label htmlFor={`wa-card-${i}-h`}>{card.header_type === 'VIDEO' ? 'Video link' : 'Image link'}</Label>
                <Input id={`wa-card-${i}-h`} value={cardValues[`${i}:h`] ?? ''} placeholder="https://example.com/file"
                  onChange={(e) => setCardValues((c) => ({ ...c, [`${i}:h`]: e.target.value }))} />
                {card.body_vars.map((n, j) => (
                  <div key={j}>
                    <Label htmlFor={`wa-card-${i}-b${j}`}>{`{{${n}}}`}</Label>
                    <Input id={`wa-card-${i}-b${j}`} value={cardValues[`${i}:b${j}`] ?? ''}
                      onChange={(e) => setCardValues((c) => ({ ...c, [`${i}:b${j}`]: e.target.value }))} />
                  </div>
                ))}
                {card.buttons.map((b, index) => (b.type === 'QUICK_REPLY' || b.dynamic) && (
                  <div key={index}>
                    <Label htmlFor={`wa-card-${i}-u${index}`}>{b.type === 'QUICK_REPLY' ? `Button ${index + 1} payload` : `Button ${index + 1} (end of link)`}</Label>
                    <Input id={`wa-card-${i}-u${index}`} value={cardValues[`${i}:u${index}`] ?? ''}
                      onChange={(e) => setCardValues((c) => ({ ...c, [`${i}:u${index}`]: e.target.value }))} />
                  </div>
                ))}
              </fieldset>
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
