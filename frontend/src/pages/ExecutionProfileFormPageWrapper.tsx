import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { usePageLayout } from '@/hooks/usePageLayout';
import { ExecutionProfileFormPage } from './ExecutionProfileFormPage';
import { getExecutionProfile } from '../services/executionProfileApi';

export function ExecutionProfileFormPageWrapper() {
  const { id } = useParams<{ id: string }>();
  const isNew = id === 'new';
  const [profileTitle, setProfileTitle] = useState<string>('New Execution Profile');

  useEffect(() => {
    if (isNew) {
      setProfileTitle('New Execution Profile');
      return;
    }

    if (!id) return;
    getExecutionProfile(id)
      .then((doc) => {
        setProfileTitle(doc.profile_name || id);
      })
      .catch(() => {
        setProfileTitle(id);
      });
  }, [id, isNew]);

  const breadcrumbs = [
    { label: 'Code Execution', href: '/execution-profiles' },
    { label: profileTitle },
  ];

  usePageLayout({ breadcrumbs });

  return <ExecutionProfileFormPage />;
}

export default ExecutionProfileFormPageWrapper;
