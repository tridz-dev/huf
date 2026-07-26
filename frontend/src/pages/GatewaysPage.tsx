import { FormEvent, useEffect, useState } from 'react';
import { Link2, Mail, MessageCircle, Send, Settings, ShieldCheck, Slack } from 'lucide-react';
import { PageLayout, GridView, ItemCard } from '@/components/dashboard';
import { getGateways, type GatewayDoc } from '@/services/gatewayApi';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { Button } from '@/components/ui/button';

const providerIcons = {
  Telegram: Send,
  Slack,
  Email: Mail,
  WhatsApp: MessageCircle,
} as const;

const providerNames = {
  Telegram: 'Telegram bot',
  Slack: 'Slack workspace',
  Email: 'Shared inbox',
  WhatsApp: 'WhatsApp business number',
} as const;

export default function GatewaysPage() {
  const [gateways, setGateways] = useState<GatewayDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showSetup, setShowSetup] = useState(false);
  const [creating, setCreating] = useState(false);
  const [gatewayName, setGatewayName] = useState('');
  const [provider, setProvider] = useState<GatewayDoc['provider']>('Telegram');

  useEffect(() => {
    getGateways()
      .then(setGateways)
      .catch(() => setError('Could not load gateways.'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <PageLayout subtitle="Let people reach Huf from the channels they already use — safely and with clear routing.">
      <div className="mb-6 rounded-lg border border-line bg-panel p-5">
        <div className="flex gap-3">
          <div className="rounded-md bg-primary/10 p-2 h-fit"><Link2 className="h-5 w-5 text-primary" /></div>
          <div className="space-y-2">
            <h1 className="text-lg font-semibold">What is a gateway?</h1>
            <p className="max-w-3xl text-sm text-steel">
              A gateway is a safe front door from Telegram, Slack, email, or WhatsApp into Huf.
              It decides who can ask for help and which Agent or Flow should respond. It is different
              from an integration tool: tools let an Agent send messages; gateways let people start work.
            </p>
            <div className="flex items-center gap-2 text-sm text-steel">
              <ShieldCheck className="h-4 w-4 text-primary" />
              New gateways deny unknown senders until you choose an access policy and route.
            </div>
          </div>
        </div>
      </div>

      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold">Your gateways</h2>
          <p className="text-sm text-steel">Create a safe draft first. It will not receive messages until you finish routing and enable it.</p>
        </div>
        <Button size="sm" onClick={() => setShowSetup((value) => !value)}>
          {showSetup ? 'Cancel' : 'Add gateway'}
        </Button>
      </div>

      {showSetup && (
        <form
          className="mb-6 grid gap-4 rounded-lg border border-line bg-panel p-5 md:grid-cols-[1fr_220px_auto] md:items-end"
          onSubmit={async (event: FormEvent) => {
            event.preventDefault();
            if (!gatewayName.trim()) return;
            setCreating(true);
            setError('');
            try {
              const created = await db.createDoc(doctype.Gateway, {
                gateway_name: gatewayName.trim(),
                provider,
                is_enabled: 0,
                access_policy: 'Deny by default',
              }) as GatewayDoc;
              setGateways((current) => [created, ...current]);
              setGatewayName('');
              setShowSetup(false);
            } catch {
              setError('Could not create the gateway. Choose a different name and try again.');
            } finally {
              setCreating(false);
            }
          }}
        >
          <label className="grid gap-1 text-sm font-medium">
            Give it a clear name
            <input
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={gatewayName}
              onChange={(event) => setGatewayName(event.target.value)}
              placeholder="Customer support on Telegram"
              required
            />
          </label>
          <label className="grid gap-1 text-sm font-medium">
            Where people will message you
            <select
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={provider}
              onChange={(event) => setProvider(event.target.value as GatewayDoc['provider'])}
            >
              <option value="Telegram">Telegram</option>
              <option value="Slack">Slack</option>
              <option value="Email">Email</option>
              <option value="WhatsApp">WhatsApp</option>
            </select>
          </label>
          <Button type="submit" disabled={creating}>{creating ? 'Creating…' : 'Create safe draft'}</Button>
        </form>
      )}

      {error && <p className="mb-4 text-sm text-destructive">{error}</p>}
      <GridView
        items={gateways}
        loading={loading}
        columns={{ sm: 1, md: 2, lg: 3 }}
        emptyState={
          <div className="max-w-xl py-10 text-center">
            <p className="mb-2 font-medium">No gateways yet.</p>
            <p className="text-sm text-steel">
              Start with Telegram or Slack for a conversational assistant, email for an inbox workflow,
              or WhatsApp when your customers already use it. Add a safe draft above; it will stay off
              until you connect the provider and choose where messages should go.
            </p>
          </div>
        }
        renderItem={(gateway) => {
          const Icon = providerIcons[gateway.provider];
          const target = gateway.default_target_type === 'Agent'
            ? gateway.default_agent
            : gateway.default_target_type === 'Flow' ? gateway.default_flow : 'No default route';
          return (
            <ItemCard
              title={gateway.gateway_name}
              description={gateway.description || providerNames[gateway.provider]}
              status={{
                label: gateway.is_enabled ? 'ready' : 'not receiving messages',
                variant: gateway.is_enabled ? 'default' : 'secondary',
              }}
              metadata={[
                { label: 'Channel', value: gateway.provider, icon: Icon },
                { label: 'Access', value: gateway.access_policy },
                { label: 'Default route', value: target || 'No default route' },
              ]}
              actions={[
                {
                  icon: Settings,
                  label: 'Finish setup in Desk',
                  onClick: () => { window.location.href = `/app/gateway/${encodeURIComponent(gateway.name)}`; },
                },
              ]}
            />
          );
        }}
        keyExtractor={(gateway) => gateway.name}
      />
    </PageLayout>
  );
}
