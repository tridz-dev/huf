import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import AgentContextArtifactDetailPage from './AgentContextArtifactDetailPage';
import { getArtifact, type AgentContextArtifactDoc } from '@/services/agentContextArtifactApi';

export { AgentContextArtifactDetailPageWrapper };
export default AgentContextArtifactDetailPageWrapper;

function AgentContextArtifactDetailPageWrapper() {
  const { artifactId } = useParams<{ artifactId: string }>();
  const [label, setLabel] = useState<string>('Artifact');

  useEffect(() => {
    if (!artifactId) {
      setLabel('Artifact');
      return;
    }

    (async () => {
      try {
        const doc = (await getArtifact(artifactId)) as AgentContextArtifactDoc | null;
        setLabel(doc?.name || artifactId);
      } catch {
        setLabel(artifactId);
      }
    })();
  }, [artifactId]);

  const breadcrumbs = [
    { label: 'Artifacts', href: '/artifacts' },
    { label },
  ];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs} showCurrentCrumb>
      <AgentContextArtifactDetailPage />
    </UnifiedLayout>
  );
}
