import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '@/layouts/UnifiedLayout';
import { IntegrationServiceFormPage } from './IntegrationServiceFormPage';
import { getIntegrationService } from '@/services/integrationApi';

export function IntegrationServiceFormPageWrapper() {
  const { serviceId } = useParams<{ serviceId: string }>();
  const [title, setTitle] = useState('New Service');
  const isNew = serviceId === 'new';

  useEffect(() => {
    if (serviceId && !isNew) {
      getIntegrationService(serviceId)
        .then((doc) => {
          setTitle(doc.service_name.replace(/_/g, ' '));
        })
        .catch(() => {
          setTitle('Integration Service');
        });
    } else {
      setTitle('New Service');
    }
  }, [serviceId, isNew]);

  const breadcrumbs = [
    { label: 'Integration Services', href: '/integration-services' },
    { label: title },
  ];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <IntegrationServiceFormPage />
    </UnifiedLayout>
  );
}

export default IntegrationServiceFormPageWrapper;
