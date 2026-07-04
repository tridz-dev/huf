import { Shield } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from './ui/button';
import { usePermissions } from '@/contexts/PermissionsContext';

export function UsersHeaderActions() {
  const { hasCapability } = usePermissions();

  if (!hasCapability('roles.manage')) {
    return null;
  }

  return (
    <Button asChild variant="outline" size="sm">
      <Link to="/roles">
        <Shield className="w-4 h-4 mr-2" />
        View Role details
      </Link>
    </Button>
  );
}
