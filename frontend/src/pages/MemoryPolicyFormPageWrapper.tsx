import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { usePageLayout } from '@/hooks/usePageLayout';
import { MemoryPolicyFormPage } from './MemoryPolicyFormPage';
import { getMemoryPolicy } from '../services/memoryPolicyApi';

export { MemoryPolicyFormPageWrapper };
export default MemoryPolicyFormPageWrapper;

function MemoryPolicyFormPageWrapper() {
  const { id } = useParams<{ id: string }>();
  const [policyLabel, setPolicyLabel] = useState<string>('New Policy');
  const isNew = id === 'new';

  useEffect(() => {
    if (id && !isNew) {
      getMemoryPolicy(id)
        .then((policy) => {
          setPolicyLabel(policy.policy_name || policy.name);
        })
        .catch((error) => {
          console.error('Error loading memory policy:', error);
          setPolicyLabel('Memory Policy');
        });
    } else {
      setPolicyLabel('New Policy');
    }
  }, [id, isNew]);

  const breadcrumbs = [
    { label: 'Memory', href: '/memory' },
    { label: 'Policies', href: '/memory#policies' },
    { label: policyLabel },
  ];

  usePageLayout({ breadcrumbs });

  return <MemoryPolicyFormPage />;
}
