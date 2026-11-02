import { useMemo, useState } from 'react';
import { useFieldArray, useForm, useFormContext } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Form, FormControl, FormField, FormItem, FormMessage } from '@/components/ui/form';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  INTERACTIVE_LIMITS, sendContactsMessage, sendInteractiveMessage, sendLocationMessage, sendMediaMessage,
  sendReactionMessage, sendStickerMessage, sendTextMessage, sendVoiceNote, uploadPublicFile,
  type InteractiveKind, type MediaKind, type WhatsAppError,
} from '@/services/whatsappApi';
import {
  contactSchema, interactiveSchema, locationSchema, mediaSchema, reactionSchema, textSchema,
  type ContactValues, type InteractiveValues, type LocationValues, type MediaValues, type ReactionValues, type SendMediaKind, type TextValues,
} from './sendSchemas';
import { TemplateSend } from './TemplateSend';

export type SendType =
  | 'text' | 'template' | 'image' | 'document' | 'audio' | 'video' | 'sticker'
  | 'location' | 'contact' | 'reaction' | 'buttons' | 'list' | 'cta_url';

export const SEND_TYPES: { value: SendType; label: string; note: string }[] = [
  { value: 'text', label: 'Text', note: "Only within 24 hours of the customer's last message." },
  { value: 'template', label: 'Template', note: 'Works any time, including outside the 24-hour window.' },
  { value: 'image', label: 'Image', note: 'JPEG or PNG, up to 5 MB.' },
  { value: 'document', label: 'Document', note: 'Up to 100 MB.' },
  { value: 'audio', label: 'Audio', note: 'Up to 16 MB.' },
  { value: 'video', label: 'Video', note: 'MP4 or 3GP, up to 16 MB.' },
  { value: 'sticker', label: 'Sticker', note: 'WebP, up to 100 KB (500 KB if animated).' },
  { value: 'location', label: 'Location', note: 'A map pin.' },
  { value: 'contact', label: 'Contact', note: 'A contact card.' },
  { value: 'reaction', label: 'Reaction', note: 'React to a message the customer sent in the last 30 days.' },
  { value: 'buttons', label: 'Reply buttons', note: 'Up to 3 quick-reply buttons.' },
  { value: 'list', label: 'List', note: 'A menu of up to 10 choices.' },
  { value: 'cta_url', label: 'Link button', note: 'A message with one button that opens a link.' },
];

const MEDIA_TYPES: SendType[] = ['image', 'document', 'audio', 'video'];

interface FormProps {
  gateway: string;
  to: string;
  /** Runs a send; shows the shared error and refreshes the log on success. */
  run: (send: () => Promise<{ success: boolean } | WhatsAppError>, done: string, reset: () => void) => Promise<void>;
  sending: boolean;
  setError: (e: WhatsAppError | null) => void;
}

function SendButton({ sending, disabled, onClick }: { sending: boolean; disabled?: boolean; onClick: () => void }) {
  return (
    <Button size="sm" onClick={onClick} disabled={sending || disabled}>
      {sending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}Send
    </Button>
  );
}

/**
 * Compact send-panel fields: no visible label (the placeholder and aria-label
 * name the control), but the standard FormItem / FormControl / FormMessage
 * anatomy so validation errors render in the shared note row.
 */
function SendInput({ name, itemClassName, onValueChange, ...props }: Omit<React.ComponentProps<typeof Input>, 'name' | 'value' | 'onChange'> & {
  name: string;
  itemClassName?: string;
  onValueChange?: (value: string) => void;
}) {
  const { control } = useFormContext();
  return (
    <FormField control={control} name={name} render={({ field }) => (
      <FormItem className={itemClassName}>
        <FormControl>
          <Input {...field} {...props} value={field.value ?? ''} onChange={(e) => { field.onChange(e.target.value); onValueChange?.(e.target.value); }} />
        </FormControl>
        <FormMessage />
      </FormItem>
    )} />
  );
}

function SendTextarea({ name, ...props }: Omit<React.ComponentProps<typeof Textarea>, 'name' | 'value' | 'onChange'> & { name: string }) {
  const { control } = useFormContext();
  return (
    <FormField control={control} name={name} render={({ field }) => (
      <FormItem>
        <FormControl><Textarea {...field} {...props} value={field.value ?? ''} /></FormControl>
        <FormMessage />
      </FormItem>
    )} />
  );
}

