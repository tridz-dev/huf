import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Loader2, RefreshCw } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import {
  listSlackLinks,
  linkSlackUser,
  unlinkSlackUser,
  type SlackIdentityLink,
} from '@/services/gateways/slackIdentityApi';
import { registerProviderPanel, type ProviderPanelProps } from './index';

const errorText = (e: unknown, fallback: string) => (e instanceof Error && e.message ? e.message : fallback);

export function SlackPeoplePanel({ gateway }: ProviderPanelProps) {
  const [links, setLinks] = useState<SlackIdentityLink[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [teamId, setTeamId] = useState('');
  const [slackId, setSlackId] = useState('');
  const [user, setUser] = useState('');
  const [linking, setLinking] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setLinks(await listSlackLinks(gateway.name));
    } catch (e) {
      setError(errorText(e, 'Could not load linked people'));
    } finally {
      setLoading(false);
    }
  }, [gateway.name]);

  useEffect(() => {
    void load();
  }, [load]);

  const canLink = teamId.trim().length > 0 && slackId.trim().length > 0 && user.trim().length > 0;

  const link = useCallback(async () => {
    setLinking(true);
    setFormError(null);
    try {
      await linkSlackUser(gateway.name, teamId, slackId, user);
      toast.success('Person linked');
      setSlackId('');
      setUser('');
      await load();
    } catch (e) {
      setFormError(errorText(e, 'Could not link this person'));
    } finally {
      setLinking(false);
    }
  }, [gateway.name, teamId, slackId, user, load]);

  const revoke = useCallback(
    async (name: string) => {
      setRevoking(name);
      try {
        await unlinkSlackUser(name);
        toast.success('Link removed');
        await load();
      } catch (e) {
        toast.error(errorText(e, 'Could not remove the link'));
      } finally {
        setRevoking(null);
      }
    },
    [load]
  );

  return (
    <div className="space-y-5">
      <section className="space-y-2">
        <p className="text-sm font-medium">Link a person</p>
        <p className="text-sm text-muted-foreground">
          People normally link themselves from Slack. As an admin you can link someone directly using their Slack
          workspace ID, Slack user ID and their Huf user.
        </p>
        <div className="grid gap-2 sm:grid-cols-3">
          <div className="space-y-1">
            <Label htmlFor="slack-link-team">Workspace ID</Label>
            <Input
              id="slack-link-team"
              placeholder="T0123ABCD"
              value={teamId}
              onChange={(e) => setTeamId(e.target.value)}
              disabled={linking}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="slack-link-user">Slack user ID</Label>
            <Input
              id="slack-link-user"
              placeholder="U0123ABCD"
              value={slackId}
              onChange={(e) => setSlackId(e.target.value)}
              disabled={linking}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="slack-link-huf">Huf user (email)</Label>
            <Input
              id="slack-link-huf"
              placeholder="you@company.com"
              value={user}
              onChange={(e) => setUser(e.target.value)}
              disabled={linking}
            />
          </div>
        </div>
        <Button type="button" size="sm" onClick={link} disabled={linking || !canLink}>
          {linking && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
          Link person
        </Button>
        {formError && <p className="text-sm text-destructive">{formError}</p>}
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-medium">Linked people</p>
          <Button type="button" size="sm" variant="ghost" onClick={load} disabled={loading}>
            <RefreshCw className="mr-1 h-3.5 w-3.5" /> Refresh
          </Button>
        </div>
        {error && (
          <Alert variant="destructive">
            <AlertDescription className="flex flex-wrap items-center gap-2">
              {error}
              <Button type="button" size="sm" variant="outline" onClick={load}>
                Retry
              </Button>
            </AlertDescription>
          </Alert>
        )}
        {loading && !links && (
          <div className="space-y-2" aria-busy="true">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        )}
        {links && links.length === 0 && (
          <p className="text-sm text-muted-foreground">No one is linked yet.</p>
        )}
        {links && links.length > 0 && (
          <ul className="divide-y rounded-md border" aria-label="Linked people">
            {links.map((l) => (
              <li key={l.name} className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
                <div className="min-w-0 space-y-0.5">
                  <p className="break-words font-medium">{l.display_label || l.external_id}</p>
                  <p className="break-all text-muted-foreground">
                    {l.user} · {l.external_id}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">{l.state}</Badge>
                  {l.state !== 'Revoked' && (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => revoke(l.name)}
                      disabled={revoking === l.name}
                      aria-label={`Remove link for ${l.display_label || l.external_id}`}
                    >
                      {revoking === l.name && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                      Remove
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

registerProviderPanel('Slack', {
  id: 'slack-people',
  title: 'Slack people',
  component: SlackPeoplePanel,
});
