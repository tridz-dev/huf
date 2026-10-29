import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '@/layouts/UnifiedLayout';
import { IntegrationSettingsDetailsPage } from './IntegrationSettingsDetailsPage';
import { getIntegrationSetting } from '@/services/integrationApi';
import { integrationTitle } from '@/lib/integrations/health';

export { GatewayDetailsPageWrapper };
export default GatewayDetailsPageWrapper;

function GatewayDetailsPageWrapper() {
  const { settingId } = useParams<{ settingId: string }>();
  const [title, setTitle] = useState('New Channel');
  const isNew = settingId === 'new';

  useEffect(() => {
    if (settingId && !isNew) {
      getIntegrationSetting(settingId)
        .then((doc) => {
          setTitle(integrationTitle(doc));
        })
        .catch(() => {
          setTitle('Channel');
        });
    } else {
      setTitle('New Channel');
    }
  }, [settingId, isNew]);

  const breadcrumbs = [
    { label: 'Gateways', href: '/gateways' },
    { label: title },
  ];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <IntegrationSettingsDetailsPage surface="Gateway" />
    </UnifiedLayout>
  );
}