function TextForm({ gateway, to, run, sending, setError }: FormProps) {
  const form = useForm<TextValues>({ resolver: zodResolver(textSchema), defaultValues: { text: '' } });
  const text = form.watch('text');
  const submit = form.handleSubmit(({ text }) => {
    setError(null);
    void run(() => sendTextMessage(gateway, to, text), 'Message sent', () => form.reset());
  });
  return (
    <Form {...form}>
      <div className="space-y-2">
        <SendTextarea name="text" placeholder="Type a message" aria-label="Message text" rows={3} />
        <SendButton sending={sending} disabled={!text.trim() || !to.trim()} onClick={() => void submit()} />
      </div>
    </Form>
  );
}

const MEDIA_DEFAULTS: MediaValues = { link: '', file: null, caption: '', voice: false };

function MediaForm({ kind, gateway, to, run, sending, setError }: FormProps & { kind: SendMediaKind }) {
  const schema = useMemo(() => mediaSchema(kind), [kind]);
  const form = useForm<MediaValues>({ resolver: zodResolver(schema), defaultValues: MEDIA_DEFAULTS });
  const [uploading, setUploading] = useState(false);
  const file = form.watch('file');
  const voice = form.watch('voice');

  const pick = async (f: File | undefined) => {
    if (!f) return;
    setUploading(true);
    setError(null);
    const res = await uploadPublicFile(f);
    setUploading(false);
    if ('fileUrl' in res) {
      form.setValue('file', { fileUrl: res.fileUrl, name: f.name });
      form.setValue('link', '');
      form.clearErrors();
    } else setError(res);
  };
  const submit = form.handleSubmit(({ link, file, caption, voice }) => {
    setError(null);
    const asVoice = kind === 'audio' && voice;
    const fileUrl = link.trim() ? undefined : file?.fileUrl;
    void run(
      () => kind === 'sticker'
        ? sendStickerMessage(gateway, to, { link, fileUrl })
        : asVoice
        ? sendVoiceNote(gateway, to, { link, fileUrl })
        : sendMediaMessage(gateway, to, { kind, link, fileUrl, caption, filename: kind === 'document' ? file?.name : undefined }),
      'Message sent',
      () => form.reset(MEDIA_DEFAULTS),
    );
  });
  return (
    <Form {...form}>
      <div className="space-y-2">
        <SendInput name="link" placeholder="Public link, https://..." aria-label="Media link" onValueChange={(v) => { if (v) form.setValue('file', null); }} />
        <FormField control={form.control} name="file" render={() => (
          <FormItem>
            <div className="flex items-center gap-2 text-xs text-steel">
              <label className="cursor-pointer rounded-sm border border-line px-2 py-1 hover:bg-paper-deep">
                {uploading ? 'Uploading...' : 'Choose file'}
                <input type="file" className="sr-only" aria-label="Media file" onChange={(e) => void pick(e.target.files?.[0])} />
              </label>
              <span className="truncate">{file ? file.name : 'or upload a file'}</span>
            </div>
            <FormMessage />
          </FormItem>
        )} />
        {(kind === 'image' || kind === 'video' || kind === 'document') && (
          <SendInput name="caption" placeholder="Caption (optional)" aria-label="Media caption" />
        )}
        {kind === 'audio' && (
          <label className="flex items-center gap-2 text-xs text-steel">
            <input type="checkbox" checked={voice} onChange={(e) => form.setValue('voice', e.target.checked)} aria-label="Send as voice note" />
            Send as a voice note (Ogg/Opus, mono, up to 16 MB)
          </label>
        )}
        <SendButton sending={sending} disabled={uploading || !to.trim()} onClick={() => void submit()} />
      </div>
    </Form>
  );
}

const LOCATION_DEFAULTS: LocationValues = { lat: '', lng: '', name: '', address: '' };

function LocationForm({ gateway, to, run, sending, setError }: FormProps) {
  const form = useForm<LocationValues>({ resolver: zodResolver(locationSchema), defaultValues: LOCATION_DEFAULTS });
  const submit = form.handleSubmit(({ lat, lng, name, address }) => {
    setError(null);
    void run(() => sendLocationMessage(gateway, to, { latitude: Number(lat), longitude: Number(lng), name, address }), 'Location sent', () => form.reset(LOCATION_DEFAULTS));
  });
  return (
    <Form {...form}>
      <div className="space-y-2">
        <div className="grid grid-cols-2 items-start gap-2">
          <SendInput name="lat" placeholder="Latitude" inputMode="decimal" aria-label="Latitude" />
          <SendInput name="lng" placeholder="Longitude" inputMode="decimal" aria-label="Longitude" />
        </div>
        <SendInput name="name" placeholder="Place name (optional)" aria-label="Place name" />
        <SendInput name="address" placeholder="Address (optional)" aria-label="Address" />
        <SendButton sending={sending} disabled={!to.trim()} onClick={() => void submit()} />
      </div>
    </Form>
  );
}

