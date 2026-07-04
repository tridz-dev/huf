import { useState } from 'react';
import { AiProvidersProvider } from '../contexts/AiProvidersContext';
import { AiProvidersPage } from './AiProvidersPage';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { AiProvidersHeaderActions } from '../components/AiProvidersHeaderActions';

export { AiProvidersPageWrapper };
export default AiProvidersPageWrapper;

function AiProvidersPageWrapper() {
  const [addProviderKey, setAddProviderKey] = useState(0);

  const handleAddProvider = () => {
    // Trigger re-render to open modal in AiProvidersPage
    setAddProviderKey(prev => prev + 1);
  };

  return (
    <AiProvidersProvider onAddProvider={handleAddProvider}>
      <UnifiedLayout headerActions={<AiProvidersHeaderActions />}>
        <AiProvidersPage addProviderKey={addProviderKey} />
      </UnifiedLayout>
    </AiProvidersProvider>
  );
}

