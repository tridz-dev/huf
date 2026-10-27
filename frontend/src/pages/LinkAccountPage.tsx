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
  parseLinkToken,
  previewSelfLink,
  type SelfLinkPreview,
} from '@/services/linkAccountApi';

type Status = 'loading' | 'ready' | 'confirming' | 'done' | 'error';

export function LinkAccountPage() {
  const { search } = useLocation();
  const { user } = useUser();
  const token = useMemo(() => parseLinkToken(search), [search]);
  const [status, setStatus] = useState<Status>(token ? 'loading' : 'error');
  const [preview, setPreview] = useState<SelfLinkPreview | null>(null);
  const [error, setError] = useState<string | null>(
    token ? null : 'This link is missing or incomplete. Ask Huf for a new one in Slack.',
  );
  const [acknowledged, setAcknowledged] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    previewSelfLink(token)
      .then((result) => {
        if (cancelled) return;
        setPreview(result);
        setStatus('ready');
      })
      .catch((err) => {
        if (cancelled) return;
        setError(describeLinkError(err));
        setStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const handleConfirm = async () => {
    if (!token || !acknowledged) return;
    setStatus('confirming');
    try {
      await confirmSelfLink(token);
      setStatus('done');
    } catch (err) {
      setError(describeLinkError(err));
      setStatus('error');
    }
  };

  const hufAccount = user?.full_name || preview?.user || '';
  const hufEmail = user?.email || preview?.user || '';

  return (
    <div className="flex min-h-full items-center justify-center p-4">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>Connect this Slack account to your Huf account</CardTitle>
          <CardDescription>Linking lets Huf know which Huf user is behind your Slack messages.</CardDescription>
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
              <AlertTitle>Account linked</AlertTitle>
              <AlertDescription>
                Your Slack account is now connected to {hufAccount}. You can close this page and go back to
                Slack.
              </AlertDescription>
            </Alert>
          </CardContent>
        )}

        {(status === 'ready' || status === 'confirming') && preview && (
          <>
            <CardContent className="space-y-4">
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                <dt className="text-muted-foreground">Slack person</dt>
                <dd className="font-medium break-all">{preview.slack_label}</dd>
                <dt className="text-muted-foreground">Workspace</dt>
                <dd className="font-medium break-all">{preview.workspace_label}</dd>
                <dt className="text-muted-foreground">Huf account</dt>
                <dd className="font-medium break-all">
                  {hufAccount}
                  {hufEmail && hufEmail !== hufAccount ? ` (${hufEmail})` : ''}
                </dd>
              </dl>
              <p className="text-sm text-muted-foreground">
                Once linked, anything this Slack account asks Huf to do will run with your Huf permissions.
              </p>
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Check before you continue</AlertTitle>
                <AlertDescription>
                  Only continue if you asked Huf for this link from your own Slack account. If someone else sent
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
                  I asked for this link from my own Slack account, and I want to connect it to my Huf account.
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
