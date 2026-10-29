import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { useLocation } from 'react-router-dom';
import type { UseFormReturn } from 'react-hook-form';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { isTestable } from '@/lib/integrations/health';
import { testIntegrationConnection, type ConnectionTestResult } from '@/services/integrationApi';
import type { IntegrationSettingsDoc } from '@/types/integration.types';
import type { IntegrationFormValues } from '../types';

/** What the page remembers about the saved connection between checks. */
export interface ConnectionMeta {
  lastError: string | undefined;
  displayLabel: string;
  accountLabel: string;
  testStatus: NonNullable<IntegrationSettingsDoc['last_test_status']>;
  testAt: string | undefined;
  testMessage: string;
}

export function metaFrom(data: Partial<IntegrationSettingsDoc>): ConnectionMeta {
  return {
    lastError: data.last_error || undefined,
    displayLabel: data.display_label ?? '',
    accountLabel: data.account_label ?? '',
    testStatus: (data.last_test_status ?? '') as ConnectionMeta['testStatus'],
    testAt: data.last_test_at || undefined,
    testMessage: data.last_test_message ?? '',
  };
}

interface Options {
  form: UseFormReturn<IntegrationFormValues>;
  isNew: boolean;
  settingId?: string;
  /** The saved integration and its service are loaded. */
  ready: boolean;
  setDocMeta: Dispatch<SetStateAction<ConnectionMeta>>;
}

/**
 * Test connection for the details page: a harmless read-only check. Values typed in the form are checked as typed
 * (and not kept); otherwise the saved ones are checked and the answer is kept on the integration.
 * Right after Create the saved credentials are checked once.
 */
export function useConnectionTest({ form, isNew, settingId, ready, setDocMeta }: Options) {
  const [testing, setTesting] = useState(false);
  const [live, setLive] = useState<{ result: ConnectionTestResult; unsaved: boolean } | null>(null);
  const location = useLocation();
  const autoTested = useRef<string | null>(null);

  const runTest = useCallback(async () => {
    const service = form.getValues('service');
    const typed = Object.fromEntries(
      Object.entries(form.getValues('credentialValues') ?? {}).filter(([, v]) => typeof v === 'string' && v.trim() !== ''),
    ) as Record<string, string>;
    const unsaved = Object.keys(typed).length > 0;
    setTesting(true);
    setLive(null);
    try {
      const result = await testIntegrationConnection(service, isNew ? undefined : settingId, typed);
      if (!unsaved && result.checked_at && result.code !== 'unreachable') {
        setDocMeta((prev) => ({
          ...prev,
          testStatus: result.status,
          testAt: result.checked_at,
          testMessage: result.message,
          accountLabel: result.account ?? '',
          lastError: result.status === 'Connected' ? undefined : prev.lastError,
        }));
      } else {
        setLive({ result, unsaved });
      }
    } catch (error) {
      setLive({
        result: { status: 'Rejected', code: 'unreachable', message: getFrappeErrorMessage(error) || 'Could not run the check. Try again.' },
        unsaved: false,
      });
    } finally {
      setTesting(false);
    }
  }, [form, isNew, settingId, setDocMeta]);

  useEffect(() => {
    if (!ready || isNew || !settingId) return;
    const state = location.state as { autoTest?: boolean } | null;
    if (state?.autoTest && autoTested.current !== settingId && isTestable(form.getValues('service'))) {
      autoTested.current = settingId;
      void runTest();
    }
  }, [ready, isNew, settingId, location.state, form, runTest]);

  return { testing, live, setLive, runTest };
}
