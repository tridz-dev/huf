import { useState } from 'react';

import { ModelsHeaderActions } from '@/components/ModelsHeaderActions';
import { ModelsProvider } from '@/contexts/ModelsContext';
import { UnifiedLayout } from '@/layouts/UnifiedLayout';

import ModelListingPage from './ModelListingPage';

export { ModelListingPageWrapper };
export default ModelListingPageWrapper;

function ModelListingPageWrapper() {
  const [addModelKey, setAddModelKey] = useState(0);

  const handleAddModel = () => {
    setAddModelKey((previous) => previous + 1);
  };

  return (
    <ModelsProvider onAddModel={handleAddModel}>
      <UnifiedLayout headerActions={<ModelsHeaderActions />}>
        <ModelListingPage addModelKey={addModelKey} />
      </UnifiedLayout>
    </ModelsProvider>
  );
}
