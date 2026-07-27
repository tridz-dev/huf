import { useState } from 'react';
import { UnifiedLayout } from '@/layouts/UnifiedLayout';
import { IntegrationSettingsProvider } from '@/contexts/IntegrationSettingsContext';
import { IntegrationSettingsListingPage } from './IntegrationSettingsListingPage';
import { IntegrationSettingsHeaderActions } from '@/components/integrations/IntegrationSettingsHeaderActions';

export default function ChannelsPageWrapper() {
  const [catalogOpenKey, setCatalogOpenKey] = useState(0);

  return (
    <IntegrationSettingsProvider onAddIntegration={() => setCatalogOpenKey((value) => value + 1)}>
      <UnifiedLayout headerActions={<IntegrationSettingsHeaderActions kind="channels" />}>
        <IntegrationSettingsListingPage kind="channels" catalogOpenKey={catalogOpenKey} />
      </UnifiedLayout>
    </IntegrationSettingsProvider>
  );
}
