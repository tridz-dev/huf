import { useNavigate } from 'react-router-dom';
import { usePageLayout } from '@/hooks/usePageLayout';
import { IntegrationServicesProvider } from '@/contexts/IntegrationServicesContext';
import { IntegrationServicesListingPage } from './IntegrationServicesListingPage';
import { IntegrationServicesHeaderActions } from '@/components/integration-services/IntegrationServicesHeaderActions';

export function IntegrationServicesListingPageWrapper() {
  const navigate = useNavigate();

  const handleAddService = () => {
    navigate('/integration-services/new');
  };

  usePageLayout({ headerActions: <IntegrationServicesHeaderActions /> });

  return (
    <IntegrationServicesProvider onAddService={handleAddService}>
      <IntegrationServicesListingPage />
    </IntegrationServicesProvider>
  );
}

export default IntegrationServicesListingPageWrapper;
