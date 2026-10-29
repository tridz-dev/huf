import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { LockKeyhole } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePermissions } from '@/contexts/PermissionsContext';
import { PAGE_ACCESS_ANY } from '@/lib/permissions/pageAccess';

/**
 * What a person sees on a Huf page their role does not include. It replaces the page entirely, so nothing behind it
 * asks the server for data that would be refused. Offers the way back to somewhere they can use.
 */
export function NoAccessPanel({ pageName }: { pageName?: string }) {
  const { hasCapability, isLoading } = usePermissions();
  const canUseFlows = !isLoading && hasCapability('flows.use');
  const canUseAnything = !isLoading && hasCapability(PAGE_ACCESS_ANY);
  useEffect(() => {
    const before = document.title;
    document.title = 'No access - Huf AI';
    return () => { document.title = before; };
  }, []);
  return (
    <div className="flex h-full w-full items-center justify-center p-6" data-testid="no-access-page" role="region" aria-label="No access">
      <div className="max-w-md space-y-5 text-center">
        <div className="flex justify-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-paper-deep">
            <LockKeyhole className="h-6 w-6 text-steel" aria-hidden />
          </div>
        </div>
        <div className="space-y-2">
          <h2 className="font-display text-xl font-semibold text-ink" data-testid="no-access-title">You don't have access to this page</h2>
          <p className="text-sm text-steel" data-testid="no-access-body">
            {canUseAnything
              ? `${pageName ? `${pageName} is` : 'This page is'} not part of your role. Ask a Huf administrator if you need it.`
              : 'Your account is not set up for Huf yet. Ask a Huf administrator to give you a role.'}
          </p>
        </div>
        {canUseAnything && (
          <div className="flex flex-wrap items-center justify-center gap-2">
            {canUseFlows && (
              <Button asChild variant="outline" className="max-[1023px]:min-h-11">
                <Link to="/flows" data-testid="no-access-go-flows">Go to Flows</Link>
              </Button>
            )}
            <Button asChild variant="outline" className="max-[1023px]:min-h-11">
              <Link to="/" data-testid="no-access-go-hub">Back to the Hub</Link>
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
