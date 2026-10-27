import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { CheckCircle2, Copy, ExternalLink, Loader2, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  getSlackManifest,
  getSlackSetupStatus,
  sendSlackTestMessage,
  verifySlackSetup,
  type SlackSetupCheck,
} from '@/services/gateways/slackSetupApi';
import { registerProviderPanel, type ProviderPanelProps } from './index';

const CREATE_APP_URL = 'https://api.slack.com/apps?new_app=1';

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function CheckRow({ check }: { check: SlackSetupCheck }) {
  const Icon = check.ok ? CheckCircle2 : XCircle;
  return (
    <li className="flex gap-2 text-sm">
      <Icon
        className={`mt-0.5 h-4 w-4 shrink-0 ${check.ok ? 'text-green-600' : 'text-destructive'}`}
        aria-hidden="true"
      />
      <div className="space-y-0.5">
        <p className="font-medium">{check.plain_title}</p>
        {check.detail && <p className="text-muted-foreground">{check.detail}</p>}
        {!check.ok && check.how_to_fix && <p>{check.how_to_fix}</p>}
      </div>
    </li>
  );
}

export function SlackSetupPanel({ gateway }: ProviderPanelProps) {
  const [copying, setCopying] = useState(false);
  const [manifestError, setManifestError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [checks, setChecks] = useState<SlackSetupCheck[] | null>(null);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [slackUserId, setSlackUserId] = useState('');
  const [email, setEmail] = useState('');
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSlackSetupStatus(gateway.name)
      .then((status) => {
        if (!cancelled && status.checks.length > 0) setChecks(status.checks);
      })
      .catch(() => {
        // No earlier result to show; the admin can run the check.
      });
    return () => {
      cancelled = true;
    };
  }, [gateway.name]);

  const copyManifest = useCallback(async () => {
    setCopying(true);
    setManifestError(null);
    try {
      const manifest = await getSlackManifest(gateway.name);
      await navigator.clipboard.writeText(JSON.stringify(manifest, null, 2));
      toast.success('App manifest copied');
    } catch (error) {
      setManifestError(errorText(error, 'Could not copy the app manifest'));
    } finally {
      setCopying(false);
    }
  }, [gateway.name]);

  const verify = useCallback(async () => {
    setVerifying(true);
    setVerifyError(null);
    try {
      setChecks(await verifySlackSetup(gateway.name));
    } catch (error) {
      setVerifyError(errorText(error, 'Could not check the Slack connection'));
    } finally {
      setVerifying(false);
    }
  }, [gateway.name]);

  const sendTest = useCallback(async () => {
    setSending(true);
    setSendError(null);
    try {
      await sendSlackTestMessage(gateway.name, {
        slackUserId: slackUserId.trim(),
        email: email.trim(),
      });
      toast.success('Test message sent. Check your Slack direct messages.');
    } catch (error) {
      setSendError(errorText(error, 'Could not send the test message'));
    } finally {
      setSending(false);
    }
  }, [gateway.name, slackUserId, email]);

  const hasTarget = Boolean(slackUserId.trim()) !== Boolean(email.trim());

  return (
    <div className="space-y-5">
      <section className="space-y-2">
        <p className="text-sm font-medium">1. Create the Slack app</p>
        <p className="text-sm text-muted-foreground">
          Copy the app manifest, then create a Slack app from it. It sets up the permissions and the events address for you.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" onClick={copyManifest} disabled={copying}>
            {copying ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <Copy className="mr-1 h-3.5 w-3.5" />}
            Copy app manifest
          </Button>
          <Button type="button" size="sm" variant="ghost" asChild>
            <a href={CREATE_APP_URL} target="_blank" rel="noreferrer">
              <ExternalLink className="mr-1 h-3.5 w-3.5" /> Create app from manifest
            </a>
          </Button>
        </div>
        {manifestError && <p className="text-sm text-destructive">{manifestError}</p>}
      </section>

      <section className="space-y-1">
        <p className="text-sm font-medium">2. Add your keys</p>
        <p className="text-sm text-muted-foreground">
          Install the app to your workspace, then open the Credentials tab and paste the Bot User OAuth Token (starts
          with xoxb-) and the Signing Secret. Then, in Slack, click Save Request URL under Event Subscriptions.
        </p>
      </section>

      <section className="space-y-2">
        <p className="text-sm font-medium">3. Check the connection</p>
        <Button type="button" size="sm" onClick={verify} disabled={verifying}>
          {verifying && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
          Verify connection
        </Button>
        {verifyError && <p className="text-sm text-destructive">{verifyError}</p>}
        {checks && (
          <ul className="space-y-2" aria-label="Connection checks">
            {checks.map((check) => (
              <CheckRow key={check.id} check={check} />
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-2">
        <p className="text-sm font-medium">4. Send a test message</p>
        <p className="text-sm text-muted-foreground">
          Huf will send a direct message to one person. Enter their Slack member ID or their email.
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="slack-test-user-id">Slack member ID</Label>
            <Input
              id="slack-test-user-id"
              placeholder="U012ABCDE"
              value={slackUserId}
              onChange={(e) => setSlackUserId(e.target.value)}
              disabled={sending || Boolean(email.trim())}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="slack-test-email">Email</Label>
            <Input
              id="slack-test-email"
              type="email"
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={sending || Boolean(slackUserId.trim())}
            />
          </div>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={sendTest} disabled={sending || !hasTarget}>
          {sending && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
          Send test message to me
        </Button>
        {sendError && <p className="text-sm text-destructive">{sendError}</p>}
      </section>
    </div>
  );
}

registerProviderPanel('Slack', { id: 'slack-setup', title: 'Slack setup', component: SlackSetupPanel });
