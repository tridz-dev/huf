import { useState } from 'react';
import { Plus, X, Info } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Textarea } from '@/components/ui/textarea';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { FormLabel, FormDescription } from '@/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { AIProvider, AIModel } from '@/types/agent.types';

export interface AllowedModelRow {
  name?: string;
  provider?: string;
  model?: string;
  enable_auto_routing?: boolean;
  routing_description?: string;
  priority?: number;
}

interface AllowedModelsRoutingEditorProps {
  models: AllowedModelRow[];
  providers: AIProvider[];
  availableModels: AIModel[];
  onModelsChange: (models: AllowedModelRow[]) => void;
  disabled?: boolean;
}

function LabelWithInfo({ label, tooltip }: { label: string; tooltip: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-sm font-medium">{label}</span>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Info className="h-3.5 w-3.5 text-muted-foreground cursor-help" />
          </TooltipTrigger>
          <TooltipContent className="max-w-xs">{tooltip}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
  );
}

export function AllowedModelsRoutingEditor({
  models,
  providers,
  availableModels,
  onModelsChange,
  disabled = false,
}: AllowedModelsRoutingEditorProps) {
  const [showDialog, setShowDialog] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [formData, setFormData] = useState<AllowedModelRow>({
    provider: '',
    model: '',
    enable_auto_routing: false,
    routing_description: '',
    priority: undefined,
  });

  const handleAddClick = () => {
    setEditingIndex(null);
    setFormData({
      provider: '',
      model: '',
      enable_auto_routing: false,
      routing_description: '',
      priority: undefined,
    });
    setShowDialog(true);
  };

  const handleEditClick = (index: number) => {
    setEditingIndex(index);
    setFormData({ ...models[index] });
    setShowDialog(true);
  };

  const handleDeleteClick = (index: number) => {
    const updated = models.filter((_, i) => i !== index);
    onModelsChange(updated);
  };

  const handleSave = () => {
    if (!formData.provider || !formData.model) {
      return;
    }

    let updated: AllowedModelRow[];
    if (editingIndex !== null) {
      updated = models.map((m, i) => (i === editingIndex ? formData : m));
    } else {
      updated = [...models, formData];
    }

    onModelsChange(updated);
    setShowDialog(false);
  };

  const handleProviderChange = (provider: string) => {
    setFormData({ ...formData, provider, model: '' });
  };

  const modelsForProvider = availableModels.filter((m) => m.provider === formData.provider);

  const isEmpty = models.length === 0;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Model Routing</CardTitle>
          <CardDescription>
            Configure alternative models for this agent when using Decision Policy routing.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {isEmpty ? (
            <div className="flex flex-col items-center justify-center py-8 px-4 border border-dashed rounded-lg bg-muted/30">
              <p className="text-sm text-muted-foreground text-center mb-3">
                No models configured yet. Add models to enable routing via Decision Policies.
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleAddClick}
                disabled={disabled}
              >
                <Plus className="h-4 w-4 mr-2" />
                Add model
              </Button>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/50">
                      <TableHead className="w-[20%]">Provider</TableHead>
                      <TableHead className="w-[20%]">Model</TableHead>
                      <TableHead className="w-[12%]">
                        <LabelWithInfo
                          label="Auto Route"
                          tooltip="Enable automatic routing to this model when a Decision Policy decision is active"
                        />
                      </TableHead>
                      <TableHead className="w-[25%]">
                        <LabelWithInfo
                          label="Description"
                          tooltip="Notes on when this model should be routed to (e.g., 'For complex reasoning', 'Fast, cheap fallback')"
                        />
                      </TableHead>
                      <TableHead className="w-[12%]">
                        <LabelWithInfo
                          label="Priority"
                          tooltip="Lower numbers = higher priority for selection"
                        />
                      </TableHead>
                      <TableHead className="w-[11%]">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {models.map((row, index) => (
                      <TableRow key={row.name || index} className="hover:bg-muted/30">
                        <TableCell className="font-medium text-sm">{row.provider || '-'}</TableCell>
                        <TableCell className="text-sm">{row.model || '-'}</TableCell>
                        <TableCell>
                          <div className="flex items-center">
                            <Checkbox
                              checked={row.enable_auto_routing ?? false}
                              disabled
                              className="pointer-events-none"
                            />
                          </div>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground max-w-xs truncate">
                          {row.routing_description || '-'}
                        </TableCell>
                        <TableCell className="text-sm">{row.priority ?? '-'}</TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => handleEditClick(index)}
                              disabled={disabled}
                            >
                              Edit
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDeleteClick(index)}
                              disabled={disabled}
                              aria-label="Delete model"
                            >
                              <X className="h-4 w-4" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleAddClick}
                disabled={disabled}
              >
                <Plus className="h-4 w-4 mr-2" />
                Add model
              </Button>
            </>
          )}

          <FormDescription className="text-xs pt-2">
            Models in this list can be routed to via Decision Policies when Model Routing is enabled.
            Enable auto-routing to include this model in automatic decision evaluation.
          </FormDescription>
        </CardContent>
      </Card>

      <Dialog open={showDialog} onOpenChange={setShowDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {editingIndex !== null ? 'Edit Model Routing' : 'Add Model Routing'}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <div className="space-y-2">
              <FormLabel>Provider</FormLabel>
              <Select value={formData.provider || ''} onValueChange={handleProviderChange}>
                <SelectTrigger>
                  <SelectValue placeholder="Select provider" />
                </SelectTrigger>
                <SelectContent>
                  {providers.map((p) => (
                    <SelectItem key={p.name} value={p.name}>
                      {p.provider_name || p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <FormLabel>Model</FormLabel>
              <Select value={formData.model || ''} onValueChange={(value) => setFormData({ ...formData, model: value })}>
                <SelectTrigger disabled={!formData.provider}>
                  <SelectValue placeholder={formData.provider ? 'Select model' : 'Select provider first'} />
                </SelectTrigger>
                <SelectContent>
                  {modelsForProvider.map((m) => (
                    <SelectItem key={m.name} value={m.name}>
                      {m.model_name || m.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center gap-3 rounded-md border p-3">
              <Checkbox
                checked={formData.enable_auto_routing ?? false}
                onCheckedChange={(checked) =>
                  setFormData({ ...formData, enable_auto_routing: checked === true })
                }
              />
              <div className="flex-1">
                <label className="text-sm font-medium cursor-pointer">
                  Enable Auto Routing
                </label>
                <p className="text-xs text-muted-foreground">
                  Include this model in automatic Decision Policy routing decisions
                </p>
              </div>
            </div>

            <div className="space-y-2">
              <FormLabel>Routing Description (optional)</FormLabel>
              <Textarea
                placeholder="e.g., 'For complex reasoning tasks', 'Fast, cheap fallback'"
                value={formData.routing_description || ''}
                onChange={(e) =>
                  setFormData({ ...formData, routing_description: e.target.value })
                }
                className="min-h-[80px] resize-y"
              />
              <p className="text-xs text-muted-foreground">
                Notes on when this model should be routed to. Helps document your routing strategy.
              </p>
            </div>

            <div className="space-y-2">
              <FormLabel>Priority (optional)</FormLabel>
              <Input
                type="number"
                placeholder="0"
                value={formData.priority ?? ''}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    priority: e.target.value ? parseInt(e.target.value, 10) : undefined,
                  })
                }
                min="0"
              />
              <p className="text-xs text-muted-foreground">
                Lower numbers = higher priority. Used to order model selection when multiple models
                match a routing decision.
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setShowDialog(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={handleSave}
              disabled={!formData.provider || !formData.model}
            >
              {editingIndex !== null ? 'Update' : 'Add'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
