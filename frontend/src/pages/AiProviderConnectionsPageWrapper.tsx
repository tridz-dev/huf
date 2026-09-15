import { AiProviderConnectionsPage } from './AiProviderConnectionsPage';
import { UnifiedLayout } from '../layouts/UnifiedLayout';

export { AiProviderConnectionsPageWrapper };
export default AiProviderConnectionsPageWrapper;

function AiProviderConnectionsPageWrapper() {
  return (
    <UnifiedLayout>
      <AiProviderConnectionsPage />
    </UnifiedLayout>
  );
}
