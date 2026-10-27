import { useRef, useState } from 'react';
import { ChevronDown, Loader2, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Field, FieldRow } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import type { GatewayDoc } from '@/services/gatewayApi';
import { uploadPublicFile } from '@/services/whatsappApi';
import { cn } from '@/lib/utils';

interface WhatsAppChannelSettingsProps {
  gateway: GatewayDoc;
  onChange: (patch: Partial<GatewayDoc>) => void;
}

const toInt = (value: string): number | undefined => (value === '' ? undefined : Number(value));
const flag = (on: boolean): 0 | 1 => (on ? 1 : 0);

function Section({
  title,
  description,
  defaultOpen = false,
  children,
}: {
  title: string;
  description: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-lg border">
      <CollapsibleTrigger className="flex w-full items-start justify-between gap-3 p-4 text-left">
        <div className="space-y-0.5">
          <p className="text-sm font-medium">{title}</p>
          <p className="text-xs text-muted-foreground">{description}</p>
        </div>
        <ChevronDown className={cn('mt-0.5 h-4 w-4 shrink-0 transition-transform', open && 'rotate-180')} />
      </CollapsibleTrigger>
      <CollapsibleContent className="grid gap-3 border-t p-4">{children}</CollapsibleContent>
    </Collapsible>
  );
}

function SwitchRow({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <Field label={label} hint={hint} size="sm">
      {(fp) => (
        <div className="flex h-control-md items-center">
          <Switch {...fp} checked={checked} onCheckedChange={onChange} />
        </div>
      )}
    </Field>
  );
}

