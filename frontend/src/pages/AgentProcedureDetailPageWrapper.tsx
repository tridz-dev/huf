import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import AgentProcedureDetailPage from './AgentProcedureDetailPage';
import { getAgentProcedure, type AgentProcedureDoc } from '@/services/agentProcedureApi';

export { AgentProcedureDetailPageWrapper };
export default AgentProcedureDetailPageWrapper;

function AgentProcedureDetailPageWrapper() {
  const { procedureId } = useParams<{ procedureId: string }>();
  const [label, setLabel] = useState<string>('Procedure');

  useEffect(() => {
    if (!procedureId) {
      setLabel('Procedure');
      return;
    }

    (async () => {
      try {
        const doc = (await getAgentProcedure(procedureId)) as AgentProcedureDoc | null;
        setLabel(doc?.procedure_name || doc?.name || procedureId);
      } catch {
        setLabel(procedureId);
      }
    })();
  }, [procedureId]);

  const breadcrumbs = [
    { label: 'Procedures', href: '/procedures' },
    { label },
  ];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs} showCurrentCrumb>
      <AgentProcedureDetailPage />
    </UnifiedLayout>
  );
}
