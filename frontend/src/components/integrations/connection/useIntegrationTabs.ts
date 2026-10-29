import { useCallback, useEffect, useMemo, useState } from 'react';
import type { TabFieldMapping } from '@/utils/formValidation';

interface TabConfig {
  label: string;
  fields: string[];
  default: boolean;
  disabled: boolean;
}

/**
 * Tabs of an integration page. Connection (name, credentials, options) is always first and the default; Recipients and
 * Channel exist only where the service has them. Older links (#credentials, #general) point at the Connection tab.
 */
export function useIntegrationTabs(serviceCategory: string, surface: 'Integration' | 'Gateway') {
  const tabConfig = useMemo(() => {
    const base: Record<string, TabConfig> = {
      connection: {
        label: 'Connection',
        fields: ['service', 'display_label', 'is_active', 'is_default', 'credentialValues'],
        default: true,
        disabled: false,
      },
    };

    if (serviceCategory === 'Communication') {
      base.recipients = {
        label: 'Recipients',
        fields: ['recipients'],
        default: false,
        disabled: false,
      };
    }

    // CL-04: Telegram no longer gets its own tab. Every Gateway-surface
    // provider, Telegram included, is configured entirely from the generic
    // Channel tab below (routing, admission policy, webhook URL, and for
    // Telegram specifically, the "Setup Webhook" convenience action).
    if (surface === 'Gateway') {
      base.channel = {
        label: 'Channel',
        fields: [],
        default: false,
        disabled: false,
      };
    }

    return base;
  }, [serviceCategory, surface]);

  const validTabs = useMemo(() => Object.keys(tabConfig), [tabConfig]);
  const defaultTab = useMemo(
    () => Object.entries(tabConfig).find(([, config]) => config.default)?.[0] || validTabs[0],
    [tabConfig, validTabs],
  );
  const tabFieldMapping: TabFieldMapping = useMemo(
    () => Object.fromEntries(
      Object.entries(tabConfig).map(([key, config]) => [key, [...config.fields]]),
    ),
    [tabConfig],
  );
  const tabLabels = useMemo(
    () => Object.fromEntries(
      Object.entries(tabConfig).map(([key, config]) => [key, config.label]),
    ),
    [tabConfig],
  );

  // Older links (#credentials, #general) point at the Connection tab, where the credentials now are.
  const tabFromHash = useCallback(
    (hash: string) => {
      const name = hash === 'credentials' || hash === 'general' ? 'connection' : hash;
      return name && validTabs.includes(name) ? name : defaultTab;
    },
    [validTabs, defaultTab],
  );
  const [activeTab, setActiveTab] = useState<string>(() => {
    const hashFromUrl = window.location.hash.slice(1);
    return hashFromUrl === 'credentials' || hashFromUrl === 'general' ? 'connection' : hashFromUrl || 'connection';
  });

  useEffect(() => {
    if (!validTabs.includes(activeTab)) {
      setActiveTab(defaultTab);
    }
  }, [validTabs, activeTab, defaultTab]);

  useEffect(() => {
    const handleHashChange = () => {
      setActiveTab(tabFromHash(window.location.hash.slice(1)));
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [tabFromHash]);

  const handleTabChange = (value: string) => {
    setActiveTab(value);
    if (value === defaultTab) {
      window.history.replaceState(null, '', window.location.pathname + window.location.search);
    } else {
      window.location.hash = value;
    }
  };


  return { tabConfig, validTabs, defaultTab, tabFieldMapping, tabLabels, activeTab, setActiveTab, handleTabChange };
}
