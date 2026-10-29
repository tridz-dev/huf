import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { CopyField } from '@/components/ui/copy-field';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { getClickToChat, getWidgetSnippet, type ClickToChat } from '@/services/channelsRulesApi';
import type { PanelProps } from './panels';

export function WidgetsPanel({ gw, health }: PanelProps) {
  const [prefill, setPrefill] = useState('');
  const [ref, setRef] = useState('');
  const [link, setLink] = useState<ClickToChat | null>(null);
  const [snippet, setSnippet] = useState('');
  const [error, setError] = useState('');
  const phone = health.token_check?.phone?.display ?? null;

  useEffect(() => {
    let live = true;
    const t = setTimeout(async () => {
      try {
        const [l, s] = await Promise.all([
          getClickToChat(gw, prefill, ref, phone),
          getWidgetSnippet(gw, prefill, ref, '', 'right', phone),
        ]);
        if (live) { setLink(l); setSnippet(s); setError(''); }
      } catch (e) {
        if (live) setError(getFrappeErrorMessage(e));
      }
    }, 300);
    return () => { live = false; clearTimeout(t); };
  }, [gw, prefill, ref, phone]);

  const downloadQr = () => {
    if (!link?.qr_svg) return;
    const url = URL.createObjectURL(new Blob([link.qr_svg], { type: 'image/svg+xml' }));
    const a = document.createElement('a');
    a.href = url; a.download = 'whatsapp-qr.svg'; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle className="text-sm">Click-to-chat link</CardTitle></CardHeader>
        <CardContent className="grid max-w-xl gap-3">
          <p className="text-xs text-steel">
            People who message you through this link or widget are recorded as opted in for marketing (source: widget), unless they have sent STOP.
          </p>
          <Field label="Prefilled message" size="sm">
            {(fp) => <Input {...fp} value={prefill} onChange={(e) => setPrefill(e.target.value)} placeholder="Hi, I'd like to know more" />}
          </Field>
          <Field label="Ref tag" size="sm">
            {(fp) => <Input {...fp} value={ref} onChange={(e) => setRef(e.target.value)} placeholder="spring-campaign" />}
          </Field>
          {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
          {link && <CopyField label="wa.me link" value={link.wa_me_url} />}
          {link?.qr_svg ? (
            <div className="space-y-2">
              <div className="w-40 rounded-md border bg-card p-2" aria-label="QR code" dangerouslySetInnerHTML={{ __html: link.qr_svg }} />
              <Button variant="outline" size="sm" onClick={downloadQr}><Download className="h-4 w-4" />Download QR</Button>
            </div>
          ) : (
            link && <p className="text-xs text-steel">QR codes are not available in this build. Use the link with any QR generator.</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-sm">Website widget</CardTitle></CardHeader>
        <CardContent className="grid max-w-xl gap-3">
          <p className="text-xs text-steel">Paste this before the closing body tag to add a floating Chat on WhatsApp button.</p>
          {snippet && <CopyField label="Widget snippet" value={snippet} />}
        </CardContent>
      </Card>
    </div>
  );
}
