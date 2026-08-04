import { useState } from 'react';
import { PageHeaderActions } from '@/layouts/PageHeaderActions';
import { ModelsProvider } from '../contexts/ModelsContext';
import { ModelsPage } from './ModelsPage';
import { ModelsHeaderActions } from '../components/ModelsHeaderActions';

export function ModelsPageWrapper() {
  const [addModelKey, setAddModelKey] = useState(0);

  const handleAddModel = () => {
    setAddModelKey(prev => prev + 1);
  };

  return (
    <ModelsProvider onAddModel={handleAddModel}>
      <PageHeaderActions>
        <ModelsHeaderActions />
      </PageHeaderActions>
      <ModelsPage addModelKey={addModelKey} />
    </ModelsProvider>
  );
}

export default ModelsPageWrapper;
