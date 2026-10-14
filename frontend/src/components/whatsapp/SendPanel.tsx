import { useState } from 'react';
import { toast } from 'sonner';
import { ChevronDown, Loader2, Paperclip, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  MEDIA_KINDS, errorText, sendMediaMessage, sendTextMessage, uploadPublicFile, validateMediaSend,
  type MediaKind, type WhatsAppError,
} from '@/services/whatsappApi';
import { TemplateSend } from './TemplateSend';

/** Collapsed by default: this tab is a log, not an inbox. */
export function SendPanel({ gateway, onSent }: { gateway?: string; onSent: () => void }) {
  const [open, setOpen] = useState(false);
  const [to, setTo] = useState('');
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<WhatsAppError | null>(null);
  const [mediaKind, setMediaKind] = useState<MediaKind>('image');
  const [mediaLink, setMediaLink] = useState('');
  const [mediaFile, setMediaFile] = useState<{ fileUrl: string; name: string } | null>(null);
  const [mediaCaption, setMediaCaption] = useState('');
  const [uploading, setUploading] = useState(false);

  const send = async () => {
    if (!gateway) return;
    setSending(true);
    setSendError(null);
    const res = await sendTextMessage(gateway, to, text);
    setSending(false);
    if (res.success) { setText(''); toast.success('Message sent'); onSent(); } else setSendError(res);
  };

  const pickFile = async (f: File | undefined) => {
    if (!f) return;
    setUploading(true);
    setSendError(null);
    const res = await uploadPublicFile(f);
    setUploading(false);
    if ('fileUrl' in res) { setMediaFile({ fileUrl: res.fileUrl, name: f.name }); setMediaLink(''); } else setSendError(res);
  };

  const sendMedia = async () => {
    if (!gateway) return;
    const problem = validateMediaSend({ kind: mediaKind, link: mediaLink, fileUrl: mediaFile?.fileUrl, caption: mediaCaption });
    if (problem) return setSendError({ success: false, error: 'invalid_media', message: problem });
    setSending(true);
    setSendError(null);
    const res = await sendMediaMessage(gateway, to, {
      kind: mediaKind,
      link: mediaLink,
      fileUrl: mediaLink.trim() ? undefined : mediaFile?.fileUrl,
      caption: mediaCaption,
      filename: mediaKind === 'document' ? mediaFile?.name : undefined,
    });
    setSending(false);
    if (res.success) {
      toast.success('Media sent');
      setMediaLink(''); setMediaFile(null); setMediaCaption('');
      onSent();
    } else setSendError(res);
  };

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-sm border border-line">
      <CollapsibleTrigger className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-ink">
        Send a message
        <ChevronDown className={`h-4 w-4 text-steel transition-transform ${open ? 'rotate-180' : ''}`} />
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-3 border-t border-line p-3">
        <Input value={to} onChange={(e) => setTo(e.target.value)} placeholder="+15551234567" className="max-w-xs font-mono" aria-label="Recipient number" />
        <div className="grid gap-3 lg:grid-cols-3">
          <div className="space-y-1">
            <p className="text-xs font-medium text-ink">Text</p>
            <p className="text-[11px] text-steel">Only within 24 hours of the customer's last message.</p>
            <div className="flex gap-2">
              <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a message" aria-label="Message text" />
              <Button onClick={send} disabled={!gateway || sending || !text.trim() || !to.trim()} aria-label="Send message">
                {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </div>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-medium text-ink">Template</p>
            <p className="text-[11px] text-steel">Works any time, including outside the 24-hour window.</p>
            <TemplateSend gateway={gateway} to={to} />
          </div>
          <div className="space-y-2">
            <p className="flex items-center gap-1 text-xs font-medium text-ink"><Paperclip className="h-3 w-3" /> Media link</p>
            <div className="flex gap-2">
              <Select value={mediaKind} onValueChange={(v) => setMediaKind(v as MediaKind)}>
                <SelectTrigger className="w-28" aria-label="Media type"><SelectValue /></SelectTrigger>
                <SelectContent>{MEDIA_KINDS.map((k) => <SelectItem key={k} value={k}>{k[0].toUpperCase() + k.slice(1)}</SelectItem>)}</SelectContent>
              </Select>
              <Input
                value={mediaLink}
                onChange={(e) => { setMediaLink(e.target.value); if (e.target.value) setMediaFile(null); }}
                placeholder="Public link, https://..."
                aria-label="Media link"
              />
            </div>
            <div className="flex items-center gap-2 text-xs text-steel">
              <label className="cursor-pointer rounded-sm border border-line px-2 py-1 hover:bg-paper-deep">
                {uploading ? 'Uploading...' : 'Choose file'}
                <input type="file" className="sr-only" aria-label="Media file" onChange={(e) => void pickFile(e.target.files?.[0])} />
              </label>
              <span className="truncate">{mediaFile ? mediaFile.name : 'or upload a file'}</span>
            </div>
            {mediaKind !== 'audio' && (
              <Input value={mediaCaption} onChange={(e) => setMediaCaption(e.target.value)} placeholder="Caption (optional)" aria-label="Media caption" />
            )}
            <Button size="sm" onClick={sendMedia} disabled={!gateway || sending || uploading || !to.trim()}>
              {sending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}Send media
            </Button>
          </div>
        </div>
        {sendError && (
          <p role="alert" className="text-xs text-destructive">
            {errorText(sendError)}
            {sendError.error === 'window_closed' && ' Send an approved template instead.'}
          </p>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
