import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { usePageLayout } from '@/hooks/usePageLayout';
import AgentRunDetailPage from './AgentRunDetailPage';
import { db } from '@/lib/frappe-sdk';
import { doctype } from '@/data/doctypes';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import type { AgentRunDoc } from '@/services/agentRunApi';

export { AgentRunDetailPageWrapper };
export default AgentRunDetailPageWrapper;

function AgentRunDetailPageWrapper() {
  const { runId } = useParams<{ runId: string }>();
  const [runName, setRunName] = useState<string>('Agent Run');

  useEffect(() => {
    if (!runId) {
      setRunName('Agent Run');
      return;
    }

    (async () => {
      try {
        const doc = (await db.getDoc(doctype['Agent Run'], runId)) as AgentRunDoc;
        setRunName(doc.name || runId);
      } catch (error) {
        console.error(`Error fetching agent run ${runId}:`, getFrappeErrorMessage(error));
        setRunName(runId || 'Agent Run');
      }
    })();
  }, [runId]);

  const breadcrumbs = [
    { label: 'Executions', href: '/executions' },
    { label: runName },
  ];

  usePageLayout({ breadcrumbs });

  return <AgentRunDetailPage />;
}
