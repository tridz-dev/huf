import { useState } from 'react';
import { ModelsProvider } from '../contexts/ModelsContext';
import { ModelsPage } from './ModelsPage';

function ModelsPageWrapper() {
  const [addModelKey, setAddModelKey] = useState(0);

  const handleAddModel = () => {
    setAddModelKey(prev => prev + 1);
  };

  return (
    <ModelsProvider onAddModel={handleAddModel}>
      <ModelsPage addModelKey={addModelKey} />
    </ModelsProvider>
  );
}

export default ModelsPageWrapper;
