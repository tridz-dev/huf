import { useState } from 'react';
import { IntegrationSettingsProvider } from '@/contexts/IntegrationSettingsContext';
import { IntegrationSettingsListingPage } from './IntegrationSettingsListingPage';
import { UnifiedLayout } from '@/layouts/UnifiedLayout';
import { IntegrationSettingsHeaderActions } from '@/components/integrations/IntegrationSettingsHeaderActions';

export { IntegrationSettingsListingPageWrapper };
export default IntegrationSettingsListingPageWrapper;

function IntegrationSettingsListingPageWrapper() {
  const [catalogOpenKey, setCatalogOpenKey] = useState(0);

  const handleAddIntegration = () => {
    setCatalogOpenKey((prev) => prev + 1);
  };

  return (
    <IntegrationSettingsProvider onAddIntegration={handleAddIntegration}>
      <UnifiedLayout headerActions={<IntegrationSettingsHeaderActions />}>
        <IntegrationSettingsListingPage catalogOpenKey={catalogOpenKey} />
      </UnifiedLayout>
    </IntegrationSettingsProvider>
  );
}
