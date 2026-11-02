import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { ChevronDown } from 'lucide-react';
import { Field, FieldRow } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { errorText, type WhatsAppError } from '@/services/whatsappApi';
import { SEND_TYPES, SendForm, SendTypePicker, type SendType } from './SendForms';

/** Collapsed by default: this tab is a log, not an inbox. */
export function SendPanel({
  gateway, onSent, openRequested = false, onOpenHandled,
}: {
  gateway?: string;
  onSent: () => void;
  /** Open the panel (for example from the `#test-message` checklist link). */
  openRequested?: boolean;
  /** Called once the request was applied, so the caller can clear it. */
  onOpenHandled?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const toRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!openRequested) return;
    setOpen(true);
    onOpenHandled?.();
    const frame = requestAnimationFrame(() => {
      rootRef.current?.scrollIntoView?.({ block: 'nearest' });
      toRef.current?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [openRequested, onOpenHandled]);
  const [to, setTo] = useState('');
  const [type, setType] = useState<SendType>('text');
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<WhatsAppError | null>(null);

  const run = async (send: () => Promise<{ success: boolean } | WhatsAppError>, done: string, reset: () => void) => {
    setSending(true);
    setSendError(null);
    const res = await send();
    setSending(false);
    if (res.success) { reset(); toast.success(done); onSent(); } else setSendError(res as WhatsAppError);
  };
  const note = SEND_TYPES.find((t) => t.value === type)?.note;

  return (
    <Collapsible ref={rootRef} open={open} onOpenChange={setOpen} className="rounded-sm border border-line">
      <CollapsibleTrigger className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-ink">
        Send a message
        <ChevronDown className={`h-4 w-4 text-steel transition-transform ${open ? 'rotate-180' : ''}`} />
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-3 border-t border-line p-3">
        <FieldRow className="max-w-full grid-cols-[14rem_11rem]">
          <Field label="To" id="whatsapp-send-to">
            <Input id="whatsapp-send-to" ref={toRef} value={to} onChange={(e) => setTo(e.target.value)} placeholder="+15551234567" className="font-mono" />
          </Field>
          <Field label="Message type" id="whatsapp-send-type">
            <SendTypePicker id="whatsapp-send-type" value={type} onChange={(v) => { setType(v); setSendError(null); }} />
          </Field>
        </FieldRow>
        {note && <p className="text-[11px] text-steel">{note}</p>}
        <div className="max-w-xl">
          {gateway ? (
            <SendForm type={type} gateway={gateway} to={to} run={run} sending={sending} setError={setSendError} />
          ) : (
            <p className="text-xs text-steel">Choose a gateway first.</p>
          )}
        </div>
        {sendError && (
          <p role="alert" className="text-xs text-destructive">
            {errorText(sendError)}
            {sendError.error === 'window_closed' && ' Send an approved template instead.'}
            {sendError.error.startsWith('media_link_') && ' Uploading the file is the reliable way to send media.'}
          </p>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}
