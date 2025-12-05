import { useState } from 'react';
import { IntegrationsProvider } from '../contexts/IntegrationsContext';
import { IntegrationsPage } from './IntegrationsPage';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { IntegrationsHeaderActions } from '../components/IntegrationsHeaderActions';

export function IntegrationsPageWrapper() {
  const [addProviderKey, setAddProviderKey] = useState(0);

  const handleAddProvider = () => {
    // Trigger re-render to open modal in IntegrationsPage
    setAddProviderKey(prev => prev + 1);
  };

  return (
    <IntegrationsProvider onAddProvider={handleAddProvider}>
      <UnifiedLayout headerActions={<IntegrationsHeaderActions />}>
        <IntegrationsPage addProviderKey={addProviderKey} />
      </UnifiedLayout>
    </IntegrationsProvider>
  );
}

