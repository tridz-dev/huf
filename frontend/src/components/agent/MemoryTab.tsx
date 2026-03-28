import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';

export function MemoryTab() {
  return (
    <Card className="border-dashed">
      <CardHeader>
        <div className="flex items-center gap-2">
          <CardTitle>Memory</CardTitle>
          <Badge variant="secondary">Coming Soon</Badge>
        </div>
        <CardDescription>
          The memory system is being finalized. This preview keeps the future structure visible, but inputs are disabled until merge.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 opacity-60">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border p-4">
            <p className="text-sm font-medium">Enable agent memory</p>
            <p className="mt-1 text-xs text-muted-foreground">Capture structured memories across sessions.</p>
            <div className="mt-3">
              <Switch checked={false} disabled aria-label="Enable memory (coming soon)" />
            </div>
          </div>

          <div className="rounded-lg border p-4">
            <p className="text-sm font-medium">Memory profile</p>
            <p className="mt-1 text-xs text-muted-foreground">Choose default schema and extraction strategy.</p>
            <Input className="mt-3" value="General" disabled readOnly />
          </div>
        </div>

        <div className="rounded-lg border p-4">
          <p className="text-sm font-medium">Retrieval mode</p>
          <p className="mt-1 text-xs text-muted-foreground">Hybrid retrieval + tool access will be configurable here.</p>
          <Input className="mt-3" value="Hybrid (preview)" disabled readOnly />
        </div>
      </CardContent>
    </Card>
  );
}
