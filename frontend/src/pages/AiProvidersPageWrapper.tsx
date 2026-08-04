import { useState } from 'react';
import { PageHeaderActions } from '@/layouts/PageHeaderActions';
import { AiProvidersProvider } from '../contexts/AiProvidersContext';
import { AiProvidersPage } from './AiProvidersPage';
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
      <PageHeaderActions>
        <AiProvidersHeaderActions />
      </PageHeaderActions>
      <AiProvidersPage addProviderKey={addProviderKey} />
    </AiProvidersProvider>
  );
}
