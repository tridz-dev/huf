import { useState } from 'react';
import { usePageLayout } from '@/hooks/usePageLayout';
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

  usePageLayout({ headerActions: <AiProvidersHeaderActions /> });

  return (
    <AiProvidersProvider onAddProvider={handleAddProvider}>
      <AiProvidersPage addProviderKey={addProviderKey} />
    </AiProvidersProvider>
  );
}
