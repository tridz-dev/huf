import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { useUser } from '@/contexts/UserContext';
import {
  confirmSelfLink,
  describeLinkError,
  parseLinkProvider,
  parseLinkToken,
  providerName,
  previewSelfLink,
  type SelfLinkPreview,
} from '@/services/linkAccountApi';

type Status = 'loading' | 'ready' | 'confirming' | 'done' | 'error';

export function LinkAccountPage() {
  const { search } = useLocation();
  const { user } = useUser();
  const token = useMemo(() => parseLinkToken(search), [search]);
  const provider = useMemo(() => parseLinkProvider(search), [search]);
  const app = providerName(provider);
  const person = provider === 'teams' ? 'Teams person' : 'Slack person';
  const orgLabel = provider === 'teams' ? 'Organisation (tenant)' : 'Workspace';
  const [status, setStatus] = useState<Status>(token ? 'loading' : 'error');
  const [preview, setPreview] = useState<SelfLinkPreview | null>(null);
  const [error, setError] = useState<string | null>(
    token ? null : `This link is missing or incomplete. Ask Huf for a new one in ${app}.`,
  );
  const [acknowledged, setAcknowledged] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    previewSelfLink(token, provider)
      .then((result) => {
        if (cancelled) return;
        setPreview(result);
        setStatus('ready');
      })
      .catch((err) => {
        if (cancelled) return;
        setError(describeLinkError(err, provider));
        setStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [token, provider]);

  const handleConfirm = async () => {
    if (!token || !acknowledged) return;
    setStatus('confirming');
    try {
      await confirmSelfLink(token, provider);
      setStatus('done');
    } catch (err) {
      setError(describeLinkError(err, provider));
      setStatus('error');
    }
  };

  const hufAccount = user?.full_name || preview?.user || '';
  const hufEmail = user?.email || preview?.user || '';

  return (
    <div className="flex min-h-full items-center justify-center p-4">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>Connect this {app} account to your Huf account</CardTitle>
          <CardDescription>Linking lets Huf know which Huf user is behind your {app} messages.</CardDescription>
        </CardHeader>

        {status === 'loading' && (
          <CardContent className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading link details...
          </CardContent>
        )}

        {status === 'error' && (
          <CardContent>
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Could not link this account</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          </CardContent>
        )}

        {status === 'done' && (
          <CardContent>
            <Alert>
              <CheckCircle2 className="h-4 w-4" />
              <AlertTitle>{app === 'Slack' ? 'Check Slack to finish' : 'Account connected'}</AlertTitle>
              <AlertDescription>
                {app === 'Slack' ? (
                  <>
                    We sent a confirmation message to that Slack user. The link to {hufAccount} only becomes active
                    after they choose "Yes, link it" in Slack. You can close this page.
                  </>
                ) : (
                  <>
                    Your {app} account is now connected to {hufAccount}. You can close this page and go back to
                    {app}.
                  </>
                )}
              </AlertDescription>
            </Alert>
          </CardContent>
        )}

        {(status === 'ready' || status === 'confirming') && preview && (
          <>
            <CardContent className="space-y-4">
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                {app === 'Slack' ? (
                  <>
                    <dt className="text-muted-foreground">Slack user ID</dt>
                    <dd className="font-medium break-all">{preview.external_id}</dd>
                    <dt className="text-muted-foreground">Slack workspace</dt>
                    <dd className="font-medium break-all">
                      {preview.team_id} ({preview.workspace_label})
                    </dd>
                    <dt className="text-muted-foreground">Display name (set by that person)</dt>
                    <dd className="text-muted-foreground break-all">{preview.slack_label}</dd>
                  </>
                ) : (
                  <>
                    <dt className="text-muted-foreground">{person}</dt>
                    <dd className="font-medium break-all">{preview.person_label}</dd>
                    <dt className="text-muted-foreground">{orgLabel}</dt>
                    <dd className="font-medium break-all">{preview.workspace_label}</dd>
                  </>
                )}
                <dt className="text-muted-foreground">Huf account</dt>
                <dd className="font-medium break-all">
                  {hufAccount}
                  {hufEmail && hufEmail !== hufAccount ? ` (${hufEmail})` : ''}
                </dd>
              </dl>
              <p className="text-sm text-muted-foreground">
                {app === 'Slack'
                  ? `Slack user ${preview.external_id} will act as YOU in Huf: anything that Slack account asks Huf to do will run with your Huf permissions. The display name above is chosen by that person and proves nothing.`
                  : `Once linked, anything this ${app} account asks Huf to do will run with your Huf permissions.`}
              </p>
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Check before you continue</AlertTitle>
                <AlertDescription>
                  Only continue if you asked Huf for this link from your own {app} account. If someone else sent
                  it to you, close this page.
                </AlertDescription>
              </Alert>
              <div className="flex items-start gap-2">
                <Checkbox
                  id="link-account-ack"
                  checked={acknowledged}
                  onCheckedChange={(value) => setAcknowledged(value === true)}
                  disabled={status === 'confirming'}
                />
                <Label htmlFor="link-account-ack" className="text-sm font-normal leading-snug">
                  I asked for this link from my own {app} account, and I want to connect it to my Huf account.
                </Label>
              </div>
            </CardContent>
            <CardFooter>
              <Button onClick={handleConfirm} disabled={!acknowledged || status === 'confirming'}>
                {status === 'confirming' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Connect account
              </Button>
            </CardFooter>
          </>
        )}
      </Card>
    </div>
  );
}
