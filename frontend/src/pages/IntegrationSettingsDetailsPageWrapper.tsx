import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '@/layouts/UnifiedLayout';
import { IntegrationSettingsDetailsPage } from './IntegrationSettingsDetailsPage';
import { getIntegrationSetting } from '@/services/integrationApi';

export { IntegrationSettingsDetailsPageWrapper };
export default IntegrationSettingsDetailsPageWrapper;

function IntegrationSettingsDetailsPageWrapper() {
  const { settingId } = useParams<{ settingId: string }>();
  const [title, setTitle] = useState('New Integration');
  const isNew = settingId === 'new';

  useEffect(() => {
    if (settingId && !isNew) {
      getIntegrationSetting(settingId)
        .then((doc) => {
          setTitle(doc.name);
        })
        .catch(() => {
          setTitle('Integration');
        });
    } else {
      setTitle('New Integration');
    }
  }, [settingId, isNew]);

  const breadcrumbs = [
    { label: 'Integrations', href: '/integrations' },
    { label: title },
  ];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <IntegrationSettingsDetailsPage />
    </UnifiedLayout>
  );
}
