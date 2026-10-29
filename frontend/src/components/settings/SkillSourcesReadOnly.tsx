import { useEffect, useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { getSkillDestinations, type SkillDestination } from '@/services/skillApi';

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-0.5">
      <dt className="text-meta font-medium text-muted-foreground">{label}</dt>
      <dd className="break-all text-sm">{value || <span className="italic text-muted-foreground">Not set</span>}</dd>
    </div>
  );
}

/** Where skills can be imported from, as plain text, for people who cannot change it (only a system administrator can). */
export function SkillSourcesReadOnly() {
  const [sources, setSources] = useState<SkillDestination[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getSkillDestinations()
      .then((list) => !cancelled && setSources(list))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card data-testid="settings-skill-sources">
      <CardHeader>
        <CardTitle>Skill sources</CardTitle>
        <CardDescription>
          These are the places skills can be imported from. Only a system administrator can change them.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {failed ? (
          <p className="text-sm text-muted-foreground" data-testid="settings-skill-sources-error">The skill sources could not be loaded right now.</p>
        ) : sources === null ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : sources.length === 0 ? (
          <p className="text-sm text-muted-foreground" data-testid="settings-skill-sources-empty">No skill sources are set up.</p>
        ) : (
          sources.map((source) => (
            <dl key={source.name} className="grid gap-2 rounded-md border border-line p-3 sm:grid-cols-2" data-testid={`settings-skill-source-${source.name}`}>
              <Detail label="Name" value={source.name} />
              <Detail label="Repository" value={source.repo_url} />
              <Detail label="Folder" value={source.path ?? ''} />
              <Detail label="Branch" value={source.ref ?? ''} />
            </dl>
          ))
        )}
      </CardContent>
    </Card>
  );
}
