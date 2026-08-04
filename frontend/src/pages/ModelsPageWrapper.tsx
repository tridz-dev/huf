import { useState } from 'react';
import { usePageLayout } from '@/hooks/usePageLayout';
import { ModelsProvider } from '../contexts/ModelsContext';
import { ModelsPage } from './ModelsPage';
import { ModelsHeaderActions } from '../components/ModelsHeaderActions';

export function ModelsPageWrapper() {
  const [addModelKey, setAddModelKey] = useState(0);

  const handleAddModel = () => {
    setAddModelKey(prev => prev + 1);
  };

  usePageLayout({ headerActions: <ModelsHeaderActions /> });

  return (
    <ModelsProvider onAddModel={handleAddModel}>
      <ModelsPage addModelKey={addModelKey} />
    </ModelsProvider>
  );
}

export default ModelsPageWrapper;
