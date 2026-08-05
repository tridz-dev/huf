import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from './ui/button';
import { usePermissions } from '../contexts/PermissionsContext';

export function DataHeaderActions() {
	const navigate = useNavigate();
	const { hasCapability } = usePermissions();

	if (!hasCapability('data.tables.manage')) {
		return null;
	}

	return (
		<Button variant="display" onClick={() => navigate('/data/new')} size="sm">
			<Plus className="w-4 h-4 mr-2" />
			Create table
		</Button>
	);
}
