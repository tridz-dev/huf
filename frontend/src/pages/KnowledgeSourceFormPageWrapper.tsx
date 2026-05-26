import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { KnowledgeSourceFormPage } from './KnowledgeSourceFormPage';
import { getKnowledgeSource } from '../services/knowledgeApi';

export { KnowledgeSourceFormPageWrapper };
export default KnowledgeSourceFormPageWrapper;

function KnowledgeSourceFormPageWrapper() {
  const { id } = useParams<{ id: string }>();
  const [sourceName, setSourceName] = useState<string>('New Knowledge Source');
  const isNew = id === 'new';

  useEffect(() => {
    if (id && !isNew) {
      getKnowledgeSource(id)
        .then((source) => {
          setSourceName(source.source_name || source.name);
        })
        .catch((error) => {
          console.error('Error loading knowledge source:', error);
          setSourceName('Knowledge Source');
        });
    } else {
      setSourceName('New Knowledge Source');
    }
  }, [id, isNew]);

  const breadcrumbs = [
    { label: 'Knowledge', href: '/knowledge' },
    { label: sourceName },
  ];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <KnowledgeSourceFormPage />
    </UnifiedLayout>
  );
}
