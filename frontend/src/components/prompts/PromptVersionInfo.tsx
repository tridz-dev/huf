import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface PromptVersionInfoProps {
  version?: number;
  isLatest?: 0 | 1;
  previousVersion?: string;
  onOpenPrevious: (name: string) => void;
}

/** Version badges for a saved prompt. Older versions are read-only, so say so. */
export function PromptVersionInfo({ version, isLatest, previousVersion, onOpenPrevious }: PromptVersionInfoProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Version info</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">Version {version ?? 1}</Badge>
          {isLatest === 1 ? <Badge>Latest</Badge> : <Badge variant="secondary">Historical</Badge>}
          {previousVersion ? (
            <Button type="button" variant="link" className="h-auto p-0" onClick={() => onOpenPrevious(previousVersion)}>
              Previous: {previousVersion}
            </Button>
          ) : null}
        </div>
        {isLatest === 1 ? (
          <p className="text-xs text-steel-soft">
            Changing the prompt body and saving creates a new version. Agents locked to a version keep the old text.
          </p>
        ) : (
          <p className="text-xs text-steel-soft" data-testid="prompt-readonly-note">
            This is an older version and cannot be edited. Open the latest version to make changes.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
