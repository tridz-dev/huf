import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from './ui/button';

export function DataHeaderActions() {
	const navigate = useNavigate();

	return (
		<Button variant="display" onClick={() => navigate('/data/new')} size="sm">
			<Plus className="w-4 h-4 mr-2" />
			Create Table
		</Button>
	);
}
