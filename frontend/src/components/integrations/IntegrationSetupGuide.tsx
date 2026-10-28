import { useState } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { CheckCircle2, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { INTEGRATION_GUIDES } from '@/data/integrationGuides';
import { testIntegrationConnection, type ConnectionTestResult } from '@/services/integrationApi';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { IntegrationFormValues } from './types';

interface IntegrationSetupGuideProps {
  service: string;
  /** Saved integration, when editing: its stored credentials are tested for any field left blank. */
  settingId?: string;
  form: UseFormReturn<IntegrationFormValues>;
}

/** Numbered how-to plus a read-only Test connection for Gmail, Slack, Google Sheets and Google Drive. */
export function IntegrationSetupGuide({ service, settingId, form }: IntegrationSetupGuideProps) {
  const guide = INTEGRATION_GUIDES[service];
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<ConnectionTestResult | null>(null);
  if (!guide) return null;

  const runTest = async () => {
    setTesting(true);
    setResult(null);
    const typed = Object.fromEntries(
      Object.entries(form.getValues('credentialValues') ?? {}).filter(([, v]) => typeof v === 'string' && v.trim() !== ''),
    ) as Record<string, string>;
    try {
      setResult(await testIntegrationConnection(service, settingId, typed));
    } catch (error) {
      setResult({ status: 'Rejected', message: getFrappeErrorMessage(error) || 'Could not run the check.' });
    } finally {
      setTesting(false);
    }
  };

  const ok = result?.status === 'Connected';
  return (
    <div className="space-y-3 rounded-lg border bg-muted/30 p-4" data-testid="integration-setup-guide">
      <p className="text-sm font-medium">{guide.title}</p>
      <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground" data-testid="integration-setup-steps">
        {guide.steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      <p className="text-sm text-muted-foreground" data-testid="integration-setup-scopes">{guide.scopes}</p>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" variant="outline" size="sm" onClick={runTest} disabled={testing} data-testid="integration-test-connection">
          {testing ? <Spinner className="mr-2 h-4 w-4" /> : null}
          Test connection
        </Button>
        {result && (
          <p
            role="status"
            className={`flex items-start gap-1.5 text-sm ${ok ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'}`}
            data-testid="integration-test-result"
            data-status={result.status}
          >
            {ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0" />}
            <span>
              <span className="font-medium">{result.status}.</span> {result.message}
            </span>
          </p>
        )}
      </div>
    </div>
  );
}
