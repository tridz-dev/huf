import { Plus, Filter, Edit, Trash2, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { AgentTriggerListItem, TriggerTypeOption } from '@/services/agentApi';

interface TriggersTabProps {
  triggers: AgentTriggerListItem[];
  triggerTypes: TriggerTypeOption[];
  triggerFilter: string;
  triggerStatusFilter: string;
  onTriggerFilterChange: (value: string) => void;
  onTriggerStatusFilterChange: (value: string) => void;
  onAddTrigger: () => void;
  onEditTrigger: (trigger: AgentTriggerListItem) => void;
  onDeleteTrigger: (triggerId: string) => void;
  deletingTrigger: boolean;
}

export function TriggersTab({
  triggers,
  triggerTypes,
  triggerFilter,
  triggerStatusFilter,
  onTriggerFilterChange,
  onTriggerStatusFilterChange,
  onAddTrigger,
  onEditTrigger,
  onDeleteTrigger,
  deletingTrigger,
}: TriggersTabProps) {
  const filteredTriggers = triggers.filter(trigger => {
    if (triggerFilter !== 'all' && trigger.type !== triggerFilter) return false;
    if (triggerStatusFilter === 'active' && trigger.status !== 'active') return false;
    if (triggerStatusFilter === 'disabled' && trigger.status === 'active') return false;
    return true;
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <div className="space-y-1.5">
          <CardTitle>Agent Triggers</CardTitle>
          <CardDescription>
            Define multiple ways this agent can run
          </CardDescription>
        </div>
        <Button onClick={onAddTrigger} size="sm" type="button">
          <Plus className="w-4 h-4 mr-2" />
          Add Trigger
        </Button>
      </CardHeader>
      <CardContent>
        {triggers.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-muted-foreground mb-4">No triggers added yet.</p>
            <Button onClick={onAddTrigger} variant="outline" type="button">
              <Plus className="w-4 h-4 mr-2" />
              Add Trigger
            </Button>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-3 mb-4">
              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-muted-foreground" />
                <Select value={triggerFilter} onValueChange={onTriggerFilterChange}>
                  <SelectTrigger className="w-[180px]">
                    <SelectValue placeholder="Filter by type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Types</SelectItem>
                    {Array.isArray(triggerTypes) && triggerTypes.map((type) => (
                      <SelectItem key={type.name} value={type.name}>
                        {type.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Select value={triggerStatusFilter} onValueChange={onTriggerStatusFilterChange}>
                <SelectTrigger className="w-[150px]">
                  <SelectValue placeholder="Filter by status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="disabled">Disabled</SelectItem>
                </SelectContent>
              </Select>
              <div className="text-sm text-muted-foreground ml-auto">
                {filteredTriggers.length} of {triggers.length} triggers
              </div>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Type</TableHead>
                  <TableHead>Details</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last Run</TableHead>
                  <TableHead>Next Run</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredTriggers.map((trigger) => (
                  <TableRow key={trigger.name}>
                    <TableCell className="font-medium">{trigger.type}</TableCell>
                    <TableCell className="max-w-xs truncate">{trigger.trigger_name}</TableCell>
                    <TableCell>
                      <Badge variant={trigger.status === 'active' ? 'default' : 'secondary'}>
                        {trigger.status === 'active' ? 'Active' : 'Disabled'}
                      </Badge>
                    </TableCell>
                    <TableCell>—</TableCell>
                    <TableCell>—</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => onEditTrigger(trigger)}
                          disabled={deletingTrigger}
                        >
                          <Edit className="w-4 h-4" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => onDeleteTrigger(trigger.name)}
                          disabled={deletingTrigger}
                        >
                          {deletingTrigger ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </CardContent>
    </Card>
  );
}

