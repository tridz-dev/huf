import { useState } from 'react';
import { ModelsProvider } from '../contexts/ModelsContext';
import { ModelsPage } from './ModelsPage';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { ModelsHeaderActions } from '../components/ModelsHeaderActions';

export function ModelsPageWrapper() {
  const [addModelKey, setAddModelKey] = useState(0);

  const handleAddModel = () => {
    setAddModelKey(prev => prev + 1);
  };

  return (
    <ModelsProvider onAddModel={handleAddModel}>
      <UnifiedLayout headerActions={<ModelsHeaderActions />}>
        <ModelsPage addModelKey={addModelKey} />
      </UnifiedLayout>
    </ModelsProvider>
  );
}

export default ModelsPageWrapper;
