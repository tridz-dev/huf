import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { MultiSelectCombobox } from '@/components/ui/multi-select-combobox';
import { toast } from 'sonner';
import { getAgents } from '@/services/agentApi';
import { createApiKey, type ApiKeyScope, type ApiKeyAgentRestrictionMode, type CreatedApiKey } from '@/services/developerApi';
import { handleFrappeError } from '@/lib/frappe-error';

interface CreateApiKeyDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (key: CreatedApiKey) => void;
}

const SCOPE_OPTIONS: { value: ApiKeyScope; label: string }[] = [
  { value: 'agents:read', label: 'Read agents' },
  { value: 'agents:run', label: 'Run agents' },
  { value: 'conversations:read', label: 'Read conversations' },
  { value: 'conversations:write', label: 'Write conversations' },
  { value: 'files:read', label: 'Read files' },
  { value: 'files:write', label: 'Write files' },
  { value: 'voice:use', label: 'Use voice' },
  { value: 'ocr:use', label: 'Use OCR' },
];

type ExpirationChoice = 'never' | '30' | '90' | 'custom';

function addDays(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  return date.toISOString();
}

export function CreateApiKeyDialog({ open, onOpenChange, onCreated }: CreateApiKeyDialogProps) {
  const [label, setLabel] = useState('');
  const [restrictionMode, setRestrictionMode] = useState<ApiKeyAgentRestrictionMode>('all');
  const [selectedAgents, setSelectedAgents] = useState<string[]>([]);
  const [agentOptions, setAgentOptions] = useState<{ value: string; label: string }[]>([]);
  const [scopes, setScopes] = useState<ApiKeyScope[]>([]);
  const [expiration, setExpiration] = useState<ExpirationChoice>('never');
  const [customDate, setCustomDate] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    // Reset form each time the dialog opens
    setLabel('');
    setRestrictionMode('all');
    setSelectedAgents([]);
    setScopes([]);
    setExpiration('never');
    setCustomDate('');

    getAgents()
      .then((result) => {
        const items = Array.isArray(result) ? result : result.items;
        setAgentOptions(
          (items || []).map((agent) => ({
            value: agent.name,
            label: agent.agent_name || agent.name,
          })),
        );
      })
      .catch((error) => {
        handleFrappeError(error, 'Error fetching agents');
      });
  }, [open]);

  const toggleScope = (scope: ApiKeyScope) => {
    setScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    );
  };

  const handleSubmit = async () => {
    if (!label.trim()) {
      toast.error('Give this key a name');
      return;
    }
    if (scopes.length === 0) {
      toast.error('Select at least one permission');
      return;
    }
    if (restrictionMode === 'selected' && selectedAgents.length === 0) {
      toast.error('Select at least one agent, or switch to "All permitted agents"');
      return;
    }

    let expiresAt: string | undefined;
    if (expiration === '30') {
      expiresAt = addDays(30);
    } else if (expiration === '90') {
      expiresAt = addDays(90);
    } else if (expiration === 'custom') {
      if (!customDate) {
        toast.error('Choose an expiration date');
        return;
      }
      expiresAt = new Date(customDate).toISOString();
    }

    setSubmitting(true);
    try {
      const created = await createApiKey(
        label.trim(),
        scopes,
        restrictionMode,
        restrictionMode === 'selected' ? selectedAgents : undefined,
        expiresAt,
      );
      if (created) {
        toast.success('Key created');
        onCreated(created);
      }
    } catch (error) {
      handleFrappeError(error, 'Error creating API key');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!submitting) onOpenChange(next); }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Create key</DialogTitle>
        </DialogHeader>

        <div className="space-y-5 max-h-[65vh] overflow-y-auto pr-1">
          <div className="space-y-2">
            <Label htmlFor="api-key-label">Name</Label>
            <Input
              id="api-key-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Production integration"
            />
          </div>

          <div className="space-y-2">
            <Label>Access</Label>
            <RadioGroup
              value={restrictionMode}
              onValueChange={(value) => setRestrictionMode(value as ApiKeyAgentRestrictionMode)}
            >
              <div className="flex items-center gap-2">
                <RadioGroupItem value="all" id="access-all" />
                <Label htmlFor="access-all" className="font-normal">All permitted agents</Label>
              </div>
              <div className="flex items-center gap-2">
                <RadioGroupItem value="selected" id="access-selected" />
                <Label htmlFor="access-selected" className="font-normal">Selected agents</Label>
              </div>
            </RadioGroup>
            {restrictionMode === 'selected' && (
              <MultiSelectCombobox
                options={agentOptions}
                values={selectedAgents}
                onValuesChange={setSelectedAgents}
                placeholder="Select agents..."
                searchPlaceholder="Search agents..."
                emptyText="No agents found."
              />
            )}
          </div>

          <div className="space-y-2">
            <Label>Permissions</Label>
            <div className="grid grid-cols-2 gap-x-4 gap-y-2">
              {SCOPE_OPTIONS.map((option) => (
                <div key={option.value} className="flex items-center gap-2">
                  <Checkbox
                    id={`scope-${option.value}`}
                    checked={scopes.includes(option.value)}
                    onCheckedChange={() => toggleScope(option.value)}
                  />
                  <Label htmlFor={`scope-${option.value}`} className="font-normal">
                    {option.label}
                  </Label>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <Label>Expiration</Label>
            <Select value={expiration} onValueChange={(value) => setExpiration(value as ExpirationChoice)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="never">Never expires</SelectItem>
                <SelectItem value="30">30 days</SelectItem>
                <SelectItem value="90">90 days</SelectItem>
                <SelectItem value="custom">Custom date</SelectItem>
              </SelectContent>
            </Select>
            {expiration === 'custom' && (
              <Input
                type="date"
                value={customDate}
                onChange={(e) => setCustomDate(e.target.value)}
              />
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Creating...' : 'Create key'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
