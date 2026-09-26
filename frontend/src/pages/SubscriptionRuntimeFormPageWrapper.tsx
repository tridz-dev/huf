import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { SubscriptionRuntimeFormPage } from './SubscriptionRuntimeFormPage';
import { getSubscriptionRuntime } from '../services/subscriptionRuntimeApi';

export function SubscriptionRuntimeFormPageWrapper() {
  const { id } = useParams<{ id: string }>();
  const isNew = id === 'new';
  const [runtimeTitle, setRuntimeTitle] = useState<string>('New Subscription Runtime');

  useEffect(() => {
    if (isNew) {
      setRuntimeTitle('New Subscription Runtime');
      return;
    }

    if (!id) return;
    getSubscriptionRuntime(id)
      .then((doc) => {
        setRuntimeTitle(doc.runtime_name || id);
      })
      .catch(() => {
        setRuntimeTitle(id);
      });
  }, [id, isNew]);

  const breadcrumbs = [
    { label: 'Subscription runtimes', href: '/subscription-runtimes' },
    { label: runtimeTitle },
  ];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <SubscriptionRuntimeFormPage />
    </UnifiedLayout>
  );
}

export default SubscriptionRuntimeFormPageWrapper;
