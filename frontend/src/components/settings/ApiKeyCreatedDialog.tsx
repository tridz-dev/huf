import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Check, Copy } from 'lucide-react';
import { toast } from 'sonner';
import type { CreatedApiKey } from '@/services/developerApi';

interface ApiKeyCreatedDialogProps {
  apiKey: CreatedApiKey | null;
  onClose: () => void;
}

export function ApiKeyCreatedDialog({ apiKey, onClose }: ApiKeyCreatedDialogProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!apiKey?.raw_secret) {
      return;
    }
    try {
      if (!navigator?.clipboard) {
        throw new Error('Clipboard API not available');
      }
      await navigator.clipboard.writeText(apiKey.raw_secret);
      setCopied(true);
      toast.success('Key copied to clipboard');
    } catch (error) {
      console.error(error);
      toast.error('Unable to copy key');
    }
  };

  return (
    <Dialog open={!!apiKey} onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Key created</DialogTitle>
          <DialogDescription>
            Copy this key now. For your security, you won't be able to see it again.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <div className="flex items-center gap-2 rounded-md border bg-muted px-3 py-2 font-mono text-sm break-all">
            {apiKey?.raw_secret}
          </div>
          <Button type="button" variant="outline" onClick={handleCopy} className="w-full">
            {copied ? <Check className="h-4 w-4 mr-2" /> : <Copy className="h-4 w-4 mr-2" />}
            {copied ? 'Copied' : 'Copy key'}
          </Button>
        </div>

        <DialogFooter>
          <Button onClick={onClose}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
