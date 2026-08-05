import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Database, Loader2, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import {
  getConversationData,
  setConversationDataItem,
  type ConversationDataItem,
} from '@/services/conversationDataApi';

interface ConversationDataPanelProps {
  conversationId: string;
  canWrite: boolean;
}

export function ConversationDataPanel({ conversationId, canWrite }: ConversationDataPanelProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<ConversationDataItem[]>([]);
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    const state = await getConversationData(conversationId);
    setItems(state?.items ?? []);
    setLoading(false);
  };

  useEffect(() => {
    if (open) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, conversationId]);

  const handleAdd = async () => {
    const key = newKey.trim();
    if (!key) {
      toast.error('Key is required');
      return;
    }
    setSaving(true);
    const success = await setConversationDataItem({
      conversationId,
      name: key,
      value: newValue,
    });
    setSaving(false);
    if (success) {
      toast.success(`Saved '${key}'`);
      setNewKey('');
      setNewValue('');
      load();
    }
  };

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="gap-2">
          <Database className="h-4 w-4" />
          Conversation data
        </Button>
      </SheetTrigger>
      <SheetContent className="w-full sm:max-w-md overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Conversation data</SheetTitle>
          <SheetDescription>
            Key/value memory items stored for this conversation.
            {!canWrite && ' Read-only for this agent.'}
          </SheetDescription>
        </SheetHeader>

        <div className="mt-4 space-y-3">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : items.length === 0 ? (
            <div className="text-sm text-muted-foreground py-4">No data stored yet.</div>
          ) : (
            items.map((item) => (
              <div key={item.name} className="rounded-md border p-3 space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-sm font-medium truncate">{item.name}</span>
                  <Badge variant="secondary" className="shrink-0">
                    {item.meta?.type || 'scalar'}
                  </Badge>
                </div>
                <div className="text-sm text-muted-foreground break-words whitespace-pre-wrap">
                  {typeof item.value === 'string' ? item.value : JSON.stringify(item.value)}
                </div>
              </div>
            ))
          )}
        </div>

        {canWrite && (
          <div className="mt-6 space-y-3 border-t pt-4">
            <Label className="font-medium">Add / update item</Label>
            <Input placeholder="Key" value={newKey} onChange={(e) => setNewKey(e.target.value)} />
            <Input placeholder="Value" value={newValue} onChange={(e) => setNewValue(e.target.value)} />
            <Button onClick={handleAdd} disabled={saving} size="sm" className="gap-2">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Save
            </Button>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
