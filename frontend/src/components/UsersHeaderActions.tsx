import { Shield } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from './ui/button';

export function UsersHeaderActions() {
  return (
    <Button asChild variant="outline" size="sm">
      <Link to="/roles">
        <Shield className="w-4 h-4 mr-2" />
        View Role details
      </Link>
    </Button>
  );
}