const CONTACT_DEFAULTS: ContactValues = { name: '', phone: '', email: '', org: '' };

function ContactForm({ gateway, to, run, sending, setError }: FormProps) {
  const form = useForm<ContactValues>({ resolver: zodResolver(contactSchema), defaultValues: CONTACT_DEFAULTS });
  const submit = form.handleSubmit(({ name, phone, email, org }) => {
    setError(null);
    void run(
      () => sendContactsMessage(gateway, to, [{
        name: { formatted_name: name.trim() },
        phones: phone.trim() ? [{ phone: phone.trim() }] : undefined,
        emails: email.trim() ? [{ email: email.trim() }] : undefined,
        org: org.trim() ? { company: org.trim() } : undefined,
      }]),
      'Contact sent',
      () => form.reset(CONTACT_DEFAULTS),
    );
  });
  return (
    <Form {...form}>
      <div className="space-y-2">
        <SendInput name="name" placeholder="Full name" aria-label="Contact name" />
        <div className="grid grid-cols-2 items-start gap-2">
          <SendInput name="phone" placeholder="Phone" aria-label="Contact phone" />
          <SendInput name="email" placeholder="Email" aria-label="Contact email" />
        </div>
        <SendInput name="org" placeholder="Company (optional)" aria-label="Contact company" />
        <SendButton sending={sending} disabled={!to.trim()} onClick={() => void submit()} />
      </div>
    </Form>
  );
}

function ReactionForm({ gateway, to, run, sending, setError }: FormProps) {
  const form = useForm<ReactionValues>({ resolver: zodResolver(reactionSchema), defaultValues: { messageId: '', emoji: '', remove: false } });
  const send = (remove: boolean) => {
    form.setValue('remove', remove);
    void form.handleSubmit(({ messageId, emoji, remove }) => {
      setError(null);
      void run(() => sendReactionMessage(gateway, to, messageId, emoji, remove), remove ? 'Reaction removed' : 'Reaction sent', () => form.setValue('emoji', ''));
    })();
  };
  return (
    <Form {...form}>
      <div className="space-y-2">
        <SendInput name="messageId" placeholder="Message ID (shown in message details)" className="font-mono" aria-label="Message ID" />
        <SendInput name="emoji" placeholder="Emoji" itemClassName="w-24" aria-label="Emoji" />
        <div className="flex gap-2">
          <SendButton sending={sending} disabled={!to.trim()} onClick={() => send(false)} />
          <Button size="sm" variant="outline" disabled={sending || !to.trim()} onClick={() => send(true)}>Remove reaction</Button>
        </div>
      </div>
    </Form>
  );
}

const INTERACTIVE_DEFAULTS = (): InteractiveValues => ({
  header: '', body: '', footer: '', buttonText: '', displayText: '', url: '',
  buttons: [{ id: 'btn_1', title: '' }],
  rows: [{ title: '', description: '' }],
});

