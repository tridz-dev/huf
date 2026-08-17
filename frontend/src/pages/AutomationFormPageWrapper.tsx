import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { UnifiedLayout } from '../layouts/UnifiedLayout';
import { AutomationFormPage } from './automation/AutomationFormPage';
import { getAutomation } from '../services/automationApi';

export { AutomationFormPageWrapper };
export default AutomationFormPageWrapper;

function AutomationFormPageWrapper() {
  const { automationId } = useParams<{ automationId: string }>();
  const [automationName, setAutomationName] = useState<string>('New automation');
  const isNew = !automationId || automationId === 'new';

  useEffect(() => {
    if (automationId && !isNew) {
      getAutomation(automationId)
        .then((automation) => {
          setAutomationName(automation?.automation_name || automationId);
        })
        .catch((error) => {
          console.error('Error loading automation:', error);
          setAutomationName('Automation');
        });
    } else {
      setAutomationName('New automation');
    }
  }, [automationId, isNew]);

  // No standalone "/automations" registry page exists in this pass (see
  // this track's CONTEXT.md non-goals) -- there is nowhere useful to link
  // an "Automations" ancestor crumb back to, so this page's breadcrumb is
  // just its own name.
  const breadcrumbs = [{ label: automationName }];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <AutomationFormPage />
    </UnifiedLayout>
  );
}
