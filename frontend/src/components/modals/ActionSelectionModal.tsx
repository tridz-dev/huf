import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import {
  Search,
  Repeat,
  GitBranch,
  RotateCw,
  UserCheck,
  Code,
  Mail,
  Webhook,
  FileText,
  Calendar,
  MessageSquare,
  Sheet
} from 'lucide-react';
import { actionOptions } from '../../data/actions';
import { ActionConfig } from '../../types/flow.types';

interface ActionSelectionModalProps {
  open: boolean;
  onClose: () => void;
  onSelect: (actionType: string, config: ActionConfig) => void;
}

const iconMap: Record<string, any> = {
  Repeat,
  GitBranch,
  RotateCw,
  UserCheck,
  Code,
  Mail,
  Webhook,
  FileText,
  Calendar,
  MessageSquare,
  Sheet
};

export function ActionSelectionModal({
  open,
  onClose,
  onSelect
}: ActionSelectionModalProps) {
  const [searchQuery, setSearchQuery] = useState('');

  const filteredActions = actionOptions.filter((action) =>
    action.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const transformActions = filteredActions.filter((a) => a.category === 'transform');
  const controlActions = filteredActions.filter((a) => a.category === 'control');
  const utilityActions = filteredActions.filter((a) => a.category === 'utility');
  const integrationActions = filteredActions.filter((a) => a.category === 'integration');

  const handleSelectAction = (actionId: string) => {
    let config: ActionConfig = { type: undefined };

    if (actionId === 'transform') {
      config = { type: 'transform', transformations: [] };
    } else if (actionId === 'router') {
      config = { type: 'router', branches: [] };
    } else if (actionId === 'loop') {
      config = { type: 'loop', maxIterations: 10 };
    } else if (actionId === 'human-in-loop') {
      config = { type: 'human-in-loop', approvers: [] };
    } else if (actionId === 'code') {
      config = { type: 'code', language: 'javascript', code: '' };
    } else if (actionId === 'email') {
      config = { type: 'utility-email', to: '', subject: '', body: '' };
    } else if (actionId === 'webhook') {
      config = { type: 'utility-webhook', url: '', method: 'POST' };
    } else if (actionId === 'file') {
      config = { type: 'utility-file', operation: 'read', path: '' };
    } else if (actionId === 'date') {
      config = { type: 'utility-date', operation: 'format', format: 'YYYY-MM-DD' };
    }

    onSelect(actionId, config);
    onClose();
  };

  const renderActionCategory = (title: string, actions: typeof actionOptions) => {
    if (actions.length === 0) return null;

    return (
      <div className="mb-6">
        <h3 className="text-sm font-medium mb-3 text-muted-foreground">{title}</h3>
        <div className="grid grid-cols-2 gap-3">
          {actions.map((action) => {
            const Icon = iconMap[action.icon || 'FileText'];
            return (
              <button
                key={action.id}
                className="flex items-center gap-3 p-3 rounded-lg border border-border hover:border-primary/50 hover:bg-accent transition-all"
                onClick={() => handleSelectAction(action.id)}
              >
                <div className="w-8 h-8 rounded bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <Icon className="w-4 h-4 text-primary" />
                </div>
                <div className="text-left flex-1 min-w-0">
                  <div className="text-sm font-medium">{action.name}</div>
                  {action.description && (
                    <div className="text-xs text-muted-foreground truncate">
                      {action.description}
                    </div>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Add Action</DialogTitle>
        </DialogHeader>

        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search actions..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>

        <div className="flex-1 overflow-y-auto">
          {renderActionCategory('Transform', transformActions)}
          {renderActionCategory('Control Flow', controlActions)}
          {renderActionCategory('Utilities', utilityActions)}
          {renderActionCategory('Integrations', integrationActions)}
        </div>

        <div className="flex justify-end pt-4 border-t">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
