import { useState } from 'react';
import { usePageLayout } from '@/hooks/usePageLayout';
import { IntegrationSettingsProvider } from '@/contexts/IntegrationSettingsContext';
import { IntegrationSettingsListingPage } from './IntegrationSettingsListingPage';
import { IntegrationSettingsHeaderActions } from '@/components/integrations/IntegrationSettingsHeaderActions';

export { IntegrationSettingsListingPageWrapper };
export default IntegrationSettingsListingPageWrapper;

function IntegrationSettingsListingPageWrapper() {
  const [catalogOpenKey, setCatalogOpenKey] = useState(0);

  const handleAddIntegration = () => {
    setCatalogOpenKey((prev) => prev + 1);
  };

  usePageLayout({ headerActions: <IntegrationSettingsHeaderActions /> });

  return (
    <IntegrationSettingsProvider onAddIntegration={handleAddIntegration}>
      <IntegrationSettingsListingPage catalogOpenKey={catalogOpenKey} />
    </IntegrationSettingsProvider>
  );
}