function InteractiveForm({ kind, gateway, to, run, sending, setError }: FormProps & { kind: InteractiveKind }) {
  const schema = useMemo(() => interactiveSchema(kind), [kind]);
  const form = useForm<InteractiveValues>({ resolver: zodResolver(schema), defaultValues: INTERACTIVE_DEFAULTS() });
  // keyName: the buttons carry their own `id` field, which must not be overwritten.
  const buttons = useFieldArray({ control: form.control, name: 'buttons', keyName: '_key' });
  const rows = useFieldArray({ control: form.control, name: 'rows', keyName: '_key' });

  const submit = form.handleSubmit((v) => {
    setError(null);
    const msg = {
      kind, body: v.body, header: v.header, footer: v.footer, buttonText: v.buttonText, displayText: v.displayText, url: v.url,
      buttons: v.buttons,
      sections: [{ title: 'Options', rows: v.rows.map((r, i) => ({ id: `row_${i + 1}`, title: r.title, description: r.description.trim() || undefined })) }],
    };
    void run(() => sendInteractiveMessage(gateway, to, msg), 'Message sent', () => form.reset(INTERACTIVE_DEFAULTS()));
  });
  const arrayError = (name: 'buttons' | 'rows') => {
    const e = form.formState.errors[name];
    return e?.root?.message ?? e?.message;
  };
  return (
    <Form {...form}>
      <div className="space-y-2">
        <SendInput name="header" placeholder="Header (optional)" maxLength={60} aria-label="Header" />
        <SendTextarea name="body" placeholder="Message text" aria-label="Interactive message text" rows={2} />
        {kind === 'buttons' && (
          <div className="space-y-1.5">
            {buttons.fields.map((b, i) => (
              <div key={b._key} className="flex items-start gap-2">
                <SendInput name={`buttons.${i}.title`} itemClassName="flex-1" maxLength={INTERACTIVE_LIMITS.buttonTitle} placeholder={`Button ${i + 1}`} aria-label={`Button ${i + 1} label`} />
                {buttons.fields.length > 1 && (
                  <Button size="icon" variant="ghost" aria-label={`Remove button ${i + 1}`} onClick={() => buttons.remove(i)}><Trash2 className="h-4 w-4" /></Button>
                )}
              </div>
            ))}
            {arrayError('buttons') && <p role="alert" className="text-micro text-destructive">{arrayError('buttons')}</p>}
            {buttons.fields.length < INTERACTIVE_LIMITS.buttons && (
              <Button size="sm" variant="outline" onClick={() => buttons.append({ id: `btn_${Date.now()}`, title: '' })}><Plus className="mr-1 h-3.5 w-3.5" />Add button</Button>
            )}
          </div>
        )}
        {kind === 'list' && (
          <div className="space-y-1.5">
            <SendInput name="buttonText" maxLength={INTERACTIVE_LIMITS.ctaText} placeholder="Menu button label, for example Choose" aria-label="List button label" />
            {rows.fields.map((r, i) => (
              <div key={r._key} className="flex items-start gap-2">
                <SendInput name={`rows.${i}.title`} itemClassName="flex-1" maxLength={INTERACTIVE_LIMITS.rowTitle} placeholder={`Item ${i + 1}`} aria-label={`Item ${i + 1} title`} />
                <SendInput name={`rows.${i}.description`} itemClassName="flex-1" maxLength={72} placeholder="Description (optional)" aria-label={`Item ${i + 1} description`} />
                {rows.fields.length > 1 && (
                  <Button size="icon" variant="ghost" aria-label={`Remove item ${i + 1}`} onClick={() => rows.remove(i)}><Trash2 className="h-4 w-4" /></Button>
                )}
              </div>
            ))}
            {arrayError('rows') && <p role="alert" className="text-micro text-destructive">{arrayError('rows')}</p>}
            {rows.fields.length < INTERACTIVE_LIMITS.listRows && (
              <Button size="sm" variant="outline" onClick={() => rows.append({ title: '', description: '' })}><Plus className="mr-1 h-3.5 w-3.5" />Add item</Button>
            )}
          </div>
        )}
        {kind === 'cta_url' && (
          <div className="grid grid-cols-2 items-start gap-2">
            <SendInput name="displayText" maxLength={INTERACTIVE_LIMITS.ctaText} placeholder="Button label" aria-label="Link button label" />
            <SendInput name="url" placeholder="https://..." aria-label="Link address" />
          </div>
        )}
        <SendInput name="footer" placeholder="Footer (optional)" maxLength={60} aria-label="Footer" />
        <SendButton sending={sending} disabled={!to.trim()} onClick={() => void submit()} />
      </div>
    </Form>
  );
}

/** Wrap in a labelled `Field` (SendPanel does): `id` lets the visible label target the trigger. */
export function SendTypePicker({ value, onChange, id }: { value: SendType; onChange: (v: SendType) => void; id?: string }) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as SendType)}>
      <SelectTrigger id={id} className="w-full" aria-label="Message type"><SelectValue /></SelectTrigger>
      <SelectContent>{SEND_TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
    </Select>
  );
}

export function SendForm({ type, ...props }: FormProps & { type: SendType }) {
  if (type === 'text') return <TextForm {...props} />;
  if (type === 'template') return <TemplateSend gateway={props.gateway} to={props.to} />;
  if (MEDIA_TYPES.includes(type)) return <MediaForm key={type} kind={type as MediaKind} {...props} />;
  if (type === 'sticker') return <MediaForm kind="sticker" {...props} />;
  if (type === 'location') return <LocationForm {...props} />;
  if (type === 'contact') return <ContactForm {...props} />;
  if (type === 'reaction') return <ReactionForm {...props} />;
  return <InteractiveForm key={type} kind={type as InteractiveKind} {...props} />;
}