function AudioField({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  value?: string;
  onChange: (url: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const pick = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    const result = await uploadPublicFile(file);
    setUploading(false);
    if ('fileUrl' in result) onChange(result.fileUrl);
    else toast.error(result.message || 'Upload failed');
  };
  return (
    <Field label={label} hint={hint} size="sm">
      <div className="flex items-center gap-2">
        <Input value={value || ''} readOnly placeholder="No audio yet" className="min-w-0 flex-1 text-xs" />
        <Input
          ref={input}
          type="file"
          accept="audio/ogg,audio/opus,.ogg,.opus"
          className="hidden"
          onChange={(e) => void pick(e.target.files?.[0])}
        />
        <Button type="button" variant="outline" size="sm" disabled={uploading} onClick={() => input.current?.click()}>
          {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
          Upload
        </Button>
        {value && (
          <Button type="button" variant="ghost" size="sm" onClick={() => onChange('')}>
            Remove
          </Button>
        )}
      </div>
    </Field>
  );
}

/** WhatsApp-only gateway settings, grouped so the defaults stay out of the way until needed. */
export function WhatsAppChannelSettings({ gateway, onChange }: WhatsAppChannelSettingsProps) {
  return (
    <div className="grid gap-3">
      <Section title="Opt-out and limits" description="STOP and START keywords, and how often one person can message.">
        <FieldRow cols={2}>
          <Field label="Opt-out keywords" hint="One per line. A message that is just one of these unsubscribes the sender." size="sm">
            <Textarea
              rows={4}
              value={gateway.opt_out_keywords || ''}
              onChange={(e) => onChange({ opt_out_keywords: e.target.value })}
            />
          </Field>
          <Field label="Opt-in keywords" hint="One per line. Lets someone who opted out back in." size="sm">
            <Textarea
              rows={4}
              value={gateway.opt_in_keywords || ''}
              onChange={(e) => onChange({ opt_in_keywords: e.target.value })}
            />
          </Field>
        </FieldRow>
        <Field label="Opt-out confirmation" hint="Sent once when someone opts out." size="sm">
          <Textarea
            rows={2}
            value={gateway.opt_out_reply_text || ''}
            onChange={(e) => onChange({ opt_out_reply_text: e.target.value })}
          />
        </Field>
        <Field
          label="Messages per person (every 10 minutes)"
          hint="Extra messages are ignored. 0 turns the limit off."
          size="sm"
        >
          <Input
            type="number"
            min={0}
            value={gateway.inbound_sender_limit ?? 20}
            onChange={(e) => onChange({ inbound_sender_limit: toInt(e.target.value) })}
          />
        </Field>
      </Section>

      <Section title="Replies" description="How the agent's answers look and what happens when sending fails.">
        <SwitchRow
          label="Typing indicator"
          hint="Mark the message as read and show typing while the agent works."
          checked={Boolean(gateway.typing_indicator ?? 1)}
          onChange={(on) => onChange({ typing_indicator: flag(on) })}
        />
        <FieldRow cols={2}>
          <Field label="Voice note replies" hint="Answer a voice note with a voice note. Long or failed ones go out as text." size="sm">
            {(fp) => (
              <Select
                value={gateway.voice_reply_mode || 'Off'}
                onValueChange={(v) => onChange({ voice_reply_mode: v as GatewayDoc['voice_reply_mode'] })}
              >
                <SelectTrigger {...fp}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Off">Off</SelectItem>
                  <SelectItem value="Voice only">Voice only</SelectItem>
                  <SelectItem value="Text and voice">Text and voice</SelectItem>
                </SelectContent>
              </Select>
            )}
          </Field>
          <Field label="Link previews" hint="Show a preview card for links in replies." size="sm">
            {(fp) => (
              <Select
                value={gateway.preview_url || 'Default (off)'}
                onValueChange={(v) => onChange({ preview_url: v as GatewayDoc['preview_url'] })}
              >
                <SelectTrigger {...fp}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Default (off)">Default (off)</SelectItem>
                  <SelectItem value="On">On</SelectItem>
                  <SelectItem value="Off">Off</SelectItem>
                </SelectContent>
              </Select>
            )}
          </Field>
        </FieldRow>
        <Field
          label="Message when the agent fails"
          hint="Sent to the customer when the agent can't answer (at most once every 10 minutes). Leave empty to send nothing."
          size="sm"
        >
          <Textarea
            rows={2}
            value={gateway.error_reply_text || ''}
            onChange={(e) => onChange({ error_reply_text: e.target.value })}
          />
        </Field>
        <Field label="Send attempts" hint="Retries for a reply that hits a temporary WhatsApp error." size="sm">
          <Input
            type="number"
            min={1}
            value={gateway.retry_max_attempts ?? 4}
            onChange={(e) => onChange({ retry_max_attempts: toInt(e.target.value) })}
          />
        </Field>
        <div className="grid gap-3 rounded-md border p-3">
          <p className="text-xs text-muted-foreground">
            After 24 hours without a message from the customer, WhatsApp only allows an approved template. This
            one is sent instead of the agent&apos;s reply.
          </p>
          <FieldRow cols={2}>
            <Field label="Fallback template" size="sm">
              <Input
                value={gateway.fallback_template || ''}
                placeholder="e.g. follow_up"
                onChange={(e) => onChange({ fallback_template: e.target.value })}
              />
            </Field>
            <Field label="Template language" size="sm">
              <Input
                value={gateway.fallback_template_language || ''}
                placeholder="en_US"
                onChange={(e) => onChange({ fallback_template_language: e.target.value })}
              />
            </Field>
          </FieldRow>
          <Field
            label="Template values"
            hint='Optional. A list like ["{{contact_name}}", "Acme"] for the template&apos;s variables. {{contact_name}} becomes the customer&apos;s name.'
            size="sm"
          >
            <Input
              value={gateway.fallback_template_params || ''}
              onChange={(e) => onChange({ fallback_template_params: e.target.value })}
              className="font-mono text-xs"
            />
          </Field>
        </div>
      </Section>

      <Section
        title="What the agent may send"
        description="Who the agent can message on its own, how much, and whether it can draft templates."
      >
        <SwitchRow
          label="Send after the 24-hour window"
          hint="Let the agent send free-form messages to people who haven't written in the last 24 hours."
          checked={Boolean(gateway.agent_allow_proactive)}
          onChange={(on) => onChange({ agent_allow_proactive: flag(on) })}
        />
        <Field label="Who the agent may message" size="sm">
          {(fp) => (
            <Select
              value={gateway.agent_recipient_scope || 'Current contact'}
              onValueChange={(v) => onChange({ agent_recipient_scope: v as GatewayDoc['agent_recipient_scope'] })}
            >
              <SelectTrigger {...fp}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="Current contact">Only the person it's talking to</SelectItem>
                <SelectItem value="Allow-list">Also the numbers listed below</SelectItem>
                <SelectItem value="Approved contacts">Also anyone approved on this channel</SelectItem>
                <SelectItem value="Any number">Any number (trusted agents only)</SelectItem>
              </SelectContent>
            </Select>
          )}
        </Field>
        {gateway.agent_recipient_scope === 'Allow-list' && (
          <Field label="Allowed numbers" hint="One per line, with country code." size="sm">
            <Textarea
              rows={3}
              value={gateway.agent_recipient_allowlist || ''}
              onChange={(e) => onChange({ agent_recipient_allowlist: e.target.value })}
            />
          </Field>
        )}
        <FieldRow cols={2}>
          <Field label="Messages per run" hint="0 means no limit." size="sm">
            <Input
              type="number"
              min={0}
              value={gateway.agent_send_cap_per_run ?? 20}
              onChange={(e) => onChange({ agent_send_cap_per_run: toInt(e.target.value) })}
            />
          </Field>
          <Field label="Messages per day" hint="0 means no limit." size="sm">
            <Input
              type="number"
              min={0}
              value={gateway.agent_send_cap_per_day ?? 200}
              onChange={(e) => onChange({ agent_send_cap_per_day: toInt(e.target.value) })}
            />
          </Field>
        </FieldRow>
        <SwitchRow
          label="Agent may draft templates"
          hint="Drafts wait for a person to approve them before they reach Meta."
          checked={Boolean(gateway.agent_allow_template_management)}
          onChange={(on) =>
            onChange({
              agent_allow_template_management: flag(on),
              ...(on ? {} : { agent_auto_submit_templates: 0 }),
            })
          }
        />
        {Boolean(gateway.agent_allow_template_management) && (
          <SwitchRow
            label="Submit agent templates without approval"
            hint="Templates the agent writes go straight to Meta."
            checked={Boolean(gateway.agent_auto_submit_templates)}
            onChange={(on) => onChange({ agent_auto_submit_templates: flag(on) })}
          />
        )}
      </Section>

      <Section title="Calls" description="Answer WhatsApp calls from approved people with recorded audio.">
        <SwitchRow
          label="Answer calls"
          hint="Unknown callers are always declined. Only approved people are answered."
          checked={Boolean(gateway.calling_enabled)}
          onChange={(on) => onChange({ calling_enabled: flag(on) })}
        />
        {Boolean(gateway.calling_enabled) && (
          <>
            <AudioField
              label="Greeting"
              hint="Ogg/Opus, under 60 seconds. Start by saying the caller is talking to an automated assistant."
              value={gateway.call_greeting_audio}
              onChange={(url) => onChange({ call_greeting_audio: url })}
            />
            <AudioField
              label="Reply (optional)"
              value={gateway.call_reply_audio}
              onChange={(url) => onChange({ call_reply_audio: url })}
            />
            <AudioField
              label="Closing (optional)"
              value={gateway.call_closing_audio}
              onChange={(url) => onChange({ call_closing_audio: url })}
            />
            <Field label="Longest call (seconds)" size="sm">
              <Input
                type="number"
                min={1}
                value={gateway.call_max_seconds ?? 60}
                onChange={(e) => onChange({ call_max_seconds: toInt(e.target.value) })}
              />
            </Field>
          </>
        )}
      </Section>

      <Section title="Solutions routing" description="How long a conversation stays with the solution it was routed to.">
        <Field label="Keep a conversation with its solution for (hours)" size="sm">
          <Input
            type="number"
            min={0}
            value={gateway.pin_ttl_hours ?? 24}
            onChange={(e) => onChange({ pin_ttl_hours: toInt(e.target.value) })}
          />
        </Field>
        <SwitchRow
          label="Keywords switch solutions"
          hint="A message matching another solution's keyword moves the conversation there."
          checked={Boolean(gateway.keyword_beats_pin)}
          onChange={(on) => onChange({ keyword_beats_pin: flag(on) })}
        />
      </Section>
    </div>
  );
}
