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

  const breadcrumbs = [{ label: 'Automations', href: '/automations' }, { label: automationName }];

  return (
    <UnifiedLayout breadcrumbs={breadcrumbs}>
      <AutomationFormPage />
    </UnifiedLayout>
  );
}
