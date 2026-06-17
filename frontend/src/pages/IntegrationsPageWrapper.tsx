import { useState } from 'react';
import { IntegrationsProvider } from '../contexts/IntegrationsContext';
import { IntegrationsPage } from './IntegrationsPage';

export { IntegrationsPageWrapper };
export default IntegrationsPageWrapper;

function IntegrationsPageWrapper() {
  const [addProviderKey, setAddProviderKey] = useState(0);

  const handleAddProvider = () => {
    // Trigger re-render to open modal in IntegrationsPage
    setAddProviderKey(prev => prev + 1);
  };

  return (
    <IntegrationsProvider onAddProvider={handleAddProvider}>
      <IntegrationsPage addProviderKey={addProviderKey} />
    </IntegrationsProvider>
  );
}

