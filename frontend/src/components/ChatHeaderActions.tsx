import { Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from './ui/button';

export function ChatHeaderActions() {
  const navigate = useNavigate();

  const handleNewChat = () => {
    navigate('/chat/new');
  };

  return (
    <Button onClick={handleNewChat} size="sm">
      <Plus className="w-4 h-4 mr-2" />
      New Chat
    </Button>
  );
}


