import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { SSHConnectionFormPage } from './SSHConnectionFormPage';
import { getSSHConnection } from '../services/sshConnectionApi';

export function SSHConnectionFormPageWrapper() {
  const { id } = useParams<{ id: string }>();
  const isNew = id === 'new';
  const [connectionTitle, setConnectionTitle] = useState<string>('New SSH Connection');

  useEffect(() => {
    if (isNew) {
      setConnectionTitle('New SSH Connection');
      return;
    }

    if (!id) return;
    getSSHConnection(id)
      .then((doc) => {
        setConnectionTitle(doc.display_name || id);
      })
      .catch(() => {
        setConnectionTitle(id);
      });
  }, [id, isNew]);

  const breadcrumbs = [
    { label: 'SSH Connections', href: '/ssh-connections' },
    { label: connectionTitle },
  ];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <SSHConnectionFormPage />
    </UnifiedLayout>
  );
}

export default SSHConnectionFormPageWrapper;
