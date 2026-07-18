import { useNavigate } from 'react-router-dom';
import { IntegrationServicesProvider } from '@/contexts/IntegrationServicesContext';
import { IntegrationServicesListingPage } from './IntegrationServicesListingPage';
import { UnifiedLayout } from '@/layouts/UnifiedLayout';
import { IntegrationServicesHeaderActions } from '@/components/integration-services/IntegrationServicesHeaderActions';

export function IntegrationServicesListingPageWrapper() {
  const navigate = useNavigate();

  const handleAddService = () => {
    navigate('/integration-services/new');
  };

  return (
    <IntegrationServicesProvider onAddService={handleAddService}>
      <UnifiedLayout headerActions={<IntegrationServicesHeaderActions />}>
        <IntegrationServicesListingPage />
      </UnifiedLayout>
    </IntegrationServicesProvider>
  );
}

export default IntegrationServicesListingPageWrapper;
