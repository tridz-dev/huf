import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface Props {
  priority: number;
  maxChunks: number;
  tokenBudget: number;
  onPriority: (v: number) => void;
  onMaxChunks: (v: number) => void;
  onTokenBudget: (v: number) => void;
}

export function KnowledgeAdvancedFields(p: Props) {
  return (
    <div className="space-y-3 pt-2">
      <div className="space-y-1">
        <Label>Priority</Label>
        <Input type="number" min={0} value={p.priority} onChange={(e) => p.onPriority(Number(e.target.value))} />
        <p className="text-xs text-steel-soft">Higher-priority sources are searched first.</p>
      </div>
      <div className="space-y-1">
        <Label>Max results</Label>
        <Input type="number" min={1} value={p.maxChunks} onChange={(e) => p.onMaxChunks(Number(e.target.value))} />
        <p className="text-xs text-steel-soft">How many passages the agent sees.</p>
      </div>
      <div className="space-y-1">
        <Label>Token budget</Label>
        <Input type="number" min={0} value={p.tokenBudget} onChange={(e) => p.onTokenBudget(Number(e.target.value))} />
        <p className="text-xs text-steel-soft">Cap on text sent to the model.</p>
      </div>
    </div>
  );
}
