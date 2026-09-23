import { useEffect, useState } from 'react';
import { AlertCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { getAgentSettings } from '@/services/agentSettingsApi';
import { usePermissions } from '@/contexts/PermissionsContext';
import { handleFrappeError } from '@/lib/frappe-error';

/**
 * Banner shown when the Decision Runtime is disabled (kill switch off).
 *
 * Reads Agent Settings.decision_runtime_enabled and renders an Alert explaining
 * the runtime is off and linking to Agent Settings for users with the right capability.
 * Renders nothing when the runtime is on.
 */
export function RuntimeDisabledBanner() {
  const [isDisabled, setIsDisabled] = useState<boolean | null>(null);
  const { hasCapability } = usePermissions();

  useEffect(() => {
    getAgentSettings()
      .then((doc) => {
        // decision_runtime_enabled is 0 (disabled) or 1 (enabled)
        setIsDisabled(!doc?.decision_runtime_enabled);
      })
      .catch((error) => {
        handleFrappeError(error, 'Error loading Agent Settings');
        // Default to showing banner on error
        setIsDisabled(true);
      });
  }, []);

  // Don't render if runtime is enabled or loading
  if (isDisabled === null || !isDisabled) {
    return null;
  }

  return (
    <Alert variant="warning" className="mb-4">
      <AlertCircle className="h-4 w-4" />
      <AlertTitle>Decision Runtime is off</AlertTitle>
      <AlertDescription>
        The Decision Runtime is disabled. Enable it in{' '}
        {hasCapability('decision.admin') ? (
          <Link to="/settings" className="underline hover:no-underline font-medium">
            Agent Settings
          </Link>
        ) : (
          <span className="font-medium">Agent Settings</span>
        )}{' '}
        to use decision policies and deployments.
      </AlertDescription>
    </Alert>
  );
}
