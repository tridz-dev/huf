import { Terminal } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { ApiKeysSection } from '@/components/settings/ApiKeysSection';

export { DeveloperSettingsPage };
export default DeveloperSettingsPage;

function DeveloperSettingsPage() {
  return (
    <div className="relative h-full overflow-auto">
      <div className="relative z-10 p-6 max-w-4xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          <Terminal className="w-6 h-6 text-muted-foreground" />
          <div>
            <h1 className="text-2xl font-bold">Developer Settings</h1>
            <p className="text-sm text-muted-foreground">
              Tools and options for developers building on HUF.
            </p>
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Overview</CardTitle>
            <CardDescription>
              Everything you build against HUF goes through a single base URL.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm">
              Base URL: <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">/huf/api/v1</code>
            </p>
            <p className="text-sm text-muted-foreground mt-2">
              Full API documentation is coming soon. Create a key below to get started.
            </p>
          </CardContent>
        </Card>

        <ApiKeysSection />
      </div>
    </div>
  );
}
