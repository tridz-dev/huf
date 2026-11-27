import { useFlowPermissions } from '@/hooks/flow/useFlowPermissions';
import { useGatewayRegistry } from '@/hooks/flow/useGatewayRegistry';
import { SEND_CATEGORIES, SEND_PROVIDERS } from '@/lib/flow-send/sendMessage';
import { Combobox } from '../../ui/combobox';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../ui/select';
import { FieldHint } from '../FieldHint';
import { ListRows, ValueField } from './fields';
import { type ActionFormProps, Section, str } from './formKit';

/**
 * Send message: one WhatsApp message to the person the run is about. Every send passes the guard chain (consent,
 * window, caps) first; a blocked send is final and its reason shows in the run.
 */
export function SendMessageForm({ nodeId, cfg, patch, f, Err, title }: ActionFormProps) {
  const { canManage } = useFlowPermissions();
  const { registry, failed } = useGatewayRegistry(canManage);
  const gateway = str(cfg.gateway);
  const options = (registry?.gateways ?? [])
    .filter((g) => SEND_PROVIDERS.includes(g.provider.toLowerCase()))
    .map((g) => ({ value: g.name, label: g.label || g.name }));
  const usesText = cfg.text !== undefined && cfg.template === undefined;
  const setMode = (mode: string) =>
    patch(mode === 'text' ? { template: undefined, variables: undefined, text: str(cfg.text) } : { text: undefined, template: str(cfg.template) });
  const disabled = !canManage;

  return (
    <Section title={title} hint="Sends one message to the person this run is about. It is checked first and is not sent when a rule blocks it.">
      <div>
        <Label htmlFor="send-message-gateway" size="sm">Send from</Label>
        <Combobox
          id="send-message-gateway"
          testId={f('gateway')}
          options={gateway && !options.some((o) => o.value === gateway) ? [{ value: gateway, label: gateway }, ...options] : options}
          value={gateway}
          disabled={disabled || (!registry && !failed)}
          onValueChange={(v) => v && patch({ gateway: v })}
          placeholder={registry || failed ? 'Choose a WhatsApp number...' : 'Loading...'}
          searchPlaceholder="Search numbers..."
          emptyText={failed ? 'Could not load your channels. Try again.' : 'No WhatsApp number is connected yet.'}
        />
        <Err field="gateway" />
      </div>
      <div>
        <Label size="sm">Send to</Label>
        <ValueField field="recipient" f={f} Err={Err} nodeId={nodeId} label="Phone number" placeholder="The person's phone number" value={cfg.recipient} onChange={(v) => patch({ recipient: v })} />
      </div>
      <div>
        <Label htmlFor="send-message-category" size="sm">Kind of message</Label>
        <Select value={str(cfg.category)} disabled={disabled} onValueChange={(v) => patch({ category: v })}>
          <SelectTrigger id="send-message-category" data-testid={f('category')}><SelectValue placeholder="Choose..." /></SelectTrigger>
          <SelectContent>
            {SEND_CATEGORIES.map((c) => <SelectItem key={c.value} value={c.value}>{c.label}</SelectItem>)}
          </SelectContent>
        </Select>
        <FieldHint testId="flow-hint-send-message-category">Marketing messages need the person's consent and follow quiet hours and limits.</FieldHint>
        <Err field="category" />
      </div>
      <div>
        <Label htmlFor="send-message-mode" size="sm">Message</Label>
        <Select value={usesText ? 'text' : 'template'} disabled={disabled} onValueChange={setMode}>
          <SelectTrigger id="send-message-mode" data-testid={f('mode')}><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="template">An approved template</SelectItem>
            <SelectItem value="text">A text</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {usesText ? (
        <ValueField field="text" f={f} Err={Err} nodeId={nodeId} label="Text" placeholder="Write the message" value={cfg.text} onChange={(v) => patch({ text: v })} />
      ) : (
        <>
          <ValueField field="template" f={f} Err={Err} nodeId={nodeId} label="Template" placeholder="Template name" value={cfg.template} onChange={(v) => patch({ template: v })} />
          <div>
            <Label size="sm">Template variables</Label>
            <ListRows testId={f('variables')} nodeId={nodeId} disabled={disabled} itemLabel="Variable" placeholder="Token name" addLabel="Add a variable" value={cfg.variables} onChange={(v) => patch({ variables: v })} />
            <FieldHint testId="flow-hint-send-message-variables">Filled in for each person at send time. Their values never appear in the run.</FieldHint>
            <Err field="variables" />
          </div>
        </>
      )}
      <div>
        <Label htmlFor="send-message-language" size="sm">Language (optional)</Label>
        <Input id="send-message-language" data-testid={f('language')} disabled={disabled} value={str(cfg.language)} placeholder="en" onChange={(e) => patch({ language: e.target.value.trim() ? e.target.value : undefined })} />
      </div>
    </Section>
  );
}
